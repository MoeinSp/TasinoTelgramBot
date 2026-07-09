"""
کیبوردهای پنل — طراحی یکپارچه با دکمه‌های toggle زنده
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as B

SEP = "━━━━━━━━━━━━━━━━━━━━"


def _back(to: str = "0", label: str = "🔙 بازگشت") -> B:
    return B(text=label, callback_data=f"p:{to}")


def _home() -> B:
    return B(text="🏠 خانه", callback_data="p:0")


def _go(label: str, page: str) -> B:
    return B(text=label, callback_data=f"p:{page}")


def _cmd(label: str, action: str) -> B:
    return B(text=label, callback_data=f"cmd:{action}")


# ─── دستورات بازی و سرگرمی (toggle از پنل) ───────────────────────────────────

GAME_CMDS = [
    ("تاس", "🎲 تاس"),
    ("بسکتبال", "🏀 بسکتبال"),
    ("پنالتی", "⚽ پنالتی"),
    ("بولینگ", "🎳 بولینگ"),
    ("دارت", "🎯 دارت"),
    ("سنگ کاغذ قیچی", "✂️ سنگ‌قیچی"),
    ("شانس", "🍀 شانس"),
    ("سکه", "🪙 سکه"),
    ("اسلات", "🎰 اسلات"),
    ("بازی", "🎮 بازی"),
]

FUN_CMDS = [
    ("جوک", "😂 جوک"),
    ("فال", "📜 فال"),
    ("دانستنی", "💡 دانستنی"),
    ("فکت", "💡 فکت"),
    ("سخن", "💎 سخن"),
    ("معما", "🤔 معما"),
    ("دو راهی", "⚖️ دو راهی"),
    ("چالش", "🎯 چالش"),
    ("شخصیت", "💕 شخصیت"),
]

ALL_TOGGLEABLE_CMDS = [c for c, _ in FUN_CMDS + GAME_CMDS]
FUN_CMD_SET = {c for c, _ in FUN_CMDS}


def _cmds_panel_kb(items: list, enabled: set, prefix: str) -> InlineKeyboardMarkup:
    rows, row = [], []
    for cmd, label in items:
        on = cmd in enabled
        icon = "🟢" if on else "⚫"
        row.append(B(text=f"{icon} {label}", callback_data=f"cmd:tglc:{cmd}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_back(prefix), _home()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _toggle(label: str, key: str, on: bool) -> B:
    icon = "🟢" if on else "⚫"
    return B(text=f"{icon} {label}", callback_data=f"cmd:tgl_{key}")


def _mk(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def _nav(*rows, parent: str = "0") -> InlineKeyboardMarkup:
    r = list(rows)
    r.append([_back(parent), _home()])
    return InlineKeyboardMarkup(inline_keyboard=r)


def panel_header(icon: str, title: str, subtitle: str = "") -> str:
    lines = [f"{icon} <b>{title}</b>", SEP]
    if subtitle:
        lines.extend(["", subtitle, ""])
    return "\n".join(lines)


# ─── منوی اصلی ───────────────────────────────────────────────────────────────

def panel_main() -> InlineKeyboardMarkup:
    return _mk(
        [_go("🛡 امنیت و قفل", "locks"), _go("👥 مدیریت اعضا", "manage")],
        [_go("🎲 بازی و سرگرمی", "game"), _go("⚙️ تنظیمات گروه", "settings")],
        [_go("💰 مالی", "finance")],
        [B(text="❌ بستن", callback_data="p:close")],
    )


# ─── پنل‌های زنده ────────────────────────────────────────────────────────────

def locks_panel_text(locks: dict, group_locked: bool = False) -> str:
    from bot.helpers import LOCK_NAMES, LOCK_ORDER
    on = [LOCK_NAMES[k] for k in LOCK_ORDER if locks.get(k)]
    off = [LOCK_NAMES[k] for k in LOCK_ORDER if not locks.get(k)]

    lines = [
        panel_header("🛡", "امنیت و قفل‌ها", "روی هر دکمه بزن تا وضعیت عوض بشه."),
        f"🔐 قفل کل گروه: <b>{'روشن' if group_locked else 'خاموش'}</b>",
        f"🔒 قفل‌های فعال: <b>{len(on)}</b>  ·  🔓 غیرفعال: <b>{len(off)}</b>",
    ]
    if on:
        lines += ["", "✅ <b>روشن:</b>", " • " + " · ".join(on[:12])]
        if len(on) > 12:
            lines.append(f" • +{len(on) - 12} مورد دیگر")
    return "\n".join(lines)


def locks_panel_kb(locks: dict, group_locked: bool = False) -> InlineKeyboardMarkup:
    from bot.helpers import LOCK_NAMES, LOCK_ORDER
    rows, row = [], []
    for key in LOCK_ORDER:
        label = LOCK_NAMES.get(key)
        if not label:
            continue
        icon = "🔒" if locks.get(key) else "🔓"
        row.append(B(text=f"{icon} {label}", callback_data=f"cmd:lock_toggle_{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_toggle("قفل کل گروه", "group_lock", group_locked)])
    rows.append([_back("0"), _home()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_panel_text(s: dict) -> str:
    def st(key: str) -> str:
        return "🟢 روشن" if s.get(key) else "⚫ خاموش"

    night = s.get("night")
    night_txt = f"🌙 {night[0]}:00–{night[1]}:00" if night else "⚫ خاموش"
    return "\n".join([
        panel_header("⚙️", "تنظیمات گروه", "هر دکمه وضعیت را نشان می‌دهد و با یک کلیک تغییر می‌کند."),
        f"🤖 ربات: <b>{st('bot')}</b>",
        f"🎉 خوشامد: <b>{st('welcome')}</b>",
        f"🔐 کپچا: <b>{st('captcha')}</b>",
        f"🚫 آنتی‌فلود: <b>{st('flood')}</b>",
        f"🚨 ضد رید: <b>{st('antiraid')}</b>",
        f"🌙 حالت شب: <b>{night_txt}</b>",
    ])


def settings_panel_kb(s: dict) -> InlineKeyboardMarkup:
    return _nav(
        [_toggle("ربات", "bot", s["bot"]), _toggle("خوشامد", "welcome", s["welcome"])],
        [_toggle("کپچا", "captcha", s["captcha"]), _toggle("آنتی‌فلود", "flood", s["flood"])],
        [_toggle("ضد رید", "antiraid", s["antiraid"])],
        [_cmd("📊 جزئیات کامل", "group_status")],
        parent="0",
    )


def game_panel_text(s: dict) -> str:
    theme = s.get("theme", 1)
    fee = s.get("fee", 10)
    enabled = s.get("enabled_commands", set())
    games_on = sum(1 for c, _ in GAME_CMDS if c in enabled)
    fun_on = sum(1 for c, _ in FUN_CMDS if c in enabled)
    return "\n".join([
        panel_header("🎲", "بازی و سرگرمی", "روی هر دکمه بزن تا روشن/خاموش بشه."),
        f"🔊 سخنگو: <b>{'🟢 روشن' if s.get('speaker') else '⚫ خاموش'}</b>",
        f"🎮 ایموجی تلگرام: <b>{'🟢 روشن' if s.get('tg_emoji') else '⚫ خاموش'}</b>",
        f"🎲 تاس متوالی: <b>{'🟢 روشن' if s.get('dice_option') else '⚫ خاموش'}</b>",
        f"🎯 بازی‌ها: <b>{games_on}/{len(GAME_CMDS)}</b> فعال",
        f"🎭 سرگرمی: <b>{fun_on}/{len(FUN_CMDS)}</b> فعال",
        f"🎨 تم تاس: <b>{theme}</b>  ·  💹 حق واسطه: <b>{fee}٪</b>",
    ])


def game_panel_kb(s: dict) -> InlineKeyboardMarkup:
    return _nav(
        [_toggle("سخنگو", "speaker", s["speaker"]), _toggle("ایموجی تلگرام", "tg_emoji", s["tg_emoji"])],
        [_toggle("تاس متوالی", "dice_option", s["dice_option"])],
        [_go("🎯 بازی‌ها", "games"), _go("🎭 سرگرمی", "fun")],
        [_go("📊 آمار", "stats")],
        [_cmd("🎨 تم تاس", "dice_theme"), _cmd("💹 حق واسطه", "fee_show")],
        parent="0",
    )


def games_panel_text(enabled: set) -> str:
    on = sum(1 for c, _ in GAME_CMDS if c in enabled)
    return panel_header(
        "🎯", "بازی‌ها",
        f"🟢 فعال: {on}  ·  ⚫ خاموش: {len(GAME_CMDS) - on}",
    )


def games_panel_kb(enabled: set) -> InlineKeyboardMarkup:
    return _cmds_panel_kb(GAME_CMDS, enabled, "game")


def fun_panel_text(enabled: set) -> str:
    on = sum(1 for c, _ in FUN_CMDS if c in enabled)
    return panel_header(
        "🎭", "سرگرمی",
        f"🟢 فعال: {on}  ·  ⚫ خاموش: {len(FUN_CMDS) - on}",
    )


def fun_panel_kb(enabled: set) -> InlineKeyboardMarkup:
    return _cmds_panel_kb(FUN_CMDS, enabled, "game")


def manage_panel_text() -> str:
    return panel_header(
        "👥", "مدیریت اعضا",
        "برای افزودن/حذف، روی پیام کاربر ریپلای کن و دستور بزن.",
    )


def manage_panel_kb() -> InlineKeyboardMarkup:
    return _nav(
        [_go("👮 ادمین‌ها", "admins"), _go("⭐ اعضای ویژه", "vip")],
        [_go("🚫 بن", "ban"), _go("🤫 سکوت", "mute")],
        [_cmd("📣 تگ همه", "tag_all"), _cmd("⚠️ اخطار من", "my_warnings")],
        [_cmd("👑 مالک گروه", "owner_info"), _cmd("🔤 فیلتر کلمات", "filter_list")],
        parent="0",
    )


def finance_panel_text() -> str:
    return panel_header("💰", "مالی", "مدیریت موجودی، کارت و گزارش‌ها.")


def finance_panel_kb() -> InlineKeyboardMarkup:
    return _nav(
        [_cmd("👛 موجودی من", "my_balance"), _cmd("📊 حساب همه", "accounts")],
        [_cmd("💳 کارت مالک", "card_show"), _cmd("💹 حق واسطه", "fee_show")],
        [_cmd("📑 گزارش", "report"), _cmd("🤝 تسویه", "settle_me")],
        parent="0",
    )


# ─── زیرصفحات (لیست و اطلاعات) ─────────────────────────────────────────────

def panel_admins() -> InlineKeyboardMarkup:
    return _nav(
        [_cmd("📋 لیست ادمین‌ها", "admin_list"), _cmd("🔄 همگام‌سازی", "sync_admins")],
        parent="manage",
    )


def panel_vip() -> InlineKeyboardMarkup:
    return _nav(
        [_cmd("📋 لیست ویژه", "vip_list"), _cmd("🗑 پاکسازی", "vip_clear")],
        parent="manage",
    )


def panel_ban() -> InlineKeyboardMarkup:
    return _nav(
        [_cmd("📋 لیست بن", "ban_list")],
        parent="manage",
    )


def panel_mute() -> InlineKeyboardMarkup:
    return _nav(
        [_cmd("📋 لیست سکوت", "mute_list")],
        parent="manage",
    )


def panel_games() -> InlineKeyboardMarkup:
    return _nav([_go("🔙 به پنل بازی", "game")], parent="game")


def panel_fun() -> InlineKeyboardMarkup:
    return _nav([_go("🔙 به پنل بازی", "game")], parent="game")


def panel_stats() -> InlineKeyboardMarkup:
    return _nav(
        [_cmd("📊 آمار تاس", "dice_stats"), _cmd("🏆 برترین‌ها", "top_users")],
        parent="game",
    )


# ─── نگاشت صفحات ─────────────────────────────────────────────────────────────

_LIVE_PAGES = {"locks", "1", "1.1", "settings", "game", "manage", "finance", "games", "fun"}

_STATIC_KB = {
    "": panel_main, "0": panel_main,
    "locks": lambda: locks_panel_kb({}),
    "1": lambda: locks_panel_kb({}), "1.1": lambda: locks_panel_kb({}),
    "settings": lambda: settings_panel_kb({}),
    "game": lambda: game_panel_kb({}),
    "manage": manage_panel_kb,
    "finance": finance_panel_kb,
    "admins": panel_admins, "vip": panel_vip,
    "ban": panel_ban, "mute": panel_mute,
    "games": panel_games, "stats": panel_stats,
    # سازگاری با کدهای قدیمی
    "cat_manage": manage_panel_kb, "cat_game": lambda: game_panel_kb({}),
    "cat_finance": finance_panel_kb, "cat_settings": lambda: settings_panel_kb({}),
    "2.1": panel_admins, "2.2": panel_admins, "2.3": panel_vip,
    "2.4": panel_ban, "2.5": panel_mute, "2.6": manage_panel_kb,
    "2.7": manage_panel_kb, "3": manage_panel_kb,
    "4.1": panel_stats, "4.2": panel_games, "4.3": panel_stats, "4.4": lambda: game_panel_kb({}),
    "5": manage_panel_kb, "6.1": lambda: game_panel_kb({}),
    "6.2": panel_games, "6.3": lambda: settings_panel_kb({}),
    "7": lambda: settings_panel_kb({}),
    "8.1": finance_panel_kb, "8.2": finance_panel_kb,
    "8.3": finance_panel_kb, "8.4": finance_panel_kb,
    "welcome": lambda: settings_panel_kb({}),
    "antispam": lambda: settings_panel_kb({}),
    "captcha": lambda: settings_panel_kb({}),
    "antiraid": lambda: settings_panel_kb({}),
}

_CAT_TEXTS = {
    "manage": manage_panel_text(),
    "finance": finance_panel_text(),
    "admins": "👮 <b>ادمین‌ها</b>\n\nبرای افزودن: ریپلای + <code>ادمین</code>",
    "vip": "⭐ <b>اعضای ویژه</b>\n\nبرای افزودن: ریپلای + <code>ویژه</code>",
    "ban": "🚫 <b>بن</b>\n\nبرای بن: ریپلای + <code>بن</code>",
    "mute": "🤫 <b>سکوت</b>\n\nبرای سکوت: ریپلای + <code>سکوت</code>",
    "games": "🎯 <b>بازی‌ها</b>\n\nروی هر دکمه وضعیت را تغییر بده.",
    "fun": "🎭 <b>سرگرمی</b>\n\nروی هر دکمه وضعیت را تغییر بده.",
    "stats": "📊 <b>آمار</b>",
    "cat_manage": manage_panel_text(),
    "cat_game": panel_header("🎲", "بازی و سرگرمی"),
    "cat_finance": finance_panel_text(),
    "cat_settings": panel_header("⚙️", "تنظیمات گروه"),
}


def is_live_page(code: str) -> bool:
    return code in _LIVE_PAGES


def get_static_panel(code: str):
    from bot.group_help import PAGES, ALIASES, _norm
    code = _norm(code).strip()
    if code not in PAGES and code in ALIASES:
        code = ALIASES[code]
    text = PAGES.get(code) or _CAT_TEXTS.get(code)
    if text is None:
        return None, None
    kb_fn = _STATIC_KB.get(code, panel_main)
    kb = kb_fn() if callable(kb_fn) else kb_fn
    return text, kb


def get_panel(code: str):
    """سازگاری با کد قدیمی — پنل‌های زنده در هندلر رندر می‌شوند."""
    return get_static_panel(code)
