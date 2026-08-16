"""
هندلرهای پیوی ربات تاسینو
"""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton as Btn,
    ReplyKeyboardMarkup, KeyboardButton,
)

from bot import cache
from bot.cache_manager import load_all_caches, is_owner, is_admin
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
    db_set_forced_join_schedule,
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
_INCREASE_ADMIN_MESSAGE: dict[int, int] = {}


def _welcome_kb(bot_username: str, *, creator: bool = False) -> InlineKeyboardMarkup:
    add_url = f"https://t.me/{bot_username}?startgroup=true"
    rows = [
        [
            Btn(text="➕ افزودن ربات به گروه ↗️", url=add_url),
            Btn(text="🎲 تنظیمات گروه", callback_data="pv:group_settings"),
        ],
        [Btn(text="💰 پنل مالی گروه", callback_data="pv:finance")],
        [Btn(text=get_link_directory_title(), url=get_link_directory_url())],
        [Btn(text="📚 راهنمای ربات", callback_data="pv:help")],
    ]
    if creator:
        rows.append([Btn(text="👑 ورود به پنل ادمین", callback_data="cr:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _creator_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="👑 ورود به پنل ادمین")]],
        resize_keyboard=True,
        is_persistent=True,
    )


def _clip_tg(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit("\n", 1)[0]
    return cut + "\n…"


def _creator_panel_kb() -> InlineKeyboardMarkup:
    from bot.site_config import is_admin_sensitive_hidden
    from bot.panel_ui import toggle_label

    sens_on = is_admin_sensitive_hidden()
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🏠 داشبورد ربات", callback_data="cr:dash")],
        [
            Btn(text="🕵️ گزارش چیت", callback_data="cr:cheat:7"),
            Btn(text="📈 پیشرفت اعضا", callback_data="cr:progress"),
        ],
        [
            Btn(text="🎮 بازی زنده", callback_data="cr:live"),
            Btn(text="👥 گروه‌ها", callback_data="cr:groups:0"),
        ],
        [
            Btn(text="💰 ثروتمندها", callback_data="cr:rich"),
            Btn(text="📥 مالی باز", callback_data="cr:wd"),
        ],
        [Btn(text="🔎 بررسی کاربر", callback_data="cr:watch")],
        [
            Btn(text="⚠️ اخطار / میوت", callback_data="cr:mod"),
            Btn(text="🎲 تاس ۲۴ساعت", callback_data="cr:act"),
        ],
        [Btn(text="📊 وضعیت جوین اجباری", callback_data="cr:fj:status")],
        [Btn(text="روشن · جوین", callback_data="cr:fj:on"), Btn(text="خاموش · جوین", callback_data="cr:fj:off")],
        [Btn(text="⏰ زمان‌بندی جوین سازنده", callback_data="cr:fj:schedule"), Btn(text="♻️ حذف زمان‌بندی", callback_data="cr:fj:schedule_clear")],
        [Btn(text="🗑 حذف کانال", callback_data="cr:fj:clear"), Btn(text="📥 ثبت با آیدی", callback_data="cr:fj:setid")],
        [Btn(text="🔗 ثبت جوین سازنده با لینک", callback_data="cr:fj:setlink")],
        [Btn(
            text=toggle_label(sens_on, "مخفی حساس از ادمین"),
            callback_data="cr:sens:toggle",
        )],
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
    from bot.site_config import is_admin_sensitive_hidden
    sens = "روشن" if is_admin_sensitive_hidden() else "خاموش"
    return (
        f"👑 سلام {name}\n\n"
        "به <b>پنل سازنده تاسینو</b> خوش آمدید.\n"
        "جوین اجباری، گزارش چیت، پیشرفت اعضا، بازی زنده، بکاپ و کش را از اینجا مدیریت کنید.\n\n"
        "دستورها: <code>/admin</code> · دکمه پایین صفحه · <code>/start</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ Forced Join: {'روشن' if is_forced_join_active() else 'خاموش'}\n"
        f"🔒 مخفی حساس از ادمین: <b>{sens}</b>\n"
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


def _admin_back_kb(*, cheat: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if cheat:
        rows.append([
            Btn(text="۷ روز", callback_data="cr:cheat:7"),
            Btn(text="۳۰ روز", callback_data="cr:cheat:30"),
        ])
    rows.append([Btn(text="🔙 پنل ادمین", callback_data="cr:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


async def _send_welcome(message: Message, bot: Bot | None = None, user=None, *, reply_kb: bool = False):
    user = user or message.from_user
    name = (user.first_name if user else None) or "کاربر"
    bot = bot or message.bot
    me = await bot.get_me()
    username = me.username or "TasinoBot"
    creator = is_creator(user.id if user else message.from_user.id)
    await message.answer(
        _welcome_text(name, username),
        reply_markup=_welcome_kb(username, creator=creator),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    if creator and reply_kb:
        await message.answer(
            "👑 دکمه پایین صفحه یا /admin → پنل ادمین",
            reply_markup=_creator_reply_kb(),
        )


async def _open_creator_panel(message: Message) -> None:
    if message.from_user:
        _CREATOR_STATE.pop(message.from_user.id, None)
    name = (message.from_user.first_name if message.from_user else None) or "سازنده"
    await message.answer(
        _creator_panel_text(name),
        reply_markup=_creator_panel_kb(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@sync_to_async
def _pv_join_ads_text() -> str | None:
    """لیست جوین پنل تبلیغات — فقط اگر لینک فعالی باشد."""
    from django.utils import timezone
    from bot_setting.models import JoinMessage

    now = timezone.localtime(timezone.now())
    messages = JoinMessage.objects.filter(is_active=True).order_by("priority", "-created_at")
    if not any((m.text or "").strip() and m.is_active_now(now) for m in messages):
        return None
    return JoinMessage.get_join_message()


@router.message(Command("admin"))
@router.message(F.text.in_({"ورود به پنل ادمین", "👑 ورود به پنل ادمین", "/admin"}))
async def cmd_admin_panel(message: Message):
    if not is_creator(message.from_user.id):
        return await message.answer("⛔️ این پنل فقط برای سازنده است.")
    return await _open_creator_panel(message)


@router.message(
    F.text,
    F.func(lambda m: bool(m.from_user) and is_creator(m.from_user.id) and _CREATOR_STATE.get(m.from_user.id) == "await_watch_uid"),
)
async def cmd_creator_watch_uid(message: Message):
    import re
    m = re.search(r"(\d{5,})", message.text or "")
    if not m:
        return await message.answer("❌ شناسه عددی معتبر بفرستید. نمونه: <code>8810788620</code>", parse_mode="HTML")
    _CREATOR_STATE.pop(message.from_user.id, None)
    from bot.creator_admin import build_user_watch
    text = await build_user_watch(int(m.group(1)))
    await message.answer(
        _clip_tg(text),
        reply_markup=_admin_back_kb(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(F.text == "Mahsa1383914")
async def cmd_creator_secret(message: Message):
    if not is_creator(message.from_user.id):
        return
    name = message.from_user.first_name or "سازنده"
    return await message.answer(_creator_panel_text(name), reply_markup=_creator_panel_kb(), parse_mode="HTML", disable_web_page_preview=True)


@router.message(CommandStart())
async def start(message: Message, bot: Bot):
    from bot.finance import save_telegram_user
    await save_telegram_user(message.from_user.id, message.chat.id)
    _CREATOR_STATE.pop(message.from_user.id, None)

    # وسط بازی پیوی: منوی اصلی نیاد — فقط یادآوری بازی
    try:
        from bot.pv_dice import get_active_pv_game, _remind_in_game, ensure_sweeper
        await ensure_sweeper(bot)
        game = get_active_pv_game(message.from_user.id)
        if game:
            await _remind_in_game(bot, message.from_user.id, game)
            return
    except Exception:
        pass

    if is_forced_join_active() and not is_creator(message.from_user.id):
        if not await is_user_channel_member(bot, message.from_user.id):
            return await message.answer(
                join_required_text(),
                reply_markup=join_required_keyboard(),
                parse_mode="HTML",
            )
    await _send_welcome(message, bot, reply_kb=True)
    try:
        join_text = await _pv_join_ads_text()
        if join_text:
            await message.answer(join_text, disable_web_page_preview=True)
    except Exception:
        pass


def _waiting_settle_amount(message: Message) -> bool:
    from bot.accounts_panel import is_waiting_settle_amount
    return bool(message.from_user and is_waiting_settle_amount(message.from_user.id))


def _waiting_user_admin(message: Message) -> bool:
    from bot.user_admin import is_waiting_user_admin
    return bool(message.from_user and is_waiting_user_admin(message.from_user.id))


def _in_active_pv_game_msg(message: Message) -> bool:
    if not message.from_user:
        return False
    try:
        from bot.pv_dice import is_in_active_pv_game
        return is_in_active_pv_game(message.from_user.id)
    except Exception:
        return False


@router.message(F.text, F.func(_in_active_pv_game_msg))
async def pv_dice_game_lock_text(message: Message, bot: Bot):
    """وسط بازی پیوی: همه متن‌ها (از جمله /start و منو) فقط داخل بازی."""
    from bot.pv_dice import handle_pv_game_text, ensure_sweeper
    await ensure_sweeper(bot)
    await handle_pv_game_text(message, bot)


@router.message(F.text, F.func(_waiting_user_admin))
async def pv_user_admin_amount_catch(message: Message, bot: Bot):
    from bot.user_admin import handle_user_admin_text
    await handle_user_admin_text(message, bot)


@router.message(F.text, F.func(_waiting_settle_amount))
async def pv_settle_amount_catch(message: Message, bot: Bot):
    """مبلغ تسویه دلخواه از پنل حساب‌ها در پیوی."""
    from bot.accounts_panel import handle_settle_amount_message
    await handle_settle_amount_message(message, bot)


def _waiting_increase_amount(message: Message) -> bool:
    from bot.hidden_increase import is_waiting_increase_amount
    return bool(message.from_user and is_waiting_increase_amount(message.from_user.id))


def _waiting_increase_request(message: Message) -> bool:
    from bot.hidden_increase import is_waiting_increase_request
    return bool(message.from_user and is_waiting_increase_request(message.from_user.id))


def _waiting_manual_increase(message: Message) -> bool:
    from bot.hidden_increase import is_waiting_manual_increase
    return bool(message.from_user and is_waiting_manual_increase(message.from_user.id))


def _waiting_withdrawal(message: Message) -> bool:
    from bot.withdrawal_flow import waiting
    return bool(message.from_user and waiting(message.from_user.id))


@router.message(F.text, F.func(_waiting_withdrawal))
async def pv_withdrawal_catch(message: Message, bot: Bot):
    from bot.withdrawal_flow import handle_text
    await handle_text(bot, message.from_user.id, message.text or "")


def _waiting_pv_search(message: Message) -> bool:
    from bot.pv_search import is_waiting_pv_search
    return bool(message.from_user and is_waiting_pv_search(message.from_user.id))


@router.message(F.text, F.func(_waiting_pv_search))
async def pv_search_amount_catch(message: Message, bot: Bot):
    from bot.pv_search import handle_pv_search_text
    await handle_pv_search_text(message, bot)


# دکمه‌های منو/فلو کاربر — وسط بازی پیوی مسدود (قبل از handlerهای مربوطه)
_PV_LOCK_CB_PREFIXES = (
    "h:", "pv:help", "pv:finance", "pv:group_settings",
    "pf:", "ch:", "gs:", "inc_flow:", "incme:", "pvs:",
)
_PV_LOCK_CB_EXACT_WD = frozenset({"wd:card", "wd:name", "wd:full", "wd:cancel", "wd:amount"})


def _is_pv_locked_callback(data: str) -> bool:
    d = data or ""
    if d in _PV_LOCK_CB_EXACT_WD:
        return True
    return any(d == p or d.startswith(p) for p in _PV_LOCK_CB_PREFIXES)


def _cb_locked_by_pv_game(call: CallbackQuery) -> bool:
    if not call.from_user or not _is_pv_locked_callback(call.data or ""):
        return False
    try:
        from bot.pv_dice import is_in_active_pv_game
        return is_in_active_pv_game(call.from_user.id)
    except Exception:
        return False


@router.callback_query(F.func(_cb_locked_by_pv_game))
async def cb_pv_game_lock_nav(call: CallbackQuery, bot: Bot):
    try:
        from bot.pv_dice import get_active_pv_game, _remind_in_game, ensure_sweeper
        await ensure_sweeper(bot)
        game = get_active_pv_game(call.from_user.id)
        if game:
            await call.answer("وسط بازی پیوی هستید.", show_alert=True)
            await _remind_in_game(bot, call.from_user.id, game)
            return
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("wd:"))
async def cb_withdrawal_flow(call: CallbackQuery, bot: Bot):
    data = call.data or ""
    if data in ("wd:card", "wd:name", "wd:full", "wd:cancel", "wd:amount"):
        from bot.pv_throttle import allow_action, allow_reply, action_bucket
        uid = call.from_user.id
        if not allow_action(uid, action_bucket(data)) or not allow_reply(uid):
            await call.answer()
            return
        from bot.withdrawal_flow import handle_callback
        if await handle_callback(call, bot):
            return
    if data.startswith("wd:approve:") or data.startswith("wd:reject:") or data.startswith("wd:receipt:") or data.startswith("wd:message:") or data.startswith("wd:refresh:") or data.startswith("wd:cards:"):
        await _handle_withdrawal_admin_action(call, bot)
        return
    await call.answer()


@router.callback_query(F.data.startswith("pvd:"))
async def cb_pv_dice(call: CallbackQuery, bot: Bot):
    from bot.pv_dice import handle_callback, ensure_sweeper
    await ensure_sweeper(bot)
    await handle_callback(call, bot)


@router.callback_query(F.data.startswith("pvc:"))
async def cb_admin_pv_chat(call: CallbackQuery, bot: Bot):
    from bot.pv_dice import handle_callback, ensure_sweeper
    await ensure_sweeper(bot)
    await handle_callback(call, bot)


@router.callback_query(F.data.startswith("inc_flow:"))
async def cb_increase_request_flow(call: CallbackQuery, bot: Bot):
    from bot.pv_throttle import allow_action, allow_reply, action_bucket
    uid = call.from_user.id
    data = call.data or ""
    if not allow_action(uid, action_bucket(data)) or not allow_reply(uid):
        await call.answer()
        return
    from bot.hidden_increase import handle_increase_request_callback
    await handle_increase_request_callback(call, bot)


@router.callback_query(F.data.regexp(r"^incme:[a-f0-9]+$"))
async def cb_member_increase_offer(call: CallbackQuery, bot: Bot):
    """دکمه افزایش پس از بازی پیوی — درخواست عضو برای ادمین."""
    from bot.pv_dice import resolve_member_offer
    from bot.hidden_increase import start_increase_request_flow
    from bot.pv_throttle import allow_action, allow_reply

    uid = call.from_user.id
    if not allow_action(uid, "incme") or not allow_reply(uid):
        await call.answer()
        return

    tok = (call.data or "").split(":", 1)[-1]
    data = resolve_member_offer(tok)
    if not data:
        return await call.answer("این دکمه منقضی شده است.", show_alert=True)
    if int(call.from_user.id) != int(data["user_id"]):
        return await call.answer("این دکمه فقط برای شماست.", show_alert=True)
    await call.answer()
    ok = await start_increase_request_flow(bot, call.from_user.id, int(data["group_id"]))
    if not ok:
        await call.message.answer(
            "⚠️ شروع درخواست ممکن نشد؛ یک‌بار ربات را /start کنید و دوباره بزنید.",
        )


async def _waiting_withdrawal_receipt(message: Message) -> bool:
    from bot.withdrawal_flow import has_receipt_wait
    return bool(message.from_user and has_receipt_wait(message.from_user.id))


@router.message((F.photo | F.document), F.func(_waiting_withdrawal_receipt))
async def pv_withdrawal_receipt(message: Message, bot: Bot):
    from asgiref.sync import sync_to_async
    from account.models import WithdrawalRequest
    from bot.withdrawal_flow import pop_receipt_wait

    request_id = pop_receipt_wait(message.from_user.id)
    if not request_id:
        return
    req = await sync_to_async(WithdrawalRequest.objects.filter(id=request_id).first)()
    if not req:
        return await message.answer("❌ درخواست پیدا نشد.")

    allowed = is_owner(req.telegram_chat_id, message.from_user.id) or is_admin(req.telegram_chat_id, message.from_user.id)
    if not allowed:
        try:
            member = await bot.get_chat_member(req.telegram_chat_id, message.from_user.id)
            allowed = member.status in ("administrator", "creator", "owner")
        except Exception:
            allowed = False
    if not allowed:
        return await message.answer("❌ فقط مالک و ادمین‌های ربات دسترسی دارند.")

    file_id, kind = "", ""
    if message.photo:
        file_id, kind = message.photo[-1].file_id, "photo"
    elif message.document:
        file_id, kind = message.document.file_id, "document"
    if not file_id:
        return await message.answer("⚠️ رسید باید به‌صورت عکس یا فایل باشد.")

    if req.status == "pending":
        await sync_to_async(WithdrawalRequest.objects.filter(id=req.id).update)(
            receipt_file_id=file_id,
        )
        return await message.answer(
            "✅ رسید ذخیره شد.\n"
            "برای انجام تسویه «✅ تأیید» را بزنید (ارسال رسید اجباری نیست)."
        )

    if req.status == "done":
        if getattr(req, "receipt_file_id", ""):
            return await message.answer("ℹ️ رسید این درخواست قبلاً ثبت شده است.")
        await sync_to_async(WithdrawalRequest.objects.filter(id=req.id).update)(
            receipt_file_id=file_id,
        )
        try:
            if kind == "photo":
                await bot.send_photo(req.telegram_user_id, file_id, caption="🧾 رسید پرداخت تسویه")
            else:
                await bot.send_document(req.telegram_user_id, file_id, caption="🧾 رسید پرداخت تسویه")
        except Exception:
            pass
        return await message.answer("✅ رسید برای کاربر ارسال شد.")

    return await message.answer("⚠️ این درخواست دیگر قابل دریافت رسید نیست.")


async def _handle_withdrawal_admin_action(call: CallbackQuery, bot: Bot):
    from asgiref.sync import sync_to_async
    from django.utils import timezone
    from account.models import WithdrawalRequest
    from bot.finance import approve_withdrawal_debit
    # decrease_wallet import removed — debit is atomic inside approve_withdrawal_debit
    from bot.wallet_helpers import notify_other_admins
    from bot.withdrawal_flow import (
        set_receipt_wait,
        set_admin_message_wait,
        format_withdrawal_admin_text,
        withdrawal_admin_keyboard,
        get_card_warning_for_request,
        get_user_card_history,
        format_user_cards_history,
    )

    action, request_id = call.data.split(":")[1], int(call.data.rsplit(":", 1)[-1])
    req = await sync_to_async(WithdrawalRequest.objects.filter(id=request_id).first)()
    if not req:
        return await call.answer("درخواست پیدا نشد.", show_alert=True)
    from bot.cache_manager import can_manage_group

    allowed = can_manage_group(req.telegram_chat_id, call.from_user.id)
    if not allowed:
        try:
            member = await bot.get_chat_member(req.telegram_chat_id, call.from_user.id)
            allowed = member.status in ("administrator", "creator", "owner")
        except Exception:
            allowed = False
    if not allowed:
        return await call.answer("فقط مالک و ادمین‌های ربات دسترسی دارند.", show_alert=True)

    if action == "cards":
        try:
            u = await bot.get_chat(req.telegram_user_id)
            user_name = (u.full_name or u.first_name or "").strip() or str(req.telegram_user_id)
        except Exception:
            user_name = str(req.telegram_user_id)
        cards = await get_user_card_history(req.telegram_chat_id, req.telegram_user_id)
        await call.answer()
        return await call.message.answer(
            format_user_cards_history(cards, user_name=user_name, html=True),
            parse_mode="HTML",
        )

    if action == "refresh":
        try:
            u = await bot.get_chat(req.telegram_user_id)
            user_name = (u.full_name or u.first_name or "").strip() or str(req.telegram_user_id)
        except Exception:
            user_name = str(req.telegram_user_id)
        from bot.finance import get_playable_balance
        try:
            _t, bal, _p = await get_playable_balance(req.telegram_chat_id, req.telegram_user_id)
        except Exception:
            bal = None
        card_warning = await get_card_warning_for_request(
            req.telegram_chat_id, req.telegram_user_id, req.card_number, req.card_name,
        )
        msg = format_withdrawal_admin_text(
            user_name=user_name,
            amount=int(req.amount),
            card=req.card_number,
            card_name=req.card_name,
            status=req.status,
            refreshed=True,
            balance=bal,
            settle_kind=getattr(req, "settle_kind", None) or None,
            card_warning=card_warning,
        )
        kb = withdrawal_admin_keyboard(req.id, status=req.status)
        from bot.withdrawal_flow import remember_wd_delivery, broadcast_wd_admin_update
        if call.message:
            remember_wd_delivery(req.id, call.message.chat.id, call.message.message_id)
        await broadcast_wd_admin_update(bot, req.id, msg, kb)
        return await call.answer("بروزرسانی شد ✅")

    if action == "receipt":
        if req.status not in ("pending", "done"):
            return await call.answer("این درخواست دیگر قابل دریافت رسید نیست.", show_alert=True)
        if req.status == "done" and (getattr(req, "receipt_file_id", "") or "").strip():
            return await call.answer("رسید این درخواست قبلاً ثبت شده است.", show_alert=True)
        set_receipt_wait(call.from_user.id, req.id)
        await call.answer()
        return await call.message.answer(
            "📎 رسید را به‌صورت عکس یا فایل ارسال کنید.\n"
            "ℹ️ ارسال رسید اختیاری است — می‌توانید مستقیم «✅ تأیید» هم بزنید."
        )

    if action == "message":
        set_admin_message_wait(call.from_user.id, req.id)
        await call.answer()
        return await call.message.answer("💬 پیام موردنظر برای کاربر را بفرستید. برای لغو: لغو")

    if req.status != "pending":
        return await call.answer("این درخواست قبلاً پردازش شده است.", show_alert=True)

    approver_name = call.from_user.full_name or str(call.from_user.id)
    try:
        u = await bot.get_chat(req.telegram_user_id)
        user_name = (u.full_name or u.first_name or "").strip() or str(req.telegram_user_id)
    except Exception:
        user_name = str(req.telegram_user_id)

    if action == "reject":
        await sync_to_async(WithdrawalRequest.objects.filter(id=req.id).update)(
            status="cancelled", approved_by=call.from_user.id,
        )
        try:
            await bot.send_message(req.telegram_user_id, "❌ درخواست تسویه شما توسط مدیر رد شد.")
        except Exception:
            pass
        from bot.finance import get_playable_balance
        try:
            _t, bal, _p = await get_playable_balance(req.telegram_chat_id, req.telegram_user_id)
        except Exception:
            bal = None
        card_warning = await get_card_warning_for_request(
            req.telegram_chat_id, req.telegram_user_id, req.card_number, req.card_name,
        )
        msg = format_withdrawal_admin_text(
            user_name=user_name,
            amount=int(req.amount),
            card=req.card_number,
            card_name=req.card_name,
            status="cancelled",
            refreshed=True,
            balance=bal,
            settle_kind=getattr(req, "settle_kind", None) or None,
            card_warning=card_warning,
        )
        kb = withdrawal_admin_keyboard(req.id, status="cancelled")
        from bot.withdrawal_flow import remember_wd_delivery, broadcast_wd_admin_update
        if call.message:
            remember_wd_delivery(req.id, call.message.chat.id, call.message.message_id)
        await broadcast_wd_admin_update(bot, req.id, msg, kb)
        return await call.answer("درخواست رد شد.")

    receipt_file_id = (getattr(req, "receipt_file_id", "") or "").strip()

    from bot.finance import approve_withdrawal_debit
    req, err, live_bal = await approve_withdrawal_debit(
        request_id,
        call.from_user.id,
        receipt_file_id=receipt_file_id or None,
    )
    if err == "missing" or not req:
        return await call.answer("این درخواست قبلاً پردازش شده است.", show_alert=True)
    if err == "insufficient":
        await call.answer("موجودی کافی نیست", show_alert=True)
        await call.message.answer(
            "⚠️ موجودی فعلی کاربر کمتر از مبلغ درخواست است.\n"
            f"💰 موجودی: {int(live_bal):,} واحد\n"
            f"💸 مبلغ درخواست: {int(req.amount):,} واحد\n\n"
            "ابتدا درخواست را لغو کنید یا موجودی را افزایش دهید.",
        )
        return True

    receipt_file_id = (getattr(req, "receipt_file_id", "") or "").strip()

    await call.answer("تسویه انجام شد.")
    try:
        u = await bot.get_chat(req.telegram_user_id)
        user_name = (u.full_name or u.first_name or "").strip() or str(req.telegram_user_id)
    except Exception:
        user_name = str(req.telegram_user_id)
    from bot.finance import get_playable_balance
    try:
        _t, bal, _p = await get_playable_balance(req.telegram_chat_id, req.telegram_user_id)
    except Exception:
        bal = None
    card_warning = await get_card_warning_for_request(
        req.telegram_chat_id, req.telegram_user_id, req.card_number, req.card_name,
    )
    fresh = format_withdrawal_admin_text(
        user_name=user_name,
        amount=int(req.amount),
        card=req.card_number,
        card_name=req.card_name,
        status="done",
        refreshed=True,
        balance=bal,
        settle_kind=getattr(req, "settle_kind", None) or None,
        card_warning=card_warning,
    )
    kb_done = withdrawal_admin_keyboard(req.id, status="done")
    from bot.withdrawal_flow import remember_wd_delivery, broadcast_wd_admin_update
    if call.message:
        remember_wd_delivery(req.id, call.message.chat.id, call.message.message_id)
    await broadcast_wd_admin_update(bot, req.id, fresh, kb_done)
    try:
        from bot.pv_dice import _store_member_offer, _pv_member_offer_kb
        tok = _store_member_offer(int(req.telegram_chat_id), int(req.telegram_user_id))
        await bot.send_message(
            req.telegram_user_id,
            f"✅ درخواست تسویه شما به مبلغ {req.amount:,} انجام شد.\n"
            f"🛡 مدیر تأییدکننده: {approver_name}",
            reply_markup=_pv_member_offer_kb(tok),
        )
        if receipt_file_id:
            try:
                await bot.send_photo(req.telegram_user_id, receipt_file_id, caption="🧾 رسید پرداخت تسویه")
            except Exception:
                try:
                    await bot.send_document(req.telegram_user_id, receipt_file_id, caption="🧾 رسید پرداخت تسویه")
                except Exception:
                    pass
    except Exception:
        pass
    group_text = (
        f"✅ درخواست تسویه کاربر «{user_name}» به مبلغ {req.amount:,} "
        f"توسط مدیر «{approver_name}» انجام شد."
    )
    await bot.send_message(req.telegram_chat_id, group_text)
    await notify_other_admins(
        bot,
        req.telegram_chat_id,
        call.from_user.id,
        f"📢 {approver_name} درخواست تسویه کاربر «{user_name}» به مبلغ {req.amount:,} را تأیید کرد.",
    )
    if not receipt_file_id:
        set_receipt_wait(call.from_user.id, req.id)
        await call.message.answer(
            "📎 برای ارسال رسید به کاربر (اختیاری) عکس یا فایل بفرستید."
        )


@router.message(F.text, F.func(_waiting_manual_increase))
async def pv_manual_increase_catch(message: Message, bot: Bot):
    from bot.hidden_increase import handle_manual_increase_amount_message
    await handle_manual_increase_amount_message(message, bot)


@router.message(F.text, F.func(_waiting_increase_request))
async def pv_increase_request_catch(message: Message, bot: Bot):
    from bot.hidden_increase import handle_increase_request_message
    await handle_increase_request_message(message, bot)


@router.message((F.photo | F.document), F.func(_waiting_increase_request))
async def pv_increase_request_receipt(message: Message, bot: Bot):
    from bot.hidden_increase import handle_increase_request_receipt
    await handle_increase_request_receipt(message, bot)


@router.callback_query(F.data.startswith("inc_req:approve:"))
async def cb_approve_increase_request(call: CallbackQuery, bot: Bot):
    from bot.hidden_increase import (
        approve_increase_request,
        apply_increase_request_approval,
        get_increase_request,
        increase_request_manual_only_keyboard,
        format_increase_admin_text,
        remember_admin_delivery,
        broadcast_increase_admin_update,
    )

    request_id = int(call.data.rsplit(":", 1)[-1])
    req = await get_increase_request(request_id)
    if not req:
        return await call.answer("درخواست پیدا نشد.", show_alert=True)
    allowed = is_owner(req.telegram_chat_id, call.from_user.id) or is_admin(req.telegram_chat_id, call.from_user.id)
    if not allowed:
        try:
            member = await bot.get_chat_member(req.telegram_chat_id, call.from_user.id)
            allowed = member.status in ("administrator", "creator", "owner")
        except Exception:
            allowed = False
    if not allowed:
        return await call.answer("فقط مدیران گروه دسترسی دارند.", show_alert=True)
    req, approved = await approve_increase_request(request_id, call.from_user.id)
    if not approved:
        return await call.answer("این درخواست قبلاً تأیید یا منقضی شده است.", show_alert=True)
    await call.answer("درخواست تأیید شد.", show_alert=True)
    if call.message:
        remember_admin_delivery(req.id, call.message.chat.id, call.message.message_id)
    try:
        u = await bot.get_chat(req.telegram_user_id)
        user_name = (u.full_name or u.first_name or "").strip() or str(req.telegram_user_id)
    except Exception:
        user_name = str(req.telegram_user_id)
    msg = format_increase_admin_text(
        user_name=user_name,
        amount=int(req.amount),
        status="approved",
        refreshed=True,
    )
    kb = increase_request_manual_only_keyboard(req.id)
    await broadcast_increase_admin_update(bot, req.id, msg, kb)
    await apply_increase_request_approval(
        bot, req, call.from_user.id, req.amount, call.from_user.id,
    )


@router.callback_query(F.data.startswith("inc_req:refresh:"))
async def cb_refresh_increase_request(call: CallbackQuery, bot: Bot):
    from bot.hidden_increase import (
        get_increase_request,
        format_increase_admin_text,
        increase_request_admin_keyboard,
        remember_admin_delivery,
        broadcast_increase_admin_update,
    )

    request_id = int(call.data.rsplit(":", 1)[-1])
    req = await get_increase_request(request_id)
    if not req:
        return await call.answer("درخواست پیدا نشد.", show_alert=True)
    allowed = is_owner(req.telegram_chat_id, call.from_user.id) or is_admin(req.telegram_chat_id, call.from_user.id)
    if not allowed:
        try:
            member = await bot.get_chat_member(req.telegram_chat_id, call.from_user.id)
            allowed = member.status in ("administrator", "creator", "owner")
        except Exception:
            allowed = False
    if not allowed:
        return await call.answer("فقط مدیران گروه دسترسی دارند.", show_alert=True)
    try:
        u = await bot.get_chat(req.telegram_user_id)
        user_name = (u.full_name or u.first_name or "").strip() or str(req.telegram_user_id)
    except Exception:
        user_name = str(req.telegram_user_id)
    msg = format_increase_admin_text(
        user_name=user_name,
        amount=int(req.amount),
        status=req.status,
        refreshed=True,
    )
    kb = increase_request_admin_keyboard(req.id, status=req.status)
    if call.message:
        remember_admin_delivery(req.id, call.message.chat.id, call.message.message_id)
    await broadcast_increase_admin_update(bot, req.id, msg, kb)
    return await call.answer("بروزرسانی شد ✅")


@router.callback_query(F.data.startswith("inc_req:manual:"))
async def cb_manual_increase_request(call: CallbackQuery, bot: Bot):
    from bot.helpers import send_private
    from bot.hidden_increase import (
        get_increase_request,
        manual_increase_prompt,
        pop_manual_increase_wait,
        set_manual_increase_wait,
    )

    request_id = int(call.data.rsplit(":", 1)[-1])
    req = await get_increase_request(request_id)
    if not req:
        return await call.answer("درخواست پیدا نشد.", show_alert=True)
    allowed = is_owner(req.telegram_chat_id, call.from_user.id) or is_admin(req.telegram_chat_id, call.from_user.id)
    if not allowed:
        try:
            member = await bot.get_chat_member(req.telegram_chat_id, call.from_user.id)
            allowed = member.status in ("administrator", "creator", "owner")
        except Exception:
            allowed = False
    if not allowed:
        return await call.answer("فقط مدیران گروه دسترسی دارند.", show_alert=True)
    if req.status == "cancelled":
        return await call.answer("این درخواست رد شده و قابل افزایش نیست.", show_alert=True)
    if req.status != "pending":
        return await call.answer("بعد از تأیید، افزایش دستی ممکن نیست.", show_alert=True)

    set_manual_increase_wait(call.from_user.id, req.id)
    prompt = manual_increase_prompt(req, already_processed=False)
    ok = await send_private(bot, call.from_user.id, prompt)
    if ok:
        return await call.answer("مبلغ را در پیوی ربات بفرستید.")
    if call.message and call.message.chat and call.message.chat.type == "private":
        await call.message.answer(prompt)
        return await call.answer()
    pop_manual_increase_wait(call.from_user.id)
    return await call.answer(
        "ابتدا ربات را در پیوی استارت کنید تا افزایش دستی انجام شود.",
        show_alert=True,
    )


@router.callback_query(F.data.regexp(r"^inc_req:(reject|block|message):\d+$"))
async def cb_manage_increase_request(call: CallbackQuery, bot: Bot):
    from bot.hidden_increase import get_increase_request, reject_increase_request
    from bot.finance_ban import set_block_reason_wait
    action, request_id = call.data.split(":")[1:]
    req = await get_increase_request(int(request_id))
    if not req:
        return await call.answer("درخواست پیدا نشد.", show_alert=True)
    allowed = is_owner(req.telegram_chat_id, call.from_user.id) or is_admin(req.telegram_chat_id, call.from_user.id)
    if not allowed:
        try:
            member = await bot.get_chat_member(req.telegram_chat_id, call.from_user.id)
            allowed = member.status in ("administrator", "creator", "owner")
        except Exception:
            pass
    if not allowed:
        return await call.answer("فقط مدیران گروه دسترسی دارند.", show_alert=True)
    if action == "message":
        _INCREASE_ADMIN_MESSAGE[call.from_user.id] = req.id
        await call.answer()
        return await call.message.answer("💬 پیام موردنظر برای کاربر را بفرستید. برای لغو: لغو")
    if action == "block":
        if req.status != "pending":
            return await call.answer("این درخواست قبلاً پردازش یا منقضی شده است.", show_alert=True)
        set_block_reason_wait(call.from_user.id, req.id)
        await call.answer()
        return await call.message.answer(
            "🚫 دلیل بلاک مالی را بنویسید.\n"
            "مثال: ارسال رسید فیک\n\n"
            "برای انصراف: لغو"
        )
    if req.status != "pending":
        return await call.answer("این درخواست قبلاً پردازش یا منقضی شده است.", show_alert=True)
    req, changed = await reject_increase_request(req.id, call.from_user.id)
    if not changed:
        return await call.answer("این درخواست قبلاً پردازش شده است.", show_alert=True)
    user_text = "❌ درخواست افزایش موجودی شما توسط مدیر رد شد."
    try:
        await bot.send_message(req.telegram_user_id, user_text)
    except Exception:
        pass
    try:
        u = await bot.get_chat(req.telegram_user_id)
        user_name = (u.full_name or u.first_name or "").strip() or str(req.telegram_user_id)
    except Exception:
        user_name = str(req.telegram_user_id)
    from bot.hidden_increase import (
        format_increase_admin_text, increase_request_admin_keyboard,
        remember_admin_delivery, broadcast_increase_admin_update,
    )
    msg = format_increase_admin_text(
        user_name=user_name,
        amount=int(req.amount),
        status="cancelled",
        refreshed=True,
    )
    kb = increase_request_admin_keyboard(req.id, status="cancelled")
    if call.message:
        remember_admin_delivery(req.id, call.message.chat.id, call.message.message_id)
    await broadcast_increase_admin_update(bot, req.id, msg, kb)
    return await call.answer("درخواست پردازش شد.", show_alert=True)


def _waiting_increase_block_reason(message: Message) -> bool:
    from bot.finance_ban import is_waiting_block_reason
    return bool(message.from_user and is_waiting_block_reason(message.from_user.id))


@router.message(F.text, F.func(_waiting_increase_block_reason))
async def pv_increase_block_reason(message: Message, bot: Bot):
    from bot.finance_ban import (
        pop_block_reason_wait, set_block_reason_wait, ban_finance,
        format_group_finance_ban_announce, FINANCE_BAN_USER_TEXT,
    )
    from bot.hidden_increase import (
        get_increase_request, reject_increase_request,
        format_increase_admin_text, increase_request_admin_keyboard,
        broadcast_increase_admin_update,
    )

    request_id = pop_block_reason_wait(message.from_user.id)
    raw = (message.text or "").strip()
    if raw in ("لغو", "انصراف", "cancel"):
        return await message.answer("❌ بلاک لغو شد.")
    if len(raw) < 2:
        set_block_reason_wait(message.from_user.id, request_id)
        return await message.answer("⚠️ دلیل معتبر نیست. دوباره بنویسید یا «لغو» بزنید.")

    req = await get_increase_request(request_id)
    if not req:
        return await message.answer("❌ درخواست پیدا نشد.")
    if req.status != "pending":
        return await message.answer("⚠️ این درخواست قبلاً پردازش شده است.")

    req, changed = await reject_increase_request(req.id, message.from_user.id)
    if not changed:
        return await message.answer("⚠️ این درخواست قبلاً پردازش شده است.")

    ban = await ban_finance(req.telegram_chat_id, req.telegram_user_id, message.from_user.id, raw)
    try:
        await bot.send_message(
            req.telegram_user_id,
            f"{FINANCE_BAN_USER_TEXT}\n\n📝 دلیل: {ban['reason']}",
        )
    except Exception:
        pass

    user_name = ""
    try:
        u = await bot.get_chat(req.telegram_user_id)
        user_name = (u.full_name or u.first_name or "").strip() or str(req.telegram_user_id)
    except Exception:
        user_name = str(req.telegram_user_id)
    admin_name = (message.from_user.full_name or message.from_user.first_name or "").strip() or str(message.from_user.id)

    msg = format_increase_admin_text(
        user_name=user_name,
        amount=int(req.amount),
        status="cancelled",
        refreshed=True,
    )
    kb = increase_request_admin_keyboard(req.id, status="cancelled")
    await broadcast_increase_admin_update(bot, req.id, msg, kb)

    announce = format_group_finance_ban_announce(
        user_display=user_name,
        reason=ban["reason"],
        admin_display=admin_name,
    )
    try:
        await bot.send_message(req.telegram_chat_id, announce)
    except Exception:
        pass
    return await message.answer(
        f"✅ کاربر بلاک مالی شد.\n📝 دلیل: {ban['reason']}\n📢 در گروه اعلام شد."
    )


@router.message(F.text, F.func(lambda m: bool(m.from_user) and m.from_user.id in _INCREASE_ADMIN_MESSAGE))
async def pv_increase_admin_message(message: Message, bot: Bot):
    from bot.hidden_increase import get_increase_request
    request_id = _INCREASE_ADMIN_MESSAGE.pop(message.from_user.id, None)
    if (message.text or "").strip() in ("لغو", "انصراف", "cancel"):
        return await message.answer("❌ ارسال پیام لغو شد.")
    req = await get_increase_request(request_id)
    if not req:
        return await message.answer("❌ درخواست پیدا نشد.")
    try:
        await bot.send_message(req.telegram_user_id, f"💬 پیام مدیر درباره درخواست افزایش:\n\n{message.text}")
        return await message.answer("✅ پیام برای کاربر ارسال شد.")
    except Exception:
        return await message.answer("⚠️ ارسال پیام به کاربر ناموفق بود.")


def _waiting_wd_admin_message(message: Message) -> bool:
    from bot.withdrawal_flow import is_waiting_admin_message
    return bool(message.from_user and is_waiting_admin_message(message.from_user.id))


@router.message(F.text, F.func(_waiting_wd_admin_message))
async def pv_withdrawal_admin_message(message: Message, bot: Bot):
    from asgiref.sync import sync_to_async
    from account.models import WithdrawalRequest
    from bot.withdrawal_flow import pop_admin_message_wait

    request_id = pop_admin_message_wait(message.from_user.id)
    if (message.text or "").strip() in ("لغو", "انصراف", "cancel"):
        return await message.answer("❌ ارسال پیام لغو شد.")
    req = await sync_to_async(WithdrawalRequest.objects.filter(id=request_id).first)()
    if not req:
        return await message.answer("❌ درخواست پیدا نشد.")
    try:
        await bot.send_message(
            req.telegram_user_id,
            f"💬 پیام مدیر درباره درخواست تسویه:\n\n{message.text}",
        )
        return await message.answer("✅ پیام برای کاربر ارسال شد.")
    except Exception:
        return await message.answer("⚠️ ارسال پیام به کاربر ناموفق بود.")


def _waiting_challenge_input(message: Message) -> bool:
    from bot.challenge_panel import is_waiting_challenge_input
    return bool(message.from_user and is_waiting_challenge_input(message.from_user.id))


@router.message(F.text, F.func(_waiting_challenge_input))
async def pv_challenge_input(message: Message, bot: Bot):
    from bot.challenge_panel import handle_challenge_text
    await handle_challenge_text(message, bot)


def _waiting_share_percent(message: Message) -> bool:
    from bot.admin_accounting import is_waiting_share_percent
    return bool(message.from_user and is_waiting_share_percent(message.from_user.id))


@router.message(F.text, F.func(_waiting_share_percent))
async def pv_share_percent_catch(message: Message, bot: Bot):
    from bot.admin_accounting import handle_share_custom_text
    await handle_share_custom_text(message, bot)


@router.message(F.text, F.func(_waiting_increase_amount))
async def pv_increase_amount_catch(message: Message, bot: Bot):
    """مبلغ افزایش موجودی مخفی در پیوی."""
    from bot.hidden_increase import handle_increase_amount_message
    await handle_increase_amount_message(message, bot)


@router.message(F.text.in_(["استارت", "شروع", "start", "Start", "START"]))
async def msg_start_alias(message: Message, bot: Bot):
    from bot.finance import save_telegram_user
    await save_telegram_user(message.from_user.id, message.chat.id)
    try:
        from bot.pv_dice import get_active_pv_game, _remind_in_game, ensure_sweeper
        await ensure_sweeper(bot)
        game = get_active_pv_game(message.from_user.id)
        if game:
            await _remind_in_game(bot, message.from_user.id, game)
            return
    except Exception:
        pass
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


@router.callback_query(F.data == "pv:finance")
async def cb_pv_finance(call: CallbackQuery, bot: Bot):
    await call.answer()
    from bot.pv_finance_panel import prompt_group_id
    await prompt_group_id(bot, call.from_user.id)


@router.callback_query(F.data.startswith("pf:"))
async def cb_pv_finance_panel(call: CallbackQuery, bot: Bot):
    from bot.pv_finance_panel import handle_finance_panel_callback, set_finance_group, get_finance_group
    from bot import cache as bot_cache
    from bot.panel_ui import can_see_fee, can_see_sensitive_finance
    from bot.cache_manager import is_owner, is_admin
    from bot.constants import CREATOR_USER_ID

    uid = call.from_user.id
    chat = call.message.chat if call.message else None
    group_id = get_finance_group(uid) or bot_cache.PV_PANEL_GROUP.get(uid)
    if chat and getattr(chat, "type", "") in ("group", "supergroup"):
        group_id = chat.id
        set_finance_group(uid, group_id)
    elif group_id:
        set_finance_group(uid, group_id)

    data = call.data or ""
    if group_id and data in ("pf:oa", "pf:oy", "pf:oc", "pf:of"):
        owner = is_owner(group_id, uid) or uid == CREATOR_USER_ID
        from asgiref.sync import sync_to_async
        @sync_to_async
        def _fee_hid(cid):
            from account.models import TelegramGroup
            return bool(TelegramGroup.objects.filter(telegram_chat_id=cid).values_list("fee_hidden", flat=True).first())
        @sync_to_async
        def _pv_fin(cid):
            from account.models import TelegramGroup
            return bool(TelegramGroup.objects.filter(telegram_chat_id=cid).values_list("pv_admin_finance_enabled", flat=True).first())
        fee_hid = await _fee_hid(group_id)
        if data == "pf:of" and not can_see_fee(uid, group_id, is_owner_flag=owner, fee_hidden=fee_hid):
            return await call.answer("حق واسطه مخفی است.", show_alert=True)
        see_sens = can_see_sensitive_finance(uid, group_id, is_owner_flag=owner)
        pv_ok = owner or (is_admin(group_id, uid) and await _pv_fin(group_id) and see_sens)
        if data in ("pf:oa", "pf:oy", "pf:oc") and not (see_sens and pv_ok):
            return await call.answer("این بخش در دسترس نیست.", show_alert=True)

    await handle_finance_panel_callback(call, bot)


@router.callback_query(F.data.startswith("ch:"))
async def cb_challenge_panel(call: CallbackQuery, bot: Bot):
    from bot.challenge_panel import handle_challenge_callback
    await handle_challenge_callback(call, bot)


@router.message(
    F.text.regexp(r"^(?:شناسه\s*(?:گروه|گپ)?|گروه|group|chat[\s_]?id|id)\s*:?\s*-?\d{6,}$")
    | F.text.regexp(r"^-\d{6,}$")
)
async def pv_group_id_finance(message: Message, bot: Bot):
    """ارسال شناسه گروه در پیوی → پنل مالی."""
    # کانال اجباری سازنده اولویت دارد
    if is_creator(message.from_user.id) and _CREATOR_STATE.get(message.from_user.id) == "await_channel_id":
        return
    from bot.pv_finance_panel import handle_group_id_message
    await handle_group_id_message(message, bot)


@router.message(F.text.in_(["جستجو", "جستجوی حریف", "جستجو حریف"]))
async def pv_search_start(message: Message, bot: Bot):
    from bot.pv_search import start_pv_search
    await start_pv_search(bot, message.from_user.id, message=message)


def _pv_search_cancel_text(message: Message) -> bool:
    """لغو جستجو — حتی وقتی سشن حافظه رفته و فقط قفل یتیم مانده."""
    from bot.pv_search import _cancel_words, is_waiting_pv_search
    from bot.pv_dice import user_busy

    if not message.from_user or not _cancel_words(message.text or ""):
        return False
    uid = message.from_user.id
    # سشن فعال را همان هندلر فلو جستجو جمع می‌کند
    if is_waiting_pv_search(uid):
        return False
    busy = user_busy(uid)
    return bool(busy and busy[0] == "search")


@router.message(F.text, F.func(_pv_search_cancel_text))
async def pv_search_force_cancel(message: Message, bot: Bot):
    from bot.pv_search import try_cancel_pv_search_command
    await try_cancel_pv_search_command(bot, message.from_user.id, message=message)


_LEAGUE_PV_CMDS = (
    "لیگ من", "لیگمن",
    "لیگ", "لیگ برترها", "جدول لیگ", "برترین لیگ",
    "رتبه بندی", "رتبه‌بندی", "رتبه بندی لیگ", "رتبه‌بندی لیگ",
    "لیگ رتبه", "لیگ رتبه‌بندی",
    "لیگ راهنما", "راهنما لیگ",
)


@router.message(
    F.text.in_(_LEAGUE_PV_CMDS)
    | F.text.regexp(r"^(?:لیگ|رتبه[\u200c ]?بندی(?:\s+لیگ)?|لیگ\s+رتبه(?:[\u200c ]?بندی)?|لیگ\s+برترها|جدول\s+لیگ|برترین\s+لیگ)\s+\d+$")
)
async def pv_league_cmds(message: Message, bot: Bot):
    from bot.league import handle_league_pv_command
    await handle_league_pv_command(bot, message.from_user.id, message.text or "", message=message)


@router.callback_query(F.data.startswith("lg:") | F.data.startswith("lgb:"))
async def cb_league_pv(call: CallbackQuery, bot: Bot):
    from bot.league import handle_league_pv_callback
    await handle_league_pv_callback(call, bot)


@router.message(F.text.regexp(r"^(?:کاربر|شناسه\s*کاربر|مدیریت\s*کاربر)\s+\d{5,}$"))
async def pv_user_admin_cmd(message: Message, bot: Bot):
    from bot.user_admin import parse_user_admin_command, start_user_admin
    tid = parse_user_admin_command(message.text or "")
    if not tid:
        return
    await start_user_admin(bot, message.from_user.id, tid, message=message)


@router.callback_query(F.data.startswith("ua:"))
async def cb_user_admin(call: CallbackQuery, bot: Bot):
    from bot.user_admin import handle_user_admin_callback
    await handle_user_admin_callback(call, bot)


@router.callback_query(F.data.startswith("pvs:"))
async def cb_pv_search(call: CallbackQuery, bot: Bot):
    from bot.pv_search import handle_pv_search_callback
    await handle_pv_search_callback(call, bot)


@router.message(F.text.in_([
    "افزایش", "افزایش موجودی", "درخواست افزایش", "درخواست افزایش موجودی",
    "تسویه", "تسویه حساب", "درخواست تسویه", "درخواست تسویه حساب",
]))
async def pv_member_increase_settle(message: Message, bot: Bot):
    """در پیوی: انتخاب گپ سپس ادامه درخواست افزایش/تسویه."""
    from bot.pv_finance_panel import try_handle_member_request_text
    from bot.pv_throttle import allow_action, allow_reply

    uid = message.from_user.id
    if not allow_action(uid, "finance_text") or not allow_reply(uid):
        return
    await try_handle_member_request_text(bot, message.from_user.id, message.text or "")


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

    async def _send_report(text: str, markup=None):
        markup = markup or _admin_back_kb()
        text = _clip_tg(text)
        try:
            await call.message.edit_text(
                text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True,
            )
        except Exception:
            await call.message.answer(
                text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True,
            )

    if action == "open":
        _CREATOR_STATE.pop(call.from_user.id, None)
        name = call.from_user.first_name or "سازنده"
        await _send_report(_creator_panel_text(name), _creator_panel_kb())
        return await call.answer()

    if action == "dash":
        from bot.creator_admin import build_dashboard
        await _send_report(await build_dashboard())
        return await call.answer()

    if action.startswith("cheat:"):
        from bot.creator_admin import build_cheat_report
        days = 30 if action.endswith(":30") else 7
        await _send_report(await build_cheat_report(days), _admin_back_kb(cheat=True))
        return await call.answer()

    if action == "progress":
        from bot.creator_admin import build_progress_report
        await _send_report(await build_progress_report())
        return await call.answer()

    if action == "live":
        from bot.creator_admin import build_live_games
        await _send_report(build_live_games())
        return await call.answer()

    if action.startswith("groups:"):
        from bot.creator_admin import build_groups_page
        try:
            page = int(action.split(":")[1])
        except (IndexError, ValueError):
            page = 0
        text, page = await build_groups_page(page)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                Btn(text="◀️", callback_data=f"cr:groups:{max(0, page - 1)}"),
                Btn(text="▶️", callback_data=f"cr:groups:{page + 1}"),
            ],
            [Btn(text="🔙 پنل ادمین", callback_data="cr:open")],
        ])
        await _send_report(text, kb)
        return await call.answer()

    if action == "rich":
        from bot.creator_admin import build_rich_list
        await _send_report(await build_rich_list())
        return await call.answer()

    if action == "wd":
        from bot.creator_admin import build_open_finance
        await _send_report(await build_open_finance())
        return await call.answer()

    if action == "watch":
        _CREATOR_STATE[call.from_user.id] = "await_watch_uid"
        await call.message.answer(
            "🔎 شناسه عددی کاربر را بفرستید.\n"
            "نمونه: <code>8810788620</code>\n"
            "یا در گروه: <code>کاربر 8810788620</code>",
            parse_mode="HTML",
        )
        return await call.answer("منتظر آیدی…")

    if action == "mod":
        from bot.creator_admin import build_moderation_report
        await _send_report(await build_moderation_report())
        return await call.answer()

    if action == "act":
        from bot.creator_admin import build_activity_report
        await _send_report(await build_activity_report())
        return await call.answer()

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

    if action == "fj:schedule":
        if not cache.FORCED_JOIN.get("channel_id"):
            return await call.answer("ابتدا لینک/کانال جوین سازنده را تنظیم کنید.", show_alert=True)
        _CREATOR_STATE[call.from_user.id] = "await_forced_join_schedule"
        await call.message.answer(
            "شروع و پایان را با این قالب بفرستید:\n"
            "<code>2026-07-20 12:00 | 2026-07-25 23:30</code>\n\n"
            "زمان‌ها بر اساس Asia/Tehran هستند.", parse_mode="HTML",
        )
        return await call.answer("منتظر بازه زمانی...")

    if action == "fj:schedule_clear":
        await db_set_forced_join_schedule(None, None)
        await call.message.answer("♻️ زمان‌بندی حذف شد؛ وضعیت روشن/خاموش دستی اعمال می‌شود.")
        return await call.answer("حذف شد")

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

    if action == "fj:setlink":
        _CREATOR_STATE[call.from_user.id] = "await_channel_link"
        await call.message.answer("لینک عمومی کانال یا @username را بفرستید. ربات باید در کانال مقصد ادمین باشد.")
        return await call.answer("منتظر لینک...")

    if action == "sens:toggle":
        from bot.site_config import is_admin_sensitive_hidden, db_set_admin_sensitive_hidden
        new_state = not is_admin_sensitive_hidden()
        await db_set_admin_sensitive_hidden(new_state)
        name = call.from_user.first_name or "سازنده"
        try:
            await call.message.edit_text(
                _creator_panel_text(name),
                reply_markup=_creator_panel_kb(),
                parse_mode="HTML",
            )
        except Exception:
            await call.message.answer(
                _creator_panel_text(name),
                reply_markup=_creator_panel_kb(),
                parse_mode="HTML",
            )
        return await call.answer(
            "روشن شد — حساس‌ها از ادمین مخفی است" if new_state else "خاموش شد — ادمین‌ها دوباره می‌بینند"
        )

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
            "🕵️ گزارش چیت: میانگین تاس و درصد ۶ نسبت به شانس عادلانه.\n"
            "📈 پیشرفت اعضا / 🔎 بررسی کاربر با آیدی عددی.\n"
            "ورود: <code>/admin</code> یا دکمه پایین صفحه بعد از /start.\n\n"
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
    if action == "backup:interval":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [Btn(text="هر ۱ ساعت", callback_data="cr:backup:setinterval:1"), Btn(text="هر ۳ ساعت", callback_data="cr:backup:setinterval:3")],
            [Btn(text="هر ۶ ساعت", callback_data="cr:backup:setinterval:6")],
        ])
        await call.message.answer("فاصله بکاپ خودکار را انتخاب کنید:", reply_markup=kb)
        return await call.answer()

    if action.startswith("backup:setinterval:"):
        hours = int(action.rsplit(":", 1)[-1])
        from bot.backup_schedule import set_backup_interval
        if not set_backup_interval(hours):
            return await call.answer("زمان‌بندی هنوز آماده نیست؛ دوباره تلاش کنید.", show_alert=True)
        await call.message.answer(f"✅ بکاپ خودکار هر {hours} ساعت تنظیم شد.")
        return await call.answer()

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
    # اگر سازنده منتظر ثبت کانال اجباری است
    if is_creator(message.from_user.id) and _CREATOR_STATE.get(message.from_user.id) == "await_channel_id":
        _CREATOR_STATE.pop(message.from_user.id, None)
        channel_id = int(message.text.strip())
        ok, text = await _setup_channel(bot, channel_id)
        return await message.answer(text, parse_mode="HTML")

    # در غیر این صورت: شناسه گروه → پنل مالی
    from bot.pv_finance_panel import handle_group_id_message
    if await handle_group_id_message(message, bot):
        return


@router.message(F.text, F.func(lambda m: bool(m.from_user) and _CREATOR_STATE.get(m.from_user.id) == "await_forced_join_schedule"))
async def cmd_set_forced_join_schedule(message: Message):
    if not is_creator(message.from_user.id):
        return
    from datetime import datetime
    from django.utils import timezone
    try:
        left, right = [part.strip() for part in message.text.split("|", 1)]
        start = datetime.strptime(left, "%Y-%m-%d %H:%M")
        end = datetime.strptime(right, "%Y-%m-%d %H:%M")
        start = timezone.make_aware(start)
        end = timezone.make_aware(end)
        if end <= start:
            raise ValueError("پایان باید بعد از شروع باشد")
    except Exception as exc:
        return await message.answer(f"❌ قالب یا بازه نامعتبر است: {exc}\nنمونه: 2026-07-20 12:00 | 2026-07-25 23:30")
    _CREATOR_STATE.pop(message.from_user.id, None)
    await db_set_forced_join_schedule(start, end)
    await message.answer("✅ زمان‌بندی جوین اجباری سازنده ذخیره شد و فقط در همین بازه فعال خواهد بود.")


@router.message(F.text, F.func(lambda m: bool(m.from_user) and _CREATOR_STATE.get(m.from_user.id) == "await_channel_link"))
async def cmd_set_forced_channel_by_link(message: Message, bot: Bot):
    if not is_creator(message.from_user.id):
        return
    _CREATOR_STATE.pop(message.from_user.id, None)
    from bot.group_forced_join import resolve_target
    try:
        target = await resolve_target(bot, message.text)
        await db_save_forced_join_channel(
            target.channel_id, target.title, target.link.rsplit("/", 1)[-1], target.link, True,
        )
        await message.answer(f"✅ جوین اجباری سازنده تنظیم شد:\n<b>{target.title}</b>\n{target.link}", parse_mode="HTML")
    except Exception as exc:
        await message.answer(f"❌ تنظیم نشد: {exc}")


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
