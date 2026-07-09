"""
هندلرهای پیوی ربات تاسینو
"""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton as Btn

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


async def _send_welcome(message: Message):
    name = message.from_user.first_name or "کاربر"
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
    channel_id = int(message.text.split()[-1])
    ok, text = await _setup_channel(bot, channel_id)
    await message.answer(text, parse_mode="HTML")


@router.message(F.forward_from_chat)
async def cmd_set_channel_forward(message: Message, bot: Bot):
    if not is_creator(message.from_user.id):
        return
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
