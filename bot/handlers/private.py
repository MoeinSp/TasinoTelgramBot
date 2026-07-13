"""
هندلرهای پیوی ربات تاسینو
"""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton as Btn

from bot import cache
from bot.cache_manager import load_all_caches, is_owner
from bot.panel_keyboards import panel_main
from bot.group_help import PAGE_MAIN
from bot.help_keyboards import get_help_content
from bot.constants import CREATOR_USER_ID
from bot.required_join import (
    is_creator,
    is_user_channel_member,
    is_forced_join_active,
    join_required_text,
    join_required_keyboard,
    creator_status_text,
    db_save_forced_join_channel,
    db_set_forced_join_enabled,
    db_clear_forced_join,
    verify_bot_channel_access,
    resolve_channel_invite_link,
)
from bot.site_config import (
    get_link_directory_url,
    get_link_directory_title,
    get_support_url,
    get_support_title,
    db_set_link_directory,
    db_set_support_url,
    db_set_premium_emoji,
    db_clear_premium_emoji,
    db_import_premium_emojis,
    db_set_dice_theme_field,
    db_reset_dice_theme,
    db_create_dice_theme,
    db_import_dice_themes,
    site_config_status_text,
)
from asgiref.sync import sync_to_async

router = Router()
router.message.filter(F.chat.type == "private")
_CREATOR_STATE: dict[int, str] = {}


def _welcome_kb(bot_username: str) -> InlineKeyboardMarkup:
    add_url = f"https://t.me/{bot_username}?startgroup=true"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            Btn(text="➕ افزودن ربات به گروه ↗️", url=add_url),
            Btn(text="🎲 تنظیمات گروه", callback_data="pv:group_settings"),
        ],
        [Btn(text=get_link_directory_title(), url=get_link_directory_url())],
        [Btn(text="📚 راهنمای ربات", callback_data="pv:help")],
    ])


def _creator_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="📊 وضعیت جوین اجباری", callback_data="cr:fj:status")],
        [Btn(text="🟢 روشن", callback_data="cr:fj:on"), Btn(text="⚫ خاموش", callback_data="cr:fj:off")],
        [Btn(text="🗑 حذف کانال", callback_data="cr:fj:clear"), Btn(text="📥 ثبت کانال با آیدی", callback_data="cr:fj:setid")],
        [Btn(text="🔗 وضعیت لینکدونی", callback_data="cr:ld:status")],
        [Btn(text="✏️ تنظیم لینکدونی", callback_data="cr:ld:set"), Btn(text="💬 تنظیم پشتیبانی", callback_data="cr:sp:set")],
        [Btn(text="🎨 ایموجی‌های پرمیوم", callback_data="cr:emoji:0")],
        [Btn(text="🎲 تم‌های تاس", callback_data="cr:theme:0")],
        [
            Btn(text="💾 بکاپ الان", callback_data="cr:backup:now"),
            Btn(text="♻️ بازیابی", callback_data="cr:backup:restore"),
        ],
        [Btn(text="🧠 وضعیت کش", callback_data="cr:cache:stats"), Btn(text="♻️ ریلود کش", callback_data="cr:cache:reload")],
        [Btn(text="🤖 اطلاعات ربات", callback_data="cr:bot:info"), Btn(text="📘 راهنمای سریع", callback_data="cr:help")],
    ])


def _creator_panel_text(name: str) -> str:
    return (
        f"👑 سلام {name}\n\n"
        "به <b>پنل سازنده تاسینو</b> خوش آمدید.\n"
        "جوین اجباری، لینکدونی، ایموجی، تم تاس، بکاپ و کش را از اینجا مدیریت کنید.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ Forced Join: {'🟢 فعال' if is_forced_join_active() else '⚫ غیرفعال'}\n"
        f"🔗 لینکدونی: <code>{get_link_directory_url()}</code>\n"
        "💾 بکاپ خودکار هر <b>۳ ساعت</b> به همین پیوی ارسال می‌شود."
    )


def _backup_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="✅ تأیید بازیابی", callback_data="cr:backup:confirm_yes")],
        [Btn(text="❌ انصراف", callback_data="cr:backup:confirm_no")],
    ])


def _theme_panel_text(page: int = 0) -> str:
    from bot.dice_themes import themes_page, page_count, theme_status_line, list_theme_ids, has_override

    total = page_count()
    page = max(0, min(int(page), total - 1))
    ids = themes_page(page)
    custom_n = sum(1 for tid in list_theme_ids() if has_override(tid))
    lines = [
        "🎲 <b>تم‌های تاس</b>",
        f"صفحه <b>{page + 1}</b> از <b>{total}</b> — کل: <b>{len(list_theme_ids())}</b> · سفارشی: <b>{custom_n}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "📦 پیش‌فرض · ✏️ ویرایش‌شده · 🆕 تم جدید",
        "",
    ]
    for tid in ids:
        lines.append(theme_status_line(tid))
    lines.append("\nروی تم بزن تا هدر تکی/جمعی، جداکننده، فوتر و وجه‌ها را عوض کنی.")
    lines.append("ایموجی پرمیوم را مستقیم بفرست یا از <code>{pe:dice}</code> استفاده کن.")
    return "\n".join(lines)


