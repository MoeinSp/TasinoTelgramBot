from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.button_emoji import btn


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("بازی‌ها", "btn_games", callback_data="menu:games"),
            btn("راهنما", "btn_help", callback_data="menu:help"),
        ],
        [
            btn("کانال‌ها", "btn_channels", url="https://t.me/TasinoBot"),
            btn("پشتیبانی", "btn_support", callback_data="menu:support"),
        ],
    ])


def games_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("تاس", "game_dice", callback_data="game:dice"),
            btn("دارت", "game_dart", callback_data="game:dart"),
            btn("بسکتبال", "game_basketball", callback_data="game:basketball"),
        ],
        [
            btn("پنالتی", "game_penalty", callback_data="game:penalty"),
            btn("بولینگ", "game_bowling", callback_data="game:bowling"),
            btn("اسلات", "game_slots", callback_data="game:slots"),
        ],
        [
            btn("سکه", "game_coin", callback_data="game:coin"),
            btn("سنگ کاغذ قیچی", "game_rps", callback_data="game:rps"),
            btn("شانس", "game_luck", callback_data="game:luck"),
        ],
        [btn("بازگشت", "btn_back", callback_data="menu:home")],
    ])


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("قفل‌ها", "help_locks", callback_data="help:locks"),
            btn("اعضا", "help_members", callback_data="help:members"),
        ],
        [
            btn("اخطارها", "help_warnings", callback_data="help:warnings"),
            btn("سکوت", "help_mute", callback_data="help:mute"),
        ],
        [
            btn("بازی‌ها", "help_games", callback_data="help:games"),
            btn("فیلتر کلمه", "help_filter", callback_data="help:filter"),
        ],
        [btn("بازگشت", "btn_back", callback_data="menu:home")],
    ])


HELP_TEXTS = {
    "locks": (
        "🔒 **دستورات قفل:**\n\n"
        "قفل لینک — جلوگیری از ارسال لینک\n"
        "قفل فوروارد — جلوگیری از فوروارد\n"
        "قفل یوزرنیم — جلوگیری از منشن\n"
        "قفل عکس — جلوگیری از عکس\n"
        "قفل مدیا — جلوگیری از فایل\n\n"
        "مثال: `قفل لینک` یا `آزاد لینک`"
    ),
    "members": (
        "👥 **دستورات اعضا:**\n\n"
        "`پروفایل` — نمایش اطلاعات عضو\n"
        "`برترین` — لیست فعال‌ترین اعضا\n"
        "`من` — اطلاعات من در گروه"
    ),
    "warnings": (
        "⚠️ **سیستم اخطار:**\n\n"
        "`اخطار` (ریپلای) — دادن اخطار\n"
        "`حذف اخطار` (ریپلای) — برداشتن اخطار\n"
        "بعد از تعداد مشخص اخطار → بن خودکار"
    ),
    "mute": (
        "🔇 **سکوت:**\n\n"
        "`سکوت` (ریپلای) — سکوت موقت (۲۴ساعت)\n"
        "`سکوت ۱ساعت` — سکوت با مدت دلخواه\n"
        "`آنسکوت` (ریپلای) — برداشتن سکوت"
    ),
    "games": (
        "🎮 **بازی‌ها:**\n\n"
        "تاس | دارت | بسکتبال | پنالتی\n"
        "بولینگ | اسلات | سکه | شانس\n"
        "سنگ کاغذ قیچی"
    ),
    "filter": (
        "🔤 **فیلتر کلمه:**\n\n"
        "`کلمه فیلتر [کلمه]` — اضافه کردن کلمه فیلتر\n"
        "`حذف فیلتر [کلمه]` — حذف کلمه فیلتر"
    ),
}
