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
        [Btn(text="🧠 وضعیت کش", callback_data="cr:cache:stats"), Btn(text="♻️ ریلود کش", callback_data="cr:cache:reload")],
        [Btn(text="🤖 اطلاعات ربات", callback_data="cr:bot:info"), Btn(text="📘 راهنمای سریع", callback_data="cr:help")],
    ])


def _creator_panel_text(name: str) -> str:
    return (
        f"👑 سلام {name}\n\n"
        "به <b>پنل سازنده تاسینو</b> خوش آمدید.\n"
        "جوین اجباری، لینکدونی، کش و تنظیمات کلیدی را از اینجا مدیریت کنید.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ Forced Join: {'🟢 فعال' if is_forced_join_active() else '⚫ غیرفعال'}\n"
        f"🔗 لینکدونی: <code>{get_link_directory_url()}</code>"
    )


def _welcome_text(name: str, bot_username: str) -> str:
    add_url = f"https://t.me/{bot_username}?startgroup=true"
    support = get_support_url()
    support_title = get_support_title()
    return (
        f"سلام <b>{name}</b> عزیز 🌹\n\n"
        "به ربات <b>تاسینو</b> خوش آمدید!\n"
        "ابزاری قدرتمند برای مدیریت گروه، امنیت و برگزاری مسابقات تاس.\n\n"
        "<b>✨ ویژگی‌های کلیدی:</b>\n"
        "✅ پاسخ‌دهی سریع و پایدار\n"
        "✅ محافظت کامل گروه و آنتی‌اسپم\n"
        "✅ قفل‌های پیشرفته و فیلتر کلمات\n"
        "✅ سیستم اخطار، سکوت و مدیریت اعضا\n"
        "✅ مسابقات تاس با شرط و کیف پول\n"
        "✅ پنل اینلاین تنظیمات در گروه\n"
        "✅ خوشامدگویی، کپچا و آنتی‌فلود\n"
        "✅ گزارش مالی و حق واسطه\n\n"
        "<b>🚀 نصب و راه‌اندازی:</b>\n"
        f'۱. ربات را به گروه اضافه کنید: <a href="{add_url}">کلیک کنید</a>\n'
        "۲. ربات را به عنوان <b>ادمین کامل</b> ارتقا دهید\n\n"
        "<b>📌 نکات مهم:</b>\n"
        "• گروه باید از نوع <b>سوپرگروه</b> باشد\n"
        "• برای تنظیمات در گروه بنویسید: <code>پنل</code>\n"
        "• برای راهنما در گروه بنویسید: <code>راهنما</code>\n\n"
        f'در صورت بروز مشکل به <a href="{support}">{support_title}</a> بپیوندید ❤️\n\n'
        "─── 🎲 <b>تاسینو</b> ───"
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
    if is_forced_join_active() and not is_creator(message.from_user.id):
        if not await is_user_channel_member(bot, message.from_user.id):
            return await message.answer(
                join_required_text(),
                reply_markup=join_required_keyboard(),
                parse_mode="HTML",
            )
    await _send_welcome(message, bot)


@router.message(F.text.in_(["استارت", "شروع", "start", "Start", "START"]))
async def msg_start_alias(message: Message, bot: Bot):
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
