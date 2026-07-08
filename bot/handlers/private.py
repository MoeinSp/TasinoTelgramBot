"""
هندلرهای پیوی ربات تاسینو
"""
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton as Btn

from bot.panel_keyboards import get_panel, panel_main
from bot.group_help import PAGE_MAIN

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


@router.message(CommandStart())
async def start(message: Message):
    name = message.from_user.first_name or "کاربر"
    await message.answer(
        f"سلام {name} عزیز! 👋\n\n"
        "🎲 به ربات تاسینو خوش اومدی!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "از دکمه‌های زیر برای دسترسی به راهنما استفاده کن:\n"
        "یا توی گروه بنویس:  `راهنما`",
        reply_markup=_welcome_kb(),
        parse_mode="Markdown",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(PAGE_MAIN, reply_markup=panel_main())


@router.message(F.text.in_(["راهنما", "منو", "پنل", "help", "menu"]))
async def msg_help(message: Message):
    await message.answer(PAGE_MAIN, reply_markup=panel_main())
