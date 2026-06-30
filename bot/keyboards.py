from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 بازی‌ها", callback_data="menu:games"),
            InlineKeyboardButton(text="📚 راهنما", callback_data="menu:help"),
        ],
        [
            InlineKeyboardButton(text="📣 کانال‌ها", url="https://t.me/TasinoBot"),
            InlineKeyboardButton(text="💬 پشتیبانی", callback_data="menu:support"),
        ],
    ])


def games_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎲 تاس", callback_data="game:dice"),
            InlineKeyboardButton(text="🎯 دارت", callback_data="game:dart"),
            InlineKeyboardButton(text="🏀 بسکتبال", callback_data="game:basketball"),
        ],
        [
            InlineKeyboardButton(text="⚽ پنالتی", callback_data="game:penalty"),
            InlineKeyboardButton(text="🎳 بولینگ", callback_data="game:bowling"),
            InlineKeyboardButton(text="🎰 اسلات", callback_data="game:slots"),
        ],
        [
            InlineKeyboardButton(text="🪙 سکه", callback_data="game:coin"),
            InlineKeyboardButton(text="✂️ سنگ کاغذ قیچی", callback_data="game:rps"),
            InlineKeyboardButton(text="🍀 شانس", callback_data="game:luck"),
        ],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:home")],
    ])


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔒 قفل‌ها", callback_data="help:locks"),
            InlineKeyboardButton(text="👥 اعضا", callback_data="help:members"),
        ],
        [
            InlineKeyboardButton(text="⚠️ اخطارها", callback_data="help:warnings"),
            InlineKeyboardButton(text="🔇 سکوت", callback_data="help:mute"),
        ],
        [
            InlineKeyboardButton(text="🎮 بازی‌ها", callback_data="help:games"),
            InlineKeyboardButton(text="🔤 فیلتر کلمه", callback_data="help:filter"),
        ],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:home")],
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