def _theme_panel_kb(page: int = 0) -> InlineKeyboardMarkup:
    from bot.dice_themes import themes_page, page_count

    total = page_count()
    page = max(0, min(int(page), total - 1))
    ids = themes_page(page)
    kb: list[list] = []
    row: list = []
    for tid in ids:
        row.append(Btn(text=f"🎲 {tid}", callback_data=f"cr:theme:item:{tid}:{page}"))
        if len(row) == 5:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    nav = []
    if page > 0:
        nav.append(Btn(text="◀️ قبلی", callback_data=f"cr:theme:{page - 1}"))
    if page < total - 1:
        nav.append(Btn(text="▶️ بعدی", callback_data=f"cr:theme:{page + 1}"))
    if nav:
        kb.append(nav)
    kb.append([
        Btn(text="➕ تم جدید", callback_data=f"cr:theme:new:{page}"),
        Btn(text="👁 پیش‌نمایش سریع", callback_data=f"cr:theme:quickprev:{page}"),
    ])
    kb.append([
        Btn(text="📤 اکسپورت", callback_data=f"cr:theme:export:{page}"),
        Btn(text="📥 ایمپورت", callback_data=f"cr:theme:import:{page}"),
    ])
    kb.append([Btn(text="🔙 بازگشت به پنل", callback_data="cr:theme:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def _theme_item_text(theme_id: int, page: int = 0) -> str:
    from html import escape
    from bot.dice_themes import (
        get_theme, get_field_value, has_override, is_custom_only, FIELD_LABELS,
    )

    theme = get_theme(theme_id)
    name = escape(str(theme.get("name") or f"#{theme_id}"))
    if is_custom_only(theme_id):
        status = "🆕 تم کاملاً سفارشی"
    elif has_override(theme_id):
        status = "✏️ ویرایش‌شده روی پیش‌فرض"
    else:
        status = "📦 پیش‌فرض داخلی"

    def _short(val: str, n: int = 80) -> str:
        v = (val or "").replace("\n", " ↵ ")
        return escape(v if len(v) <= n else v[: n - 1] + "…")

    lines = [
        f"🎲 <b>تم {theme_id}</b> — {name}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{status}\n",
        f"<b>{FIELD_LABELS['single_header']}:</b>\n{_short(get_field_value(theme_id, 'single_header'))}\n",
        f"<b>{FIELD_LABELS['multi_header']}:</b>\n{_short(get_field_value(theme_id, 'multi_header'))}\n",
        f"<b>{FIELD_LABELS['separator']}:</b> {_short(get_field_value(theme_id, 'separator'), 40)}\n",
        f"<b>{FIELD_LABELS['footer']}:</b>\n{_short(get_field_value(theme_id, 'footer'))}\n",
        "<b>وجه‌ها:</b>",
    ]
    for i in range(1, 7):
        lines.append(f"  {i} → {_short(get_field_value(theme_id, f'face_{i}'), 40)}")
    lines.append(
        "\n💡 پلیس‌هولدرها: <code>{value}</code> <code>{count}</code> "
        "<code>{total}</code> <code>{pe:dice}</code>"
    )
    return "\n".join(lines)


def _theme_item_kb(theme_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            Btn(text="✏️ نام", callback_data=f"cr:theme:set:{theme_id}:name:{page}"),
            Btn(text="👁 پیش‌نمایش", callback_data=f"cr:theme:prev:{theme_id}:{page}"),
        ],
        [Btn(text="📝 هدر تکی", callback_data=f"cr:theme:set:{theme_id}:single_header:{page}")],
        [Btn(text="📝 هدر جمعی", callback_data=f"cr:theme:set:{theme_id}:multi_header:{page}")],
        [
            Btn(text="➖ جداکننده", callback_data=f"cr:theme:set:{theme_id}:separator:{page}"),
            Btn(text="📉 فوتر", callback_data=f"cr:theme:set:{theme_id}:footer:{page}"),
        ],
        [
            Btn(text="۱", callback_data=f"cr:theme:set:{theme_id}:face_1:{page}"),
            Btn(text="۲", callback_data=f"cr:theme:set:{theme_id}:face_2:{page}"),
            Btn(text="۳", callback_data=f"cr:theme:set:{theme_id}:face_3:{page}"),
            Btn(text="۴", callback_data=f"cr:theme:set:{theme_id}:face_4:{page}"),
            Btn(text="۵", callback_data=f"cr:theme:set:{theme_id}:face_5:{page}"),
            Btn(text="۶", callback_data=f"cr:theme:set:{theme_id}:face_6:{page}"),
        ],
        [Btn(text="♻️ ریست به پیش‌فرض", callback_data=f"cr:theme:reset:{theme_id}:{page}")],
        [Btn(text="🔙 لیست تم‌ها", callback_data=f"cr:theme:{page}")],
    ])


def _theme_field_hint(field: str) -> str:
    from bot.dice_themes import FIELD_LABELS
    label = FIELD_LABELS.get(field, field)
    hints = {
        "name": "فقط یک نام کوتاه بفرست (مثلاً neon).",
        "single_header": (
            "متن هدر تاس تکی را بفرست.\n"
            "مثال:\n<code>{pe:dice} نتیجه: {value}</code>\n"
            "یا مستقیم ایموجی پرمیوم + متن بفرست."
        ),
        "multi_header": (
            "متن هدر تاس جمعی را بفرست.\n"
            "مثال:\n<code>{pe:dice} تاس × {count}</code>"
        ),
        "separator": "خط جداکننده بین وجه‌ها را بفرست.",
        "footer": (
            "متن فوتر (مجموع) را بفرست.\n"
            "مثال:\n<code>\\n{pe:dice} مجموع: {total}</code>"
        ),
    }
    if field.startswith("face_"):
        n = field.split("_", 1)[1]
        return (
            f"طرح وجه <b>{n}</b> را بفرست (می‌تواند چندخطی و شامل ایموجی پرمیوم باشد).\n"
            "مثال:\n<code>⬤ ⬤\\n  ⬤</code>"
        )
    return hints.get(field, f"مقدار جدید برای <b>{label}</b> را بفرست.")


def _emoji_panel_text(page: int = 0) -> str:
    from bot.premium_emoji import slots_page, page_count, EMOJI_SLOTS, PAGE_SIZE, get_id

    total = page_count()
    page = max(0, min(int(page), total - 1))
    rows = slots_page(page)
    set_n = sum(1 for k, _ in EMOJI_SLOTS if get_id(k))
    lines = [
        "🎨 <b>ایموجی‌های پرمیوم</b>",
        f"صفحه <b>{page + 1}</b> از <b>{total}</b> — تنظیم‌شده: <b>{set_n}/{len(EMOJI_SLOTS)}</b>",
        "━━━━━━━━━━━━━━━━━━━━\n",
    ]
    for i, st in enumerate(rows, start=page * PAGE_SIZE + 1):
        if st["set"]:
            src = "DB" if st["source"] == "db" else "ENV"
            lines.append(
                f"{i}. {st['preview']} <b>{st['key']}</b> — {st['label']}\n"
                f"   ✅ تنظیم شده ({src})\n"
                f"   <code>{st['id']}</code>\n"
            )
        else:
            lines.append(
                f"{i}. {st['fallback']} <b>{st['key']}</b> — {st['label']}\n"
                f"   ⚪ خالی (ایموجی عادی)\n"
            )
    lines.append("روی دکمه بزن تا تغییر یا پاک کنی.")
    return "\n".join(lines)


def _emoji_panel_kb(page: int = 0) -> InlineKeyboardMarkup:
    from bot.premium_emoji import slots_page, page_count

    total = page_count()
    page = max(0, min(int(page), total - 1))
    rows = slots_page(page)
    kb: list[list] = []
    for st in rows:
        mark = "✅" if st["set"] else "⚪"
        kb.append([
            Btn(
                text=f"{mark} {st['fallback']} {st['key']}",
                callback_data=f"cr:emoji:item:{st['key']}:{page}",
            )
        ])
    nav = []
    if page > 0:
        nav.append(Btn(text="◀️ قبلی", callback_data=f"cr:emoji:{page - 1}"))
    if page < total - 1:
        nav.append(Btn(text="▶️ بعدی", callback_data=f"cr:emoji:{page + 1}"))
    if nav:
        kb.append(nav)
    kb.append([
        Btn(text="📤 اکسپورت", callback_data=f"cr:emoji:export:{page}"),
        Btn(text="📥 ایمپورت", callback_data=f"cr:emoji:import:{page}"),
    ])
    kb.append([Btn(text="🔙 بازگشت به پنل", callback_data="cr:emoji:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def _emoji_item_text(key: str, page: int = 0) -> str:
    from bot.premium_emoji import slot_status

    st = slot_status(key)
    if st["set"]:
        body = (
            f"وضعیت: ✅ تنظیم شده ({'دیتابیس' if st['source'] == 'db' else 'env'})\n"
            f"پیش‌نمایش: {st['preview']}\n"
            f"ID: <code>{st['id']}</code>"
        )
    else:
        body = (
            f"وضعیت: ⚪ خالی\n"
            f"الان نشان داده می‌شود: {st['fallback']}\n"
            "هنوز ID پرمیوم ندارد."
        )
    return (
        f"🎨 <b>{st['key']}</b> — {st['label']}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}\n\n"
        "نام اسلات فقط محل استفاده در متن است.\n"
        "برای تغییر: هر ایموجی پرمیوم دلخواه را بفرست (یا ID عددی)."
    )


def _emoji_item_kb(key: str, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="✏️ تغییر", callback_data=f"cr:emoji:set:{key}:{page}")],
        [Btn(text="🗑 پاک کردن", callback_data=f"cr:emoji:clear:{key}:{page}")],
        [Btn(text="🔙 لیست ایموجی‌ها", callback_data=f"cr:emoji:{page}")],
    ])


def _welcome_text(name: str, bot_username: str) -> str:
    from bot.premium_emoji import pe
    add_url = f"https://t.me/{bot_username}?startgroup=true"
    support = get_support_url()
    support_title = get_support_title()
    return (
        f"سلام <b>{name}</b> عزیز {pe('rose', '🌹')}\n\n"
        f"به ربات <b>تاسینو</b> خوش آمدید! {pe('wave', '👋')}\n"
        "ابزاری قدرتمند برای مدیریت گروه، امنیت و برگزاری مسابقات تاس.\n\n"
        f"<b>{pe('spark', '✨')} ویژگی‌های کلیدی:</b>\n"
        f"{pe('check', '✅')} پاسخ‌دهی سریع و پایدار\n"
        f"{pe('check', '✅')} محافظت کامل گروه و آنتی‌اسپم\n"
        f"{pe('check', '✅')} قفل‌های پیشرفته و فیلتر کلمات\n"
        f"{pe('check', '✅')} سیستم اخطار، سکوت و مدیریت اعضا\n"
        f"{pe('dice', '🎲')} مسابقات تاس با شرط و کیف پول\n"
        f"{pe('gear', '⚙️')} پنل اینلاین تنظیمات در گروه\n"
        f"{pe('check', '✅')} خوشامدگویی، کپچا و آنتی‌فلود\n"
        f"{pe('money', '💰')} گزارش مالی و حق واسطه\n\n"
        f"<b>{pe('rocket', '🚀')} نصب و راه‌اندازی:</b>\n"
        f'۱. ربات را به گروه اضافه کنید: <a href="{add_url}">کلیک کنید</a>\n'
        "۲. ربات را به عنوان <b>ادمین کامل</b> ارتقا دهید\n\n"
        f"<b>{pe('pin', '📌')} نکات مهم:</b>\n"
        "• گروه باید از نوع <b>سوپرگروه</b> باشد\n"
        "• برای تنظیمات در گروه بنویسید: <code>پنل</code>\n"
        "• برای راهنما در گروه بنویسید: <code>راهنما</code>\n\n"
        f'در صورت بروز مشکل به <a href="{support}">{support_title}</a> بپیوندید {pe("heart", "❤️")}\n\n'
        f"─── {pe('dice', '🎲')} <b>تاسینو</b> ───"
    )


async def _send_welcome(message: Message, bot: Bot | None = None, user=None):
    user = user or message.from_user
    name = (user.first_name if user else None) or "کاربر"
    if is_creator(user.id if user else message.from_user.id):
        return await message.answer(
            _creator_panel_text(name),
            reply_markup=_creator_panel_kb(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    bot = bot or message.bot
    me = await bot.get_me()
    username = me.username or "TasinoBot"
    await message.answer(
        _welcome_text(name, username),
        reply_markup=_welcome_kb(username),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(CommandStart())
async def start(message: Message, bot: Bot):
    from bot.finance import save_telegram_user
    await save_telegram_user(message.from_user.id, message.chat.id)
    _CREATOR_STATE.pop(message.from_user.id, None)
    if is_forced_join_active() and not is_creator(message.from_user.id):
        if not await is_user_channel_member(bot, message.from_user.id):
            return await message.answer(
                join_required_text(),
                reply_markup=join_required_keyboard(),
                parse_mode="HTML",
            )
    await _send_welcome(message, bot)


def _waiting_settle_amount(message: Message) -> bool:
    from bot.accounts_panel import is_waiting_settle_amount
    return bool(message.from_user and is_waiting_settle_amount(message.from_user.id))


@router.message(F.text, F.func(_waiting_settle_amount))
async def pv_settle_amount_catch(message: Message, bot: Bot):
    """مبلغ تسویه دلخواه از پنل حساب‌ها در پیوی."""
    from bot.accounts_panel import handle_settle_amount_message
    await handle_settle_amount_message(message, bot)


def _waiting_increase_amount(message: Message) -> bool:
    from bot.hidden_increase import is_waiting_increase_amount
    return bool(message.from_user and is_waiting_increase_amount(message.from_user.id))


@router.message(F.text, F.func(_waiting_increase_amount))
async def pv_increase_amount_catch(message: Message, bot: Bot):
    """مبلغ افزایش موجودی مخفی در پیوی."""
    from bot.hidden_increase import handle_increase_amount_message
    await handle_increase_amount_message(message, bot)


@router.message(F.text.in_(["استارت", "شروع", "start", "Start", "START"]))
async def msg_start_alias(message: Message, bot: Bot):
    from bot.finance import save_telegram_user
    await save_telegram_user(message.from_user.id, message.chat.id)
    if is_forced_join_active() and not is_creator(message.from_user.id):
        if not await is_user_channel_member(bot, message.from_user.id):
            return await message.answer(
                join_required_text(),
                reply_markup=join_required_keyboard(),
                parse_mode="HTML",
            )
    await _send_welcome(message, bot)


@router.callback_query(F.data == "join:recheck")
async def cb_join_recheck(call: CallbackQuery, bot: Bot):
    if await is_user_channel_member(bot, call.from_user.id, bypass_cache=True):
        await call.answer("✅ عضویت شما تأیید شد!", show_alert=True)
        try:
            await call.message.edit_text(
                "✅ <b>عضویت تأیید شد</b>\n\n"
                "اکنون می‌توانید از تمام خدمات ربات استفاده کنید.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await _send_welcome(call.message, bot, user=call.from_user)
        return
    await call.answer("هنوز عضو کانال نشده‌اید.", show_alert=True)
    try:
        await call.message.edit_text(
            join_required_text(),
            reply_markup=join_required_keyboard(),
            parse_mode="HTML",
        )
    except Exception:
        await call.message.answer(
            join_required_text(),
            reply_markup=join_required_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "pv:help")
async def cb_pv_help(call: CallbackQuery):
    text, kb = get_help_content("0")
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("h:"))
async def cb_help_nav(call: CallbackQuery, bot: Bot):
    code = call.data[2:]
    if code == "home":
        await call.answer()
        return await _send_welcome(call.message, bot, user=call.from_user)

    text, kb = get_help_content(code)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@sync_to_async
def _db_owned_groups(user_id: int) -> list[dict]:
    from account.models import TelegramGroup, TelegramGroupMember

    chat_ids = set()
    for cid, oid in cache.OWNER_CACHE.items():
        if oid == user_id:
            chat_ids.add(cid)

    for m in TelegramGroupMember.objects.filter(
        telegram_user_id=user_id, is_owner=True,
    ).only("telegram_chat_id"):
        chat_ids.add(m.telegram_chat_id)

    if not chat_ids:
        return []

    groups = {
        g.telegram_chat_id: g
        for g in TelegramGroup.objects.filter(telegram_chat_id__in=chat_ids)
    }
    result = []
    for cid in chat_ids:
        g = groups.get(cid)
        if g is not None and (not g.is_active or g.off):
            continue
        if cid in cache.OFF_GROUP:
            continue
        name = (g.name if g and g.name else None) or f"گروه {cid}"
        result.append({"chat_id": cid, "name": name})
    return result


async def _owned_active_groups(bot: Bot, user_id: int) -> list[dict]:
    """گروه‌هایی که کاربر مالک است و ربات هنوز داخلشان فعال است."""
    candidates = await _db_owned_groups(user_id)
    if not candidates:
        return []
    me = await bot.get_me()
    active = []
    for item in candidates:
        cid = item["chat_id"]
        try:
            member = await bot.get_chat_member(cid, me.id)
            if member.status not in ("administrator", "member", "creator"):
                continue
            chat = await bot.get_chat(cid)
            if chat.title:
                item["name"] = chat.title
            active.append(item)
        except Exception:
            continue
    return active


def _groups_list_kb(groups: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for g in groups:
        label = f"🏷 {g['name']}"
        if len(label) > 60:
            label = label[:57] + "…"
        rows.append([Btn(text=label, callback_data=f"gs:sel:{g['chat_id']}")])
    rows.append([Btn(text="🔄 بروزرسانی لیست", callback_data="gs:list")])
    rows.append([Btn(text="🏠 بازگشت به منوی اصلی", callback_data="h:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_groups_list(call: CallbackQuery, bot: Bot, edit: bool = True):
    groups = await _owned_active_groups(bot, call.from_user.id)
    if not groups:
        text = (
            "🎲 <b>تنظیمات گروه</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ گروهی پیدا نشد که:\n"
            "• شما مالک آن باشید\n"
            "• و ربات داخلش فعال باشد\n\n"
            "ربات را به گروه اضافه کنید، ادمین کامل کنید،\n"
            "سپس دوباره این دکمه را بزنید."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [Btn(text="🔄 تلاش مجدد", callback_data="gs:list")],
            [Btn(text="🏠 بازگشت به منوی اصلی", callback_data="h:home")],
        ])
    else:
        text = (
            "🎲 <b>تنظیمات گروه</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 {len(groups)} گروه فعال پیدا شد.\n"
            "گروه مورد نظر را انتخاب کنید:"
        )
        kb = _groups_list_kb(groups)

    if edit:
        try:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await call.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "pv:group_settings")
async def cb_pv_group_settings(call: CallbackQuery, bot: Bot):
    await call.answer()
    await _show_groups_list(call, bot, edit=True)


@router.callback_query(F.data == "gs:list")
async def cb_gs_list(call: CallbackQuery, bot: Bot):
    await call.answer("در حال بارگذاری…")
    await _show_groups_list(call, bot, edit=True)


@router.callback_query(F.data.startswith("gs:sel:"))
async def cb_gs_select(call: CallbackQuery, bot: Bot):
    try:
        chat_id = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        return await call.answer("❌ گروه نامعتبر", show_alert=True)

    user_id = call.from_user.id
    if user_id != CREATOR_USER_ID and not is_owner(chat_id, user_id):
        # ممکن است کش قدیمی باشد — از DB چک کن
        owned = await _db_owned_groups(user_id)
        if chat_id not in {g["chat_id"] for g in owned}:
            return await call.answer("❌ فقط مالک گروه دسترسی دارد.", show_alert=True)

    # تایید حضور ربات
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        if member.status not in ("administrator", "member", "creator"):
            return await call.answer("❌ ربات در این گروه فعال نیست.", show_alert=True)
        chat = await bot.get_chat(chat_id)
        gname = chat.title or str(chat_id)
    except Exception:
        return await call.answer("❌ دسترسی به گروه ممکن نیست.", show_alert=True)

    cache.PV_PANEL_GROUP[user_id] = chat_id
    text = (
        f"⚙️ <b>پنل تنظیمات</b>\n"
        f"🏷 گروه: <b>{gname}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{PAGE_MAIN}"
    )
    kb = panel_main(pv=True)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer(f"✅ {gname}")


@router.message(Command("help"))
async def cmd_help(message: Message):
    text, kb = get_help_content("0")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


def _emoji_id_report(found: list[dict]) -> str:
    from bot.premium_emoji import tg_emoji

    lines = ["✅ <b>ایموجی پرمیوم</b>\n"]
    env_parts = []
    for i, item in enumerate(found, 1):
        alt = item["alt"] or "⭐"
        eid = item["id"]
        preview = tg_emoji(eid, alt)
        lines.append(f"{i}. {preview}  ID: <code>{eid}</code>")
        env_parts.append(f"emoji{i}:{eid}" if i > 1 else f"rose:{eid}")
    lines.append("\nخط env:\n<code>PREMIUM_EMOJI_IDS=" + ",".join(env_parts) + "</code>")
    return "\n".join(lines)


def _waiting_theme_field(message: Message) -> bool:
    if not message.from_user or not is_creator(message.from_user.id):
        return False
    state = _CREATOR_STATE.get(message.from_user.id) or ""
    return state.startswith("await_theme:")


def _waiting_theme_import(message: Message) -> bool:
    if not message.from_user or not is_creator(message.from_user.id):
        return False
    state = _CREATOR_STATE.get(message.from_user.id) or ""
    return state.startswith("await_theme_import")


@router.message(F.text, F.func(_waiting_theme_field))
async def cmd_creator_theme_field(message: Message):
    """ذخیره فیلد تم — متن معمولی یا با ایموجی پرمیوم."""
    from bot.dice_themes import message_to_theme_html, FIELD_LABELS

    state = _CREATOR_STATE.get(message.from_user.id) or ""
    # await_theme:4:single_header:0
    parts = state.split(":")
    if len(parts) < 3:
        return
    tid = int(parts[1]) if parts[1].isdigit() else 0
    field = parts[2]
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    if not tid or not field:
        return

    value = message_to_theme_html(message)
    # پشتیبانی از \n تایپ‌شده
    if "\\n" in value and "<tg-emoji" not in value:
        value = value.replace("\\n", "\n")

    await db_set_dice_theme_field(tid, field, value)
    _CREATOR_STATE.pop(message.from_user.id, None)
    label = FIELD_LABELS.get(field, field)
    await message.answer(
        f"✅ تم <b>{tid}</b> — <b>{label}</b> ذخیره شد.\n\n"
        "برای دیدن نتیجه «پیش‌نمایش» را بزن.",
        reply_markup=_theme_item_kb(tid, page),
        parse_mode="HTML",
    )


@router.message(F.text, F.func(_waiting_theme_import))
async def cmd_creator_theme_import(message: Message):
    from bot.dice_themes import parse_theme_import

    state = _CREATOR_STATE.get(message.from_user.id) or ""
    replace = state.startswith("await_theme_import_replace")
    page = 0
    parts = state.split(":")
    if parts and parts[-1].isdigit():
        page = int(parts[-1])

    entries, err = parse_theme_import(message.text or "")
    if err:
        return await message.answer(f"❌ {err}", parse_mode="HTML")

    await db_import_dice_themes(entries, replace=replace)
    _CREATOR_STATE.pop(message.from_user.id, None)
    mode = "جایگزین شد" if replace else "ادغام شد"
    await message.answer(
        f"✅ ایمپورت تم {mode}: <b>{len(entries)}</b> تم\n"
        + "\n".join(f"• تم <code>{k}</code>" for k in list(entries.keys())[:20]),
        reply_markup=_theme_panel_kb(page),
        parse_mode="HTML",
    )


def _creator_emoji_only(message: Message) -> bool:
    if not message.from_user or not is_creator(message.from_user.id):
        return False
    # اگر منتظر فیلد تم هستیم، هندلر تم اولویت دارد
    state = _CREATOR_STATE.get(message.from_user.id) or ""
    if state.startswith("await_theme"):
        return False
    from bot.premium_emoji import is_custom_emoji_only_message
    return is_custom_emoji_only_message(message)


async def _apply_emoji_id(message: Message, key: str, emoji_id: str, page: int = 0, alt: str = "⭐"):
    from bot.premium_emoji import tg_emoji, DEFAULTS

    fb = alt if alt and alt != "?" else DEFAULTS.get(key, "⭐")
    await db_set_premium_emoji(key, emoji_id, fb)
    _CREATOR_STATE.pop(message.from_user.id, None)
    preview = tg_emoji(emoji_id, fb)
    await message.answer(
        f"✅ اسلات <b>{key}</b> با ایموجی دلخواهت ذخیره شد\n\n"
        f"پیش‌نمایش: {preview}\n"
        f"ID: <code>{emoji_id}</code>\n\n"
        "<i>نام اسلات فقط برای جای متن است؛ خود ایموجی هر چیزی می‌تواند باشد.</i>",
        reply_markup=_emoji_item_kb(key, page),
        parse_mode="HTML",
    )


@router.message(F.text, F.func(_creator_emoji_only))
async def cmd_creator_premium_emoji_auto(message: Message):
    """مالک فقط ایموجی پرمیوم فرستاد → تنظیم اسلات یا نمایش ID."""
    from bot.premium_emoji import extract_custom_emoji_ids

    found = extract_custom_emoji_ids(message)
    if not found:
        return

    state = _CREATOR_STATE.get(message.from_user.id) or ""
    if state.startswith("await_emoji:"):
        parts = state.split(":")
        # await_emoji:rose:0
        key = parts[1] if len(parts) > 1 else ""
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        if key:
            return await _apply_emoji_id(
                message, key, found[0]["id"], page, found[0].get("alt") or "⭐"
            )

    await message.answer(_emoji_id_report(found), parse_mode="HTML")


@router.message(
    F.text.regexp(r"^\d{10,}$"),
    F.func(lambda m: bool(m.from_user) and is_creator(m.from_user.id)),
)
async def cmd_creator_emoji_id_paste(message: Message):
    """وقتی منتظر ایموجی هستیم، ID عددی هم قبول شود."""
    state = _CREATOR_STATE.get(message.from_user.id) or ""
    if not state.startswith("await_emoji:"):
        return
    parts = state.split(":")
    key = parts[1] if len(parts) > 1 else ""
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    if not key:
        return
    await _apply_emoji_id(message, key, message.text.strip(), page)


def _waiting_emoji_import(message: Message) -> bool:
    if not message.from_user or not is_creator(message.from_user.id):
        return False
    state = _CREATOR_STATE.get(message.from_user.id) or ""
    return state.startswith("await_emoji_import")


@router.message(F.text, F.func(_waiting_emoji_import))
async def cmd_creator_emoji_import(message: Message):
    from bot.premium_emoji import parse_import_payload

    state = _CREATOR_STATE.get(message.from_user.id) or ""
    replace = state.startswith("await_emoji_import_replace")
    page = 0
    parts = state.split(":")
    if parts and parts[-1].isdigit():
        page = int(parts[-1])

    entries, err = parse_import_payload(message.text or "")
    if err:
        return await message.answer(f"❌ {err}", parse_mode="HTML")

    await db_import_premium_emojis(entries, replace=replace)
    _CREATOR_STATE.pop(message.from_user.id, None)
    mode = "جایگزین شد" if replace else "ادغام شد"
    await message.answer(
        f"✅ ایمپورت {mode}: <b>{len(entries)}</b> اسلات\n\n"
        + "\n".join(f"• <code>{k}</code> → <code>{v['id']}</code>" for k, v in list(entries.items())[:20]),
        reply_markup=_emoji_panel_kb(page),
        parse_mode="HTML",
    )


@router.message(Command("emoji_id"))
async def cmd_emoji_id(message: Message):
    """ریپلای به پیام دارای ایموجی پرمیوم → نمایش custom_emoji_id."""
    if not is_creator(message.from_user.id):
        return
    from bot.premium_emoji import extract_custom_emoji_ids, configured_names

    src = message.reply_to_message
    if not src:
        names = configured_names()
        configured = ", ".join(names) if names else "هیچ‌کدام"
        return await message.answer(
            "📌 ایموجی پرمیوم را <b>تنها</b> در پیوی بفرست تا خودکار ID بدهد.\n"
            "یا به پیام ریپلای کن و بزن: <code>/emoji_id</code>\n\n"
            f"کلیدهای لودشده: <code>{configured}</code>\n\n"
            "تست: <code>/emoji_test</code>",
            parse_mode="HTML",
        )
    found = extract_custom_emoji_ids(src)
    if not found:
        return await message.answer(
            "❌ در پیام ریپلای‌شده ایموجی پرمیوم پیدا نشد.",
            parse_mode="HTML",
        )
    await message.answer(_emoji_id_report(found), parse_mode="HTML")


@router.message(Command("emoji_test"))
async def cmd_emoji_test(message: Message):
    """نمایش وضعیت env و ارسال نمونه rose پرمیوم."""
    if not is_creator(message.from_user.id):
        return
    from bot.premium_emoji import pe, get_id, configured_names, reload_ids

    reload_ids()
    names = configured_names()
    rose_id = get_id("rose")
    html = pe("rose", "🌹")
    status = "✅ ID لود شده" if rose_id else "❌ ID لود نشده (env خالی یا غلط)"
    await message.answer(
        "🧪 <b>تست ایموجی پرمیوم</b>\n\n"
        f"وضعیت rose: {status}\n"
        f"ID: <code>{rose_id or '—'}</code>\n"
        f"کلیدها: <code>{', '.join(names) if names else 'هیچ‌کدام'}</code>\n\n"
        f"نمونه: {html}\n\n"
        f"HTML خام:\n<code>{html}</code>\n\n"
        "اگر نمونه بالا گل معمولی است:\n"
        "• یا env به ربات نرسیده (ری‌استارت کن)\n"
        "• یا Premium روی اکانت سازنده ربات در BotFather نیست\n"
        "• یا ID اشتباه است",
        parse_mode="HTML",
    )

@router.message(F.text.in_(["راهنما", "help"]))
async def msg_help(message: Message):
    text, kb = get_help_content("0")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text.in_(["منو", "پنل", "menu"]))
async def msg_menu_alias(message: Message, bot: Bot):
    """در پیوی: لیست گروه‌ها برای تنظیمات."""
    groups = await _owned_active_groups(bot, message.from_user.id)
    if not groups:
        return await message.answer(
            "🎲 <b>تنظیمات گروه</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "گروه فعالی که مالک آن باشید پیدا نشد.\n"
            "برای راهنما بنویسید: <code>راهنما</code>",
            parse_mode="HTML",
        )
    text = (
        "🎲 <b>تنظیمات گروه</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 {len(groups)} گروه فعال پیدا شد.\n"
        "گروه مورد نظر را انتخاب کنید:"
    )
    await message.answer(text, reply_markup=_groups_list_kb(groups), parse_mode="HTML")


@router.callback_query(F.data.startswith("cr:"))
async def cb_creator_panel(call: CallbackQuery, bot: Bot):
    if not is_creator(call.from_user.id):
        return await call.answer("⛔️ این پنل فقط برای سازنده است.", show_alert=True)

    action = call.data[3:]

    if action == "fj:status":
        await call.message.answer(creator_status_text(), parse_mode="HTML")
        return await call.answer("📊 وضعیت ارسال شد")

    if action == "fj:on":
        if not cache.FORCED_JOIN.get("channel_id"):
            await call.answer("اول کانال را تنظیم کن.", show_alert=True)
            await call.message.answer(
                "❌ ابتدا کانال را تنظیم کنید:\n"
                "<code>تنظیم کانال اجباری -1001234567890</code>\n"
                "یا یک پیام از کانال فوروارد کنید.",
                parse_mode="HTML",
            )
            return
        await db_set_forced_join_enabled(True)
        await call.message.answer("🟢 جوین اجباری فعال شد.", parse_mode="HTML")
        return await call.answer("انجام شد")

    if action == "fj:off":
        await db_set_forced_join_enabled(False)
        await call.message.answer("⚫ جوین اجباری غیرفعال شد.", parse_mode="HTML")
        return await call.answer("انجام شد")

    if action == "fj:clear":
        await db_clear_forced_join()
        await call.message.answer("🗑 کانال اجباری حذف شد و سیستم غیرفعال شد.", parse_mode="HTML")
        return await call.answer("حذف شد")

    if action == "fj:setid":
        _CREATOR_STATE[call.from_user.id] = "await_channel_id"
        await call.message.answer(
            "📥 شناسه کانال را ارسال کنید.\n"
            "نمونه: <code>-1001234567890</code>\n"
            "یا یک پیام از کانال فوروارد کنید.",
            parse_mode="HTML",
        )
        return await call.answer("منتظر آیدی کانال...")

    if action == "cache:stats":
        joined_cache = len(cache.FORCED_JOIN_MEMBER_CHECK)
        await call.message.answer(
            "🧠 <b>وضعیت کش</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"• CACHE_LOADED: {'✅' if cache.CACHE_LOADED else '❌'}\n"
            f"• ForcedJoin Cache Keys: <code>{joined_cache}</code>\n"
            f"• Groups Cache: <code>{len(cache.GROUP_LOCKS)}</code>\n"
            f"• Admins Cache: <code>{len(cache.ADMINS_CACHE)}</code>\n"
            f"• VIP Cache: <code>{len(cache.VIP_USERS_CACHE)}</code>",
            parse_mode="HTML",
        )
        return await call.answer("ارسال شد")

    if action == "cache:reload":
        await load_all_caches()
        await call.message.answer("♻️ کش‌ها با موفقیت دوباره بارگذاری شدند.", parse_mode="HTML")
        return await call.answer("ریلود شد")

    if action == "bot:info":
        me = await bot.get_me()
        await call.message.answer(
            "🤖 <b>اطلاعات ربات</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"• Name: <b>{me.full_name}</b>\n"
            f"• Username: @{me.username}\n"
            f"• ID: <code>{me.id}</code>\n"
            f"• Forced Join: {'🟢 فعال' if is_forced_join_active() else '⚫ غیرفعال'}",
            parse_mode="HTML",
        )
        return await call.answer("آماده")

    if action == "help":
        await call.message.answer(
            "📘 <b>راهنمای سریع پنل سازنده</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "• تنظیم کانال: <code>تنظیم کانال اجباری -1001234567890</code>\n"
            "• یا فوروارد یک پیام از کانال\n"
            "• روشن: <code>جوین اجباری روشن</code>\n"
            "• خاموش: <code>جوین اجباری خاموش</code>\n"
            "• وضعیت: <code>وضعیت جوین اجباری</code>\n"
            "• حذف: <code>حذف کانال اجباری</code>\n\n"
            "🔗 لینکدونی:\n"
            "• <code>تنظیم لینکدونی https://t.me/xxx</code>\n"
            "• <code>تنظیم لینکدونی https://t.me/xxx | متن دکمه</code>\n"
            "• <code>وضعیت لینکدونی</code>\n\n"
            "💬 پشتیبانی:\n"
            "• <code>تنظیم پشتیبانی https://t.me/Spayers</code>\n\n"
            "🎨 ایموجی پرمیوم و 🎲 تم تاس از دکمه‌های پنل.\n\n"
            "💾 بکاپ:\n"
            "• خودکار هر ۳ ساعت به پیوی شما\n"
            "• دستی: دکمه «بکاپ الان» یا دستور <code>بکاپ</code>\n"
            "• بازیابی: دکمه «بازیابی» سپس ارسال فایل دامپ\n\n"
            "اگر ربات ادمین کانال نباشد، بررسی عضویت انجام نمی‌شود.",
            parse_mode="HTML",
        )
        return await call.answer("راهنما ارسال شد")

    if action == "ld:status":
        await call.message.answer(site_config_status_text(), parse_mode="HTML", disable_web_page_preview=True)
        return await call.answer("ارسال شد")

    if action == "ld:set":
        _CREATOR_STATE[call.from_user.id] = "await_link_directory"
        await call.message.answer(
            "🔗 لینک لینکدونی را ارسال کنید.\n\n"
            "نمونه:\n"
            "<code>https://t.me/TasinoBot</code>\n"
            "یا با متن دکمه:\n"
            "<code>https://t.me/xxx | 🔥 لینکدونی من</code>",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return await call.answer("منتظر لینک…")

    if action == "sp:set":
        _CREATOR_STATE[call.from_user.id] = "await_support_url"
        await call.message.answer(
            "💬 لینک پشتیبانی را ارسال کنید.\n\n"
            "نمونه:\n"
            "<code>https://t.me/Spayers</code>\n"
            "یا با عنوان:\n"
            "<code>https://t.me/Spayers | پشتیبانی تاسینو</code>",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return await call.answer("منتظر لینک…")

    # ─── ایموجی پرمیوم ─────────────────────────────────────────────────────
    if action == "emoji:back":
        name = call.from_user.first_name or "سازنده"
        try:
            await call.message.edit_text(
                _creator_panel_text(name),
                reply_markup=_creator_panel_kb(),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            await call.message.answer(
                _creator_panel_text(name),
                reply_markup=_creator_panel_kb(),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        return await call.answer()

    if action.startswith("emoji:item:"):
        # emoji:item:rose:0
        parts = action.split(":")
        key = parts[2] if len(parts) > 2 else ""
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        if not key:
            return await call.answer("نامعتبر", show_alert=True)
        try:
            await call.message.edit_text(
                _emoji_item_text(key, page),
                reply_markup=_emoji_item_kb(key, page),
                parse_mode="HTML",
            )
        except Exception:
            await call.message.answer(
                _emoji_item_text(key, page),
                reply_markup=_emoji_item_kb(key, page),
                parse_mode="HTML",
            )
        return await call.answer()

    if action.startswith("emoji:set:"):
        parts = action.split(":")
        key = parts[2] if len(parts) > 2 else ""
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        if not key:
            return await call.answer("نامعتبر", show_alert=True)
        _CREATOR_STATE[call.from_user.id] = f"await_emoji:{key}:{page}"
        await call.message.answer(
            f"✏️ برای اسلات <b>{key}</b> هر <b>ایموجی پرمیوم دلخواه</b> را بفرست.\n\n"
            "لازم نیست شبیه نام اسلات باشد — هر کدام که بخوای.\n"
            "یا فقط شناسه عددی را بفرست.\n\n"
            "لغو: /start",
            parse_mode="HTML",
        )
        return await call.answer("منتظر ایموجی…")

    if action.startswith("emoji:export:"):
        from html import escape
        from bot.premium_emoji import export_settings_json, export_settings_env_line, export_settings
        page_s = action.split(":")[-1]
        data = export_settings()
        n = len(data.get("premium_emoji_ids") or {})
        if not n:
            await call.answer("چیزی برای اکسپورت نیست", show_alert=True)
            return
        js = export_settings_json(pretty=True)
        env_line = export_settings_env_line()
        text = (
            f"📤 <b>اکسپورت ایموجی پرمیوم</b> — {n} مورد\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "JSON (برای ایمپورت کامل با alt):\n"
            f"<pre>{escape(js)}</pre>\n\n"
            "خط env:\n"
            f"<code>{escape(env_line)}</code>"
        )
        if len(text) > 3900:
            text = (
                f"📤 <b>اکسپورت</b> — {n} مورد\n\n"
                f"<pre>{escape(js[:3500])}</pre>"
            )
        await call.message.answer(text, parse_mode="HTML")
        return await call.answer("اکسپورت شد")

    if action.startswith("emoji:import_do:"):
        # emoji:import_do:merge:0 یا replace:0
        parts = action.split(":")
        mode = parts[2] if len(parts) > 2 else "merge"
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        replace = mode == "replace"
        _CREATOR_STATE[call.from_user.id] = (
            f"await_emoji_import_replace:{page}" if replace else f"await_emoji_import:{page}"
        )
        mode_txt = "جایگزینی کامل (پاک کردن قبلی‌ها)" if replace else "ادغام با تنظیمات فعلی"
        await call.message.answer(
            f"📥 <b>ایمپورت ایموجی</b> — {mode_txt}\n\n"
            "یکی از این‌ها را بفرست:\n"
            "• همان JSON اکسپورت\n"
            "• <code>rose:123,dice:456</code>\n"
            "• <code>PREMIUM_EMOJI_IDS=rose:123,...</code>\n\n"
            "لغو: /start",
            parse_mode="HTML",
        )
        return await call.answer("منتظر فایل/متن…")

    if action.startswith("emoji:import:"):
        page_s = action.split(":")[-1]
        page = int(page_s) if page_s.isdigit() else 0
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [Btn(text="➕ ادغام (Merge)", callback_data=f"cr:emoji:import_do:merge:{page}")],
            [Btn(text="♻️ جایگزینی کامل", callback_data=f"cr:emoji:import_do:replace:{page}")],
            [Btn(text="🔙 بازگشت", callback_data=f"cr:emoji:{page}")],
        ])
        await call.message.answer(
            "📥 <b>ایمپورت تنظیمات ایموجی</b>\n\n"
            "• <b>ادغام</b>: روی اسلات‌های فعلی می‌نشیند\n"
            "• <b>جایگزینی</b>: همه را پاک می‌کند و از نو می‌نویسد",
            reply_markup=kb,
            parse_mode="HTML",
        )
        return await call.answer()

    if action.startswith("emoji:clear:"):
        parts = action.split(":")
        key = parts[2] if len(parts) > 2 else ""
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        if not key:
            return await call.answer("نامعتبر", show_alert=True)
        await db_clear_premium_emoji(key)
        from bot.premium_emoji import slot_status
        st = slot_status(key)
        note = ""
        if st["set"] and st["source"] == "env":
            note = "\n\n⚠️ هنوز از <b>env</b> می‌آید؛ برای حذف کامل از <code>PREMIUM_EMOJI_IDS</code> هم پاک کن."
        try:
            await call.message.edit_text(
                _emoji_item_text(key, page) + "\n\n🗑 از دیتابیس پاک شد." + note,
                reply_markup=_emoji_item_kb(key, page),
                parse_mode="HTML",
            )
        except Exception:
            await call.message.answer(
                f"🗑 <b>{key}</b> پاک شد." + note,
                reply_markup=_emoji_item_kb(key, page),
                parse_mode="HTML",
            )
        return await call.answer("پاک شد")

    if action.startswith("emoji:"):
        # emoji:0 / emoji:1 ...
        page_s = action.split(":", 1)[1]
        page = int(page_s) if page_s.isdigit() else 0
        try:
            await call.message.edit_text(
                _emoji_panel_text(page),
                reply_markup=_emoji_panel_kb(page),
                parse_mode="HTML",
            )
        except Exception:
            await call.message.answer(
                _emoji_panel_text(page),
                reply_markup=_emoji_panel_kb(page),
                parse_mode="HTML",
            )
        return await call.answer()

    # ─── تم‌های تاس ─────────────────────────────────────────────────────────
    if action == "theme:back":
        name = call.from_user.first_name or "سازنده"
        try:
            await call.message.edit_text(
                _creator_panel_text(name),
                reply_markup=_creator_panel_kb(),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            await call.message.answer(
                _creator_panel_text(name),
                reply_markup=_creator_panel_kb(),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        return await call.answer()

    if action.startswith("theme:item:"):
        parts = action.split(":")
        tid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        try:
            await call.message.edit_text(
                _theme_item_text(tid, page),
                reply_markup=_theme_item_kb(tid, page),
                parse_mode="HTML",
            )
        except Exception:
            await call.message.answer(
                _theme_item_text(tid, page),
                reply_markup=_theme_item_kb(tid, page),
                parse_mode="HTML",
            )
        return await call.answer()

    if action.startswith("theme:set:"):
        # theme:set:4:single_header:0
        parts = action.split(":")
        tid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        field = parts[3] if len(parts) > 3 else ""
        page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
        if not tid or not field:
            return await call.answer("نامعتبر", show_alert=True)
        from bot.dice_themes import FIELD_LABELS, get_field_value
        from html import escape
        _CREATOR_STATE[call.from_user.id] = f"await_theme:{tid}:{field}:{page}"
        cur = escape(get_field_value(tid, field) or "")
        await call.message.answer(
            f"✏️ <b>ویرایش تم {tid}</b> — {FIELD_LABELS.get(field, field)}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{_theme_field_hint(field)}\n\n"
            f"مقدار فعلی:\n<code>{cur}</code>\n\n"
            "لغو: /start",
            parse_mode="HTML",
        )
        return await call.answer("منتظر متن…")

    if action.startswith("theme:prev:"):
        parts = action.split(":")
        tid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        from bot.dice_themes import preview_theme
        await call.message.answer(
            preview_theme(tid),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [Btn(text="🔙 بازگشت به تم", callback_data=f"cr:theme:item:{tid}:{page}")],
            ]),
        )
        return await call.answer("پیش‌نمایش")

    if action.startswith("theme:reset:"):
        parts = action.split(":")
        tid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        if not tid:
            return await call.answer("نامعتبر", show_alert=True)
        await db_reset_dice_theme(tid)
        try:
            await call.message.edit_text(
                _theme_item_text(tid, page) + "\n\n♻️ به پیش‌فرض برگشت.",
                reply_markup=_theme_item_kb(tid, page),
                parse_mode="HTML",
            )
        except Exception:
            await call.message.answer(
                f"♻️ تم {tid} ریست شد.",
                reply_markup=_theme_item_kb(tid, page),
                parse_mode="HTML",
            )
        return await call.answer("ریست شد")

    if action.startswith("theme:new:"):
        page = int(action.split(":")[-1]) if action.split(":")[-1].isdigit() else 0
        data = await db_create_dice_theme()
        tid = data.get("_created_theme_id") or 16
        await call.message.answer(
            f"🆕 تم جدید <b>{tid}</b> ساخته شد.\n"
            "الان می‌توانی همه فیلدها را ویرایش کنی.\n"
            f"در گروه: <code>تاس تم {tid}</code>",
            parse_mode="HTML",
            reply_markup=_theme_item_kb(tid, page),
        )
        return await call.answer(f"تم {tid}")

    if action.startswith("theme:quickprev:"):
        page = int(action.split(":")[-1]) if action.split(":")[-1].isdigit() else 0
        from bot.dice_themes import themes_page, preview_theme
        ids = themes_page(page)
        if not ids:
            return await call.answer("تمی نیست", show_alert=True)
        await call.message.answer(preview_theme(ids[0]), parse_mode="HTML")
        return await call.answer("پیش‌نمایش")

    if action.startswith("theme:export:"):
        from html import escape
        from bot.dice_themes import export_themes_json, export_themes
        page_s = action.split(":")[-1]
        data = export_themes(include_builtins=False)
        n = len(data.get("dice_themes") or {})
        if not n:
            # اگر سفارشی نبود، builtins کامل
            js = export_themes_json(pretty=True, include_builtins=True)
            note = "هیچ override سفارشی نیست — خروجی = همه تم‌های فعلی (با رندر pe)."
        else:
            js = export_themes_json(pretty=True, include_builtins=False)
            note = f"{n} تم سفارشی/ویرایش‌شده"
        text = (
            f"📤 <b>اکسپورت تم تاس</b> — {note}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<pre>{escape(js[:3500])}</pre>"
        )
        await call.message.answer(text, parse_mode="HTML")
        return await call.answer("اکسپورت شد")

    if action.startswith("theme:import_do:"):
        parts = action.split(":")
        mode = parts[2] if len(parts) > 2 else "merge"
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        replace = mode == "replace"
        _CREATOR_STATE[call.from_user.id] = (
            f"await_theme_import_replace:{page}" if replace else f"await_theme_import:{page}"
        )
        mode_txt = "جایگزینی کامل" if replace else "ادغام"
        await call.message.answer(
            f"📥 <b>ایمپورت تم تاس</b> — {mode_txt}\n\n"
            "JSON اکسپورت را بفرست.\n\nلغو: /start",
            parse_mode="HTML",
        )
        return await call.answer("منتظر JSON…")

    if action.startswith("theme:import:"):
        page_s = action.split(":")[-1]
        page = int(page_s) if page_s.isdigit() else 0
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [Btn(text="➕ ادغام (Merge)", callback_data=f"cr:theme:import_do:merge:{page}")],
            [Btn(text="♻️ جایگزینی کامل", callback_data=f"cr:theme:import_do:replace:{page}")],
            [Btn(text="🔙 بازگشت", callback_data=f"cr:theme:{page}")],
        ])
        await call.message.answer(
            "📥 <b>ایمپورت تم‌های تاس</b>\n\n"
            "• <b>ادغام</b>: روی تم‌های فعلی می‌نشیند\n"
            "• <b>جایگزینی</b>: همه overrideها پاک و از نو نوشته می‌شوند",
            reply_markup=kb,
            parse_mode="HTML",
        )
        return await call.answer()

    if action.startswith("theme:"):
        page_s = action.split(":", 1)[1]
        page = int(page_s) if page_s.isdigit() else 0
        try:
            await call.message.edit_text(
                _theme_panel_text(page),
                reply_markup=_theme_panel_kb(page),
                parse_mode="HTML",
            )
        except Exception:
            await call.message.answer(
                _theme_panel_text(page),
                reply_markup=_theme_panel_kb(page),
                parse_mode="HTML",
            )
        return await call.answer()

    # ─── بکاپ / بازیابی ─────────────────────────────────────────────────────
    if action == "backup:now":
        await call.answer("در حال ساخت دامپ…")
        await call.message.answer("⏳ در حال ساخت بکاپ دیتابیس… لطفاً صبر کنید.", parse_mode="HTML")
        from bot.backup import send_dump_to_owner
        ok, msg = await send_dump_to_owner(bot, reason="manual", chat_id=call.from_user.id)
        if not ok:
            await call.message.answer(msg, parse_mode="HTML")
        return

    if action == "backup:restore":
        _CREATOR_STATE[call.from_user.id] = "await_backup_file"
        await call.message.answer(
            "♻️ <b>بازیابی دیتابیس</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "فایل دامپ را همین‌جا بفرست:\n"
            "• <code>.dump</code> (پیشنهادی)\n"
            "• <code>.sql</code> یا <code>.sql.gz</code>\n\n"
            "⚠️ بازیابی داده‌های فعلی را با فایل دامپ جایگزین می‌کند.\n"
            "لغو: /start",
            parse_mode="HTML",
        )
        return await call.answer("منتظر فایل…")

    if action == "backup:confirm_yes":
        from bot.backup import PENDING_RESTORE, restore_dump, format_size
        path = PENDING_RESTORE.pop(call.from_user.id, None)
        _CREATOR_STATE.pop(call.from_user.id, None)
        if not path:
            return await call.answer("فایلی در صف نیست", show_alert=True)
        await call.answer("در حال بازیابی…")
        await call.message.answer(
            f"⏳ بازیابی از <code>{path.name}</code> ({format_size(path)})…\n"
            "ممکن است چند دقیقه طول بکشد.",
            parse_mode="HTML",
        )
        ok, msg = await restore_dump(path)
        await call.message.answer(msg, parse_mode="HTML")
        if ok:
            await load_all_caches()
            await call.message.answer(
                "♻️ کش‌ها دوباره بارگذاری شدند.\n"
                "✅ دیتابیس آماده استفاده است.",
                parse_mode="HTML",
            )
        return

    if action == "backup:confirm_no":
        from bot.backup import PENDING_RESTORE
        PENDING_RESTORE.pop(call.from_user.id, None)
        _CREATOR_STATE.pop(call.from_user.id, None)
        await call.message.answer("❌ بازیابی لغو شد.", parse_mode="HTML")
        return await call.answer("لغو شد")

    await call.answer()


# ─── تنظیم جوین اجباری (فقط سازنده) ─────────────────────────────────────────

async def _setup_channel(bot: Bot, channel_id: int) -> tuple[bool, str]:
    ok, err = await verify_bot_channel_access(bot, channel_id)
    if not ok:
        return False, err
    try:
        chat = await bot.get_chat(channel_id)
    except Exception as e:
        return False, f"کانال یافت نشد: {e}"
    invite = await resolve_channel_invite_link(bot, channel_id, chat.username)
    if not invite:
        return False, "لینک دعوت ساخته نشد. کانال باید عمومی باشد یا ربات دسترسی دعوت داشته باشد."
    await db_save_forced_join_channel(
        channel_id=channel_id,
        title=chat.title or "",
        username=chat.username or "",
        invite_link=invite,
        enabled=True,
    )
    uname = f"@{chat.username}" if chat.username else "—"
    return True, (
        "✅ <b>کانال اجباری تنظیم شد</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📣 <b>{chat.title}</b>\n"
        f"🔗 {uname}\n"
        "\n"
        "🟢 جوین اجباری فعال شد.\n"
        "کاربران بدون عضویت در پیوی خدمات دریافت نمی‌کنند."
    )


@router.message(F.text.regexp(r"^تنظیم کانال اجباری\s+(-?\d+)\s*$"))
async def cmd_set_forced_channel(message: Message, bot: Bot):
    if not is_creator(message.from_user.id):
        return
    _CREATOR_STATE.pop(message.from_user.id, None)
    channel_id = int(message.text.split()[-1])
    ok, text = await _setup_channel(bot, channel_id)
    await message.answer(text, parse_mode="HTML")


@router.message(F.text.regexp(r"^-100\d{6,}$"))
async def cmd_set_forced_channel_by_state(message: Message, bot: Bot):
    if not is_creator(message.from_user.id):
        return
    if _CREATOR_STATE.get(message.from_user.id) != "await_channel_id":
        return
    _CREATOR_STATE.pop(message.from_user.id, None)
    channel_id = int(message.text.strip())
    ok, text = await _setup_channel(bot, channel_id)
    await message.answer(text, parse_mode="HTML")


@router.message(F.forward_from_chat)
async def cmd_set_channel_forward(message: Message, bot: Bot):
    if not is_creator(message.from_user.id):
        return
    _CREATOR_STATE.pop(message.from_user.id, None)
    ch = message.forward_from_chat
    if not ch or ch.type != "channel":
        return await message.answer("⚠️ فقط پیام فوروارد‌شده از <b>کانال</b> قابل قبول است.", parse_mode="HTML")
    ok, text = await _setup_channel(bot, ch.id)
    await message.answer(text, parse_mode="HTML")


@router.message(F.text.in_([
    "جوین اجباری روشن", "فعال کردن جوین اجباری",
]))
async def cmd_join_on(message: Message):
    if not is_creator(message.from_user.id):
        return
    from bot import cache
    if not cache.FORCED_JOIN.get("channel_id"):
        return await message.answer(
            "❌ ابتدا کانال را تنظیم کنید:\n"
            "<code>تنظیم کانال اجباری -1001234567890</code>",
            parse_mode="HTML",
        )
    await db_set_forced_join_enabled(True)
    await message.answer("🟢 جوین اجباری <b>فعال</b> شد.", parse_mode="HTML")


@router.message(F.text.in_([
    "جوین اجباری خاموش", "غیرفعال کردن جوین اجباری",
]))
async def cmd_join_off(message: Message):
    if not is_creator(message.from_user.id):
        return
    await db_set_forced_join_enabled(False)
    await message.answer("⚫ جوین اجباری <b>غیرفعال</b> شد.", parse_mode="HTML")


@router.message(F.text.in_([
    "وضعیت جوین اجباری", "جوین اجباری",
]))
async def cmd_join_status(message: Message):
    if not is_creator(message.from_user.id):
        return
    await message.answer(creator_status_text(), parse_mode="HTML")


@router.message(F.text.in_([
    "حذف کانال اجباری", "پاک کردن کانال اجباری",
]))
async def cmd_join_clear(message: Message):
    if not is_creator(message.from_user.id):
        return
    await db_clear_forced_join()
    await message.answer(
        "🗑 کانال اجباری حذف شد و سیستم جوین غیرفعال شد.",
        parse_mode="HTML",
    )


def _parse_url_and_title(raw: str) -> tuple[str, str | None]:
    text = raw.strip()
    title = None
    if "|" in text:
        url_part, title_part = text.split("|", 1)
        text = url_part.strip()
        title = title_part.strip() or None
    if text.startswith("t.me/"):
        text = "https://" + text
    elif text.startswith("@"):
        text = f"https://t.me/{text[1:]}"
    return text, title


@router.message(F.text.in_(["وضعیت لینکدونی", "لینکدونی"]))
async def cmd_link_directory_status(message: Message):
    if not is_creator(message.from_user.id):
        return
    await message.answer(site_config_status_text(), parse_mode="HTML", disable_web_page_preview=True)


@router.message(F.text.regexp(r"^(تنظیم لینکدونی|لینک لینکدونی)\s+.+$"))
async def cmd_set_link_directory(message: Message):
    if not is_creator(message.from_user.id):
        return
    _CREATOR_STATE.pop(message.from_user.id, None)
    payload = message.text.split(None, 1)[1].strip()
    url, title = _parse_url_and_title(payload)
    if not url.startswith("http"):
        return await message.answer("❌ لینک معتبر نیست. با https:// شروع شود.")
    data = await db_set_link_directory(url, title)
    await message.answer(
        "✅ لینکدونی ذخیره شد.\n\n"
        f"🔗 <code>{data['link_directory_url']}</code>\n"
        f"📝 {data['link_directory_title']}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(F.text.regexp(r"^(تنظیم پشتیبانی|لینک پشتیبانی)\s+.+$"))
async def cmd_set_support(message: Message):
    if not is_creator(message.from_user.id):
        return
    _CREATOR_STATE.pop(message.from_user.id, None)
    payload = message.text.split(None, 1)[1].strip()
    url, title = _parse_url_and_title(payload)
    if not url.startswith("http"):
        return await message.answer("❌ لینک معتبر نیست. با https:// شروع شود.")
    data = await db_set_support_url(url, title)
    await message.answer(
        "✅ لینک پشتیبانی ذخیره شد.\n\n"
        f"💬 <code>{data['support_url']}</code>\n"
        f"📝 {data['support_title']}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(F.text.regexp(r"^(https?://\S+|t\.me/\S+|@\w+)(\s*\|\s*.+)?$"))
async def cmd_creator_await_url(message: Message):
    if not is_creator(message.from_user.id):
        return
    state = _CREATOR_STATE.get(message.from_user.id)
    if state not in ("await_link_directory", "await_support_url"):
        return
    _CREATOR_STATE.pop(message.from_user.id, None)
    url, title = _parse_url_and_title(message.text)
    if not url.startswith("http"):
        return await message.answer("❌ لینک معتبر نیست.")
    if state == "await_link_directory":
        data = await db_set_link_directory(url, title)
        return await message.answer(
            "✅ لینکدونی ذخیره شد.\n\n"
            f"🔗 <code>{data['link_directory_url']}</code>\n"
            f"📝 {data['link_directory_title']}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    data = await db_set_support_url(url, title)
    await message.answer(
        "✅ لینک پشتیبانی ذخیره شد.\n\n"
        f"💬 <code>{data['support_url']}</code>\n"
        f"📝 {data['support_title']}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ─── بکاپ / بازیابی (فقط سازنده) ────────────────────────────────────────────

@router.message(Command("backup", "dump"))
@router.message(F.text.in_([
    "بکاپ", "دامپ", "بکاپ بگیر", "دامپ بگیر",
]))
async def cmd_manual_backup(message: Message, bot: Bot):
    if not is_creator(message.from_user.id):
        return
    await message.answer("⏳ در حال ساخت بکاپ دیتابیس…", parse_mode="HTML")
    from bot.backup import send_dump_to_owner
    ok, msg = await send_dump_to_owner(bot, reason="manual", chat_id=message.from_user.id)
    if not ok:
        await message.answer(msg, parse_mode="HTML")


@router.message(Command("restore"))
@router.message(F.text.in_([
    "بازیابی", "ریستور", "restore",
]))
async def cmd_restore_start(message: Message):
    if not is_creator(message.from_user.id):
        return
    _CREATOR_STATE[message.from_user.id] = "await_backup_file"
    await message.answer(
        "♻️ <b>بازیابی دیتابیس</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "فایل دامپ (<code>.dump</code> / <code>.sql</code> / <code>.sql.gz</code>) را بفرست.\n\n"
        "⚠️ داده‌های فعلی جایگزین می‌شوند.\n"
        "لغو: /start",
        parse_mode="HTML",
    )


@router.message(F.document, F.func(lambda m: bool(m.from_user) and is_creator(m.from_user.id)))
async def cmd_creator_backup_document(message: Message, bot: Bot):
    """دریافت فایل دامپ برای بازیابی."""
    from bot.backup import (
        is_backup_document, save_incoming_document, PENDING_RESTORE, format_size,
    )

    doc = message.document
    if not doc:
        return

    state = _CREATOR_STATE.get(message.from_user.id) or ""
    waiting = state == "await_backup_file"
    looks_like = is_backup_document(doc.file_name)

    if not waiting and not looks_like:
        return
    if not waiting and looks_like:
        _CREATOR_STATE[message.from_user.id] = "await_backup_file"

    if doc.file_size and doc.file_size > 49 * 1024 * 1024:
        return await message.answer(
            "❌ حجم فایل بیش از حد مجاز تلگرام برای ربات است (≈۵۰MB).",
            parse_mode="HTML",
        )

    await message.answer("⬇️ در حال دانلود فایل دامپ…", parse_mode="HTML")
    try:
        path = await save_incoming_document(bot, doc, doc.file_name)
    except Exception as e:
        _CREATOR_STATE.pop(message.from_user.id, None)
        return await message.answer(f"❌ دانلود ناموفق: {e}", parse_mode="HTML")

    PENDING_RESTORE[message.from_user.id] = path
    _CREATOR_STATE[message.from_user.id] = "await_restore_confirm"
    await message.answer(
        "⚠️ <b>تأیید بازیابی</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📁 <code>{path.name}</code>\n"
        f"📦 حجم: <b>{format_size(path)}</b>\n\n"
        "این کار دیتابیس فعلی را با این دامپ جایگزین می‌کند.\n"
        "مطمئنی؟",
        reply_markup=_backup_confirm_kb(),
        parse_mode="HTML",
    )
