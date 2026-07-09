"""
هندلرهای پیوی ربات تاسینو
"""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton as Btn

from bot import cache
from bot.cache_manager import load_all_caches
from bot.panel_keyboards import panel_main
from bot.group_help import PAGE_MAIN
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

router = Router()
router.message.filter(F.chat.type == "private")
_CREATOR_STATE: dict[int, str] = {}


def _welcome_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="📋 پنل کامل", callback_data="p:0")],
        [
            Btn(text="🛡 امنیت", callback_data="p:locks"),
            Btn(text="⚙️ تنظیمات", callback_data="p:settings"),
        ],
        [
            Btn(text="🎲 بازی", callback_data="p:game"),
            Btn(text="💰 مالی", callback_data="p:finance"),
        ],
        [Btn(text="💬 پشتیبانی", url="https://t.me/Spayers")],
    ])


def _creator_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="📊 وضعیت جوین اجباری", callback_data="cr:fj:status")],
        [Btn(text="🟢 روشن", callback_data="cr:fj:on"), Btn(text="⚫ خاموش", callback_data="cr:fj:off")],
        [Btn(text="🗑 حذف کانال", callback_data="cr:fj:clear"), Btn(text="📥 ثبت کانال با آیدی", callback_data="cr:fj:setid")],
        [Btn(text="🧠 وضعیت کش", callback_data="cr:cache:stats"), Btn(text="♻️ ریلود کش", callback_data="cr:cache:reload")],
        [Btn(text="🤖 اطلاعات ربات", callback_data="cr:bot:info"), Btn(text="📘 راهنمای سریع", callback_data="cr:help")],
    ])


def _creator_panel_text(name: str) -> str:
    return (
        f"👑 سلام {name}\n\n"
        "به <b>پنل سازنده تاسینو</b> خوش آمدید.\n"
        "از اینجا می‌توانید جوین اجباری، کش و تنظیمات کلیدی ربات را سریع مدیریت کنید.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Creator: <code>{CREATOR_USER_ID}</code>\n"
        f"⚙️ Forced Join: {'🟢 فعال' if is_forced_join_active() else '⚫ غیرفعال'}"
    )


async def _send_welcome(message: Message):
    name = message.from_user.first_name or "کاربر"
    if is_creator(message.from_user.id):
        return await message.answer(
            _creator_panel_text(name),
            reply_markup=_creator_panel_kb(),
            parse_mode="HTML",
        )
    await message.answer(
        f"سلام {name} عزیز! 👋\n\n"
        "🎲 به ربات <b>تاسینو</b> خوش آمدید!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "از دکمه‌های زیر برای دسترسی به راهنما استفاده کنید\n"
        "یا در گروه بنویسید: <code>راهنما</code>",
        reply_markup=_welcome_kb(),
        parse_mode="HTML",
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
    await _send_welcome(message)


@router.message(F.text.in_(["استارت", "شروع", "start", "Start", "START"]))
async def msg_start_alias(message: Message, bot: Bot):
    if is_forced_join_active() and not is_creator(message.from_user.id):
        if not await is_user_channel_member(bot, message.from_user.id):
            return await message.answer(
                join_required_text(),
                reply_markup=join_required_keyboard(),
                parse_mode="HTML",
            )
    await _send_welcome(message)


@router.callback_query(F.data == "join:recheck")
async def cb_join_recheck(call: CallbackQuery, bot: Bot):
    if await is_user_channel_member(bot, call.from_user.id):
        await call.answer("✅ عضویت شما تأیید شد!", show_alert=True)
        try:
            await call.message.edit_text(
                "✅ <b>عضویت تأیید شد</b>\n\n"
                "اکنون می‌توانید از تمام خدمات ربات استفاده کنید.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await _send_welcome(call.message)
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


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(PAGE_MAIN, reply_markup=panel_main(), parse_mode="HTML")


@router.message(F.text.in_(["راهنما", "منو", "پنل", "help", "menu"]))
async def msg_help(message: Message):
    await message.answer(PAGE_MAIN, reply_markup=panel_main(), parse_mode="HTML")


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
            "اگر ربات ادمین کانال نباشد، بررسی عضویت انجام نمی‌شود.",
            parse_mode="HTML",
        )
        return await call.answer("راهنما ارسال شد")

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
        f"🆔 <code>{channel_id}</code>\n\n"
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
