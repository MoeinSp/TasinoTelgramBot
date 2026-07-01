"""
کیبوردهای پنل — compact با expand
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as B


def _back(to="0", label="🔙 بازگشت") -> B:
    return B(text=label, callback_data=f"p:{to}")

def _home() -> B:
    return B(text="🏠 خانه", callback_data="p:0")

def _act(label: str, action: str) -> B:
    return B(text=label, callback_data=f"cmd:{action}")

def _mk(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


# ─── منوی اصلی (compact) ─────────────────────────────────────────────────────

def panel_main() -> InlineKeyboardMarkup:
    return _mk(
        [
            B(text="🛠 مدیریت گروه",    callback_data="p:cat_manage"),
            B(text="🎲 بازی و سرگرمی",  callback_data="p:cat_game"),
        ],
        [
            B(text="💰 مالی",            callback_data="p:cat_finance"),
            B(text="⚙️ تنظیمات",        callback_data="p:cat_settings"),
        ],
        [B(text="❌ بستن",               callback_data="p:close")],
    )


# ─── دسته: مدیریت گروه ───────────────────────────────────────────────────────

def panel_cat_manage() -> InlineKeyboardMarkup:
    return _mk(
        [
            B(text="🔐 قفل‌ها",         callback_data="p:1"),
            B(text="👮 ادمین‌ها",        callback_data="p:2.2"),
            B(text="⭐ ویژه",            callback_data="p:2.3"),
        ],
        [
            B(text="🚫 بن",             callback_data="p:2.4"),
            B(text="🤫 سکوت",           callback_data="p:2.5"),
            B(text="⚠️ اخطار",          callback_data="p:3"),
        ],
        [
            B(text="🔤 فیلتر",          callback_data="p:5"),
            B(text="👑 مالکیت",         callback_data="p:2.1"),
            B(text="📣 تگ",             callback_data="p:2.6"),
        ],
        [_back(label="🔙 منوی اصلی")],
    )


# ─── دسته: بازی و سرگرمی ─────────────────────────────────────────────────────

def panel_cat_game() -> InlineKeyboardMarkup:
    return _mk(
        [
            B(text="🎲 تاس",            callback_data="p:4.1"),
            B(text="🎮 سایر بازی‌ها",   callback_data="p:4.2"),
            B(text="📊 آمار",           callback_data="p:4.3"),
        ],
        [
            B(text="⚙️ تنظیمات بازی",  callback_data="p:4.4"),
            B(text="🤖 سخنگو",          callback_data="p:6.1"),
            B(text="📚 یادگیری",        callback_data="p:6.2"),
        ],
        [_back(label="🔙 منوی اصلی")],
    )


# ─── دسته: مالی ──────────────────────────────────────────────────────────────

def panel_cat_finance() -> InlineKeyboardMarkup:
    return _mk(
        [
            B(text="👛 موجودی",         callback_data="p:8.1"),
            B(text="💳 کارت",           callback_data="p:8.2"),
        ],
        [
            B(text="📑 گزارش/تسویه",   callback_data="p:8.3"),
            B(text="💹 کارمزد",         callback_data="p:8.4"),
        ],
        [_back(label="🔙 منوی اصلی")],
    )


# ─── دسته: تنظیمات ───────────────────────────────────────────────────────────

def panel_cat_settings() -> InlineKeyboardMarkup:
    return _mk(
        [
            B(text="⚙️ تنظیمات گروه",  callback_data="p:7"),
            B(text="🏷 لقب/مشخصات",    callback_data="p:2.7"),
            B(text="🔍 وضعیت گروه",    callback_data="p:6.3"),
        ],
        [
            B(text="🎉 خوشامدگویی",    callback_data="p:welcome"),
            B(text="🚫 آنتی فلود",     callback_data="p:antispam"),
        ],
        [_back(label="🔙 منوی اصلی")],
    )


# ─── صفحات فرعی با دکمه‌های اجرایی ──────────────────────────────────────────

def _sub(parent: str, *action_rows) -> InlineKeyboardMarkup:
    rows = list(action_rows)
    rows.append([_back(parent), _home()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_1() -> InlineKeyboardMarkup:
    return _sub("cat_manage",
        [_act("📋 وضعیت قفل‌ها", "locks_status")],
        [B(text="🔒 قفل‌های جداگانه", callback_data="p:1.1"),
         B(text="🔐 قفل کل گروه",    callback_data="p:1.2")],
    )

def panel_1_1() -> InlineKeyboardMarkup:
    return _sub("1",
        [_act("📋 وضعیت قفل‌ها", "locks_status")],
    )

def panel_1_2() -> InlineKeyboardMarkup:
    return _sub("1",
        [_act("🔐 قفل کردن گروه", "group_lock"),
         _act("🔓 باز کردن",      "group_unlock")],
    )

def panel_2_1() -> InlineKeyboardMarkup:
    return _sub("cat_manage",
        [_act("👑 مالک فعلی", "owner_info")],
    )

def panel_2_2() -> InlineKeyboardMarkup:
    return _sub("cat_manage",
        [_act("📋 لیست ادمین‌ها",       "admin_list")],
        [_act("🔄 همگام‌سازی ادمین‌ها", "sync_admins")],
    )

def panel_2_3() -> InlineKeyboardMarkup:
    return _sub("cat_manage",
        [_act("📋 لیست ویژه",          "vip_list"),
         _act("🗑 پاکسازی",            "vip_clear")],
    )

def panel_2_4() -> InlineKeyboardMarkup:
    return _sub("cat_manage",
        [_act("📋 لیست بن",            "ban_list"),
         _act("🗑 پاکسازی",            "ban_clear")],
    )

def panel_2_5() -> InlineKeyboardMarkup:
    return _sub("cat_manage",
        [_act("📋 لیست سکوت",          "mute_list"),
         _act("🗑 پاکسازی",            "mute_clear")],
    )

def panel_2_6() -> InlineKeyboardMarkup:
    return _sub("cat_manage",
        [_act("📣 تگ همه اعضا", "tag_all")],
    )

def panel_2_7() -> InlineKeyboardMarkup:
    return _sub("cat_settings",
        [_act("🏷 لقب من در گروه", "my_alias")],
    )

def panel_3() -> InlineKeyboardMarkup:
    return _sub("cat_manage",
        [_act("📊 اخطارهای من", "my_warnings")],
    )

def panel_4_1() -> InlineKeyboardMarkup:
    return _sub("cat_game",
        [_act("🎲 پرتاب تاس",      "dice_hint"),
         _act("📊 آمار تاس",       "dice_stats")],
    )

def panel_4_2() -> InlineKeyboardMarkup:
    return _sub("cat_game",
        [_act("🏀 بسکتبال", "basketball"), _act("⚽ پنالتی",  "penalty"),  _act("🎳 بولینگ", "bowling")],
        [_act("🎯 دارت",    "dart"),        _act("🎰 اسلات",   "slots"),    _act("🪙 سکه",    "coin")],
        [_act("🍀 شانس",    "luck"),        _act("✂️ سنگ‌کاغذ‌قیچی", "rps")],
    )

def panel_4_3() -> InlineKeyboardMarkup:
    return _sub("cat_game",
        [_act("📊 آمار تاس",        "dice_stats")],
        [_act("🏆 برترین کاربران",  "top_users")],
    )

def panel_4_4() -> InlineKeyboardMarkup:
    return _sub("cat_game",
        [_act("🎨 تم فعلی تاس",  "dice_theme"),
         _act("💹 کارمزد",       "fee_show")],
    )

def panel_5() -> InlineKeyboardMarkup:
    return _sub("cat_manage",
        [_act("📋 لیست کلمات فیلتر", "filter_list")],
    )

def panel_6_1() -> InlineKeyboardMarkup:
    return _sub("cat_game",
        [_act("🔊 روشن",  "speaker_on"),
         _act("🔇 خاموش", "speaker_off")],
    )

def panel_6_2() -> InlineKeyboardMarkup:
    return _sub("cat_game",
        [_act("📋 لیست یادگیری", "learn_list")],
    )

def panel_6_3() -> InlineKeyboardMarkup:
    return _sub("cat_settings",
        [_act("📊 وضعیت گروه", "group_status")],
    )

def panel_7() -> InlineKeyboardMarkup:
    return _sub("cat_settings",
        [_act("📊 وضعیت گروه",       "group_status")],
        [_act("✅ روشن کردن ربات",   "bot_on"),
         _act("💤 خاموش کردن ربات", "bot_off")],
    )

def panel_8_1() -> InlineKeyboardMarkup:
    return _sub("cat_finance",
        [_act("👛 موجودی من",       "my_balance"),
         _act("📊 حساب همه اعضا",  "accounts")],
    )

def panel_8_2() -> InlineKeyboardMarkup:
    return _sub("cat_finance",
        [_act("💳 کارت مالک", "card_show")],
    )

def panel_8_3() -> InlineKeyboardMarkup:
    return _sub("cat_finance",
        [_act("📑 گزارش تراکنش‌ها", "report"),
         _act("🤝 تسویه من",        "settle_me")],
    )

def panel_8_4() -> InlineKeyboardMarkup:
    return _sub("cat_finance",
        [_act("💹 کارمزد فعلی", "fee_show")],
    )


def panel_welcome() -> InlineKeyboardMarkup:
    return _sub("cat_settings",
        [_act("📋 وضعیت خوشامد",     "welcome_status")],
        [_act("✅ روشن کردن",         "welcome_on"),
         _act("❌ خاموش کردن",        "welcome_off")],
        [_act("🗑 حذف گیف",           "welcome_gif_del")],
    )


def panel_antispam() -> InlineKeyboardMarkup:
    return _sub("cat_settings",
        [_act("📋 وضعیت فلود",        "flood_status")],
        [_act("✅ روشن کردن",         "flood_on"),
         _act("❌ خاموش کردن",        "flood_off")],
    )


# ─── صفحات دسته‌بندی‌ها ──────────────────────────────────────────────────────

_KB_MAP = {
    "":           panel_main,
    "0":          panel_main,
    "cat_manage": panel_cat_manage,
    "cat_game":   panel_cat_game,
    "cat_finance":  panel_cat_finance,
    "cat_settings": panel_cat_settings,
    "1":    panel_1,   "1.1": panel_1_1, "1.2": panel_1_2,
    "2.1":  panel_2_1, "2.2": panel_2_2, "2.3": panel_2_3,
    "2.4":  panel_2_4, "2.5": panel_2_5, "2.6": panel_2_6, "2.7": panel_2_7,
    "3":    panel_3,
    "4.1":  panel_4_1, "4.2": panel_4_2, "4.3": panel_4_3, "4.4": panel_4_4,
    "5":    panel_5,
    "6.1":  panel_6_1, "6.2": panel_6_2, "6.3": panel_6_3,
    "7":    panel_7,
    "8.1":  panel_8_1, "8.2": panel_8_2, "8.3": panel_8_3, "8.4": panel_8_4,
    "welcome":  panel_welcome,
    "antispam": panel_antispam,
}


def get_panel(code: str):
    from bot.group_help import PAGES, ALIASES, _norm
    code = _norm(code).strip()
    if code not in PAGES and code in ALIASES:
        code = ALIASES[code]
    # صفحات دسته‌بندی متن ندارن — از PAGES_EXTRA می‌خونیم
    page = PAGES.get(code) or _CAT_TEXTS.get(code)
    if page is None:
        return None, None
    kb_fn = _KB_MAP.get(code, panel_main)
    return page, kb_fn()


# متن صفحات دسته‌بندی (جداگانه از group_help)
_CAT_TEXTS = {
    "cat_manage":   "🛠 <b>مدیریت گروه</b>\n\nبخش مورد نظر رو انتخاب کن:",
    "cat_game":     "🎲 <b>بازی و سرگرمی</b>\n\nبخش مورد نظر رو انتخاب کن:",
    "cat_finance":  "💰 <b>مالی و تراکنش</b>\n\nبخش مورد نظر رو انتخاب کن:",
    "cat_settings": "⚙️ <b>تنظیمات</b>\n\nبخش مورد نظر رو انتخاب کن:",
    "welcome":  (
        "🎉 <b>خوشامدگویی</b>\n\n"
        "وقتی عضو جدیدی وارد گروه می‌شه، ربات پیام خوشامد می‌فرسته.\n\n"
        "دستورات متنی:\n"
        "  <code>خوشامد روشن / خاموش</code>\n"
        "  <code>متن خوشامد [پیام]</code>\n"
        "  <code>گیف خوشامد</code> — ریپلای روی گیف\n"
        "  <code>حذف گیف خوشامد</code>\n\n"
        "متغیر: <code>{name}</code> = نام عضو جدید"
    ),
    "antispam": (
        "🚫 <b>آنتی فلود</b>\n\n"
        "اگه کاربری بیش از حد مجاز پیام بفرسته، ۵ دقیقه سکوت می‌شه.\n\n"
        "دستورات متنی:\n"
        "  <code>فلود روشن / خاموش</code>\n"
        "  <code>حد فلود [تعداد] [ثانیه]</code>\n"
        "  مثال: <code>حد فلود 5 10</code>"
    ),
}
