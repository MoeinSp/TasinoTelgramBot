"""
کیبوردهای پنل — طراحی یکدست، نقش‌محور، تیک‌های خوانا
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as B

from bot.panel_ui import SEP, panel_header, toggle_label, lock_label


def _back(to: str = "0", label: str = "بازگشت") -> B:
    return B(text=f"‹ {label}", callback_data=f"p:{to}")


def _home() -> B:
    return B(text="خانه", callback_data="p:0")


def _go(label: str, page: str) -> B:
    return B(text=label, callback_data=f"p:{page}")


def _cmd(label: str, action: str) -> B:
    return B(text=label, callback_data=f"cmd:{action}")


def _act(label: str, data: str) -> B:
    return B(text=label, callback_data=data)


# ─── دستورات بازی و سرگرمی ───────────────────────────────────────────────────

GAME_CMDS = [
    ("تاس", "تاس"),
    ("بسکتبال", "بسکتبال"),
    ("پنالتی", "پنالتی"),
    ("بولینگ", "بولینگ"),
    ("دارت", "دارت"),
    ("سنگ کاغذ قیچی", "سنگ‌قیچی"),
    ("شانس", "شانس"),
    ("سکه", "سکه"),
    ("اسلات", "اسلات"),
    ("بازی", "بازی"),
]

FUN_CMDS = [
    ("جوک", "جوک"),
    ("فال", "فال"),
    ("دانستنی", "دانستنی"),
    ("فکت", "فکت"),
    ("سخن", "سخن"),
    ("معما", "معما"),
    ("دو راهی", "دو راهی"),
    ("چالش", "چالش"),
    ("شخصیت", "شخصیت"),
]

ALL_TOGGLEABLE_CMDS = [c for c, _ in FUN_CMDS + GAME_CMDS]
FUN_CMD_SET = {c for c, _ in FUN_CMDS}


def _cmds_panel_kb(items: list, enabled: set, prefix: str) -> InlineKeyboardMarkup:
    rows, row = [], []
    for cmd, label in items:
        on = cmd in enabled
        row.append(B(text=toggle_label(on, label), callback_data=f"cmd:tglc:{cmd}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_back(prefix), _home()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _toggle(label: str, key: str, on: bool) -> B:
    return B(text=toggle_label(on, label), callback_data=f"cmd:tgl_{key}")


def _mk(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def _nav(*rows, parent: str = "0") -> InlineKeyboardMarkup:
    r = list(rows)
    r.append([_back(parent), _home()])
    return InlineKeyboardMarkup(inline_keyboard=r)


# ─── منوی اصلی ───────────────────────────────────────────────────────────────

def panel_main(*, pv: bool = False, is_owner: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [_go("امنیت و قفل", "locks"), _go("تنظیمات گروه", "settings")],
        [_go("اعضا", "manage"), _go("بازی و سرگرمی", "game")],
        [_go("مالی", "finance"), _go("چالش‌ها", "challenges")],
    ]
    if is_owner:
        rows.append([_go("ویژه مالک", "owner")])
    if pv:
        rows.append([B(text="‹ لیست گروه‌ها", callback_data="gs:list")])
    rows.append([B(text="بستن", callback_data="p:close")])
    return _mk(*rows)


def panel_home_text(*, group_name: str = "", role: str = "") -> str:
    lines = [
        panel_header("🎛", "پنل مدیریت", "بخش مورد نظر را انتخاب کنید."),
    ]
    if group_name:
        lines.append(f"گروه: <b>{group_name}</b>")
    if role:
        lines.append(f"نقش: <b>{role}</b>")
    return "\n".join(lines)


# ─── قفل‌ها ──────────────────────────────────────────────────────────────────

def locks_panel_text(locks: dict, group_locked: bool = False) -> str:
    from bot.helpers import LOCK_NAMES, LOCK_ORDER
    on = [LOCK_NAMES[k] for k in LOCK_ORDER if locks.get(k)]
    return "\n".join([
        panel_header("🛡", "امنیت و قفل", "با یک ضربه وضعیت عوض می‌شود."),
        f"قفل کل گروه: <b>{'روشن' if group_locked else 'خاموش'}</b>",
        f"قفل‌های فعال: <b>{len(on)}</b>",
    ])


def locks_panel_kb(locks: dict, group_locked: bool = False) -> InlineKeyboardMarkup:
    from bot.helpers import LOCK_NAMES, LOCK_ORDER
    rows, row = [], []
    for key in LOCK_ORDER:
        label = LOCK_NAMES.get(key)
        if not label:
            continue
        row.append(B(
            text=lock_label(bool(locks.get(key)), label),
            callback_data=f"cmd:lock_toggle_{key}",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_toggle("قفل کل گروه", "group_lock", group_locked)])
    rows.append([_back("0"), _home()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── تنظیمات ─────────────────────────────────────────────────────────────────

def settings_panel_text(s: dict) -> str:
    night = s.get("night")
    night_txt = f"{night[0]}:00–{night[1]}:00" if night else "خاموش"
    return "\n".join([
        panel_header("⚙️", "تنظیمات گروه"),
        f"ربات: <b>{'روشن' if s.get('bot') else 'خاموش'}</b>",
        f"خوشامد: <b>{'روشن' if s.get('welcome') else 'خاموش'}</b>",
        f"کپچا: <b>{'روشن' if s.get('captcha') else 'خاموش'}</b>",
        f"آنتی‌فلود: <b>{'روشن' if s.get('flood') else 'خاموش'}</b>",
        f"ضد رید: <b>{'روشن' if s.get('antiraid') else 'خاموش'}</b>",
        f"حالت شب: <b>{night_txt}</b>",
    ])


def settings_panel_kb(s: dict) -> InlineKeyboardMarkup:
    return _nav(
        [_toggle("ربات", "bot", s["bot"]), _toggle("خوشامد", "welcome", s["welcome"])],
        [_toggle("کپچا", "captcha", s["captcha"]), _toggle("آنتی‌فلود", "flood", s["flood"])],
        [_toggle("ضد رید", "antiraid", s["antiraid"])],
        [_cmd("جزئیات کامل", "group_status")],
        parent="0",
    )


# ─── بازی ────────────────────────────────────────────────────────────────────

def game_panel_text(s: dict) -> str:
    theme = s.get("theme", 1)
    if s.get("fee_hidden") and not s.get("can_see_fee", True):
        fee = "مخفی"
    elif s.get("can_see_fee", True):
        fee = f"{s.get('fee', 10)}٪"
    else:
        fee = "مخفی"
    enabled = s.get("enabled_commands", set())
    games_on = sum(1 for c, _ in GAME_CMDS if c in enabled)
    fun_on = sum(1 for c, _ in FUN_CMDS if c in enabled)
    return "\n".join([
        panel_header("🎲", "بازی و سرگرمی"),
        f"سخنگو: <b>{'روشن' if s.get('speaker') else 'خاموش'}</b>",
        f"ایموجی تلگرام: <b>{'روشن' if s.get('tg_emoji') else 'خاموش'}</b>",
        f"تاس متوالی: <b>{'روشن' if s.get('dice_option') else 'خاموش'}</b>",
        f"بازی‌ها: <b>{games_on}/{len(GAME_CMDS)}</b> · سرگرمی: <b>{fun_on}/{len(FUN_CMDS)}</b>",
        f"تم تاس: <b>{theme}</b> · حق واسطه: <b>{fee}</b>",
    ])


def game_panel_kb(s: dict) -> InlineKeyboardMarkup:
    rows = [
        [_toggle("سخنگو", "speaker", s["speaker"]), _toggle("ایموجی تلگرام", "tg_emoji", s["tg_emoji"])],
        [_toggle("تاس متوالی", "dice_option", s["dice_option"])],
        [_go("بازی‌ها", "games"), _go("سرگرمی", "fun")],
        [_go("آمار", "stats")],
        [_cmd("تم تاس", "dice_theme")],
    ]
    if s.get("can_see_fee", True):
        rows.append([_cmd("حق واسطه", "fee_show")])
    return _nav(*rows, parent="0")


def games_panel_text(enabled: set) -> str:
    on = sum(1 for c, _ in GAME_CMDS if c in enabled)
    return panel_header("🎯", "بازی‌ها", f"فعال: {on} · خاموش: {len(GAME_CMDS) - on}")


def games_panel_kb(enabled: set) -> InlineKeyboardMarkup:
    return _cmds_panel_kb(GAME_CMDS, enabled, "game")


def fun_panel_text(enabled: set) -> str:
    on = sum(1 for c, _ in FUN_CMDS if c in enabled)
    return panel_header("🎭", "سرگرمی", f"فعال: {on} · خاموش: {len(FUN_CMDS) - on}")


def fun_panel_kb(enabled: set) -> InlineKeyboardMarkup:
    return _cmds_panel_kb(FUN_CMDS, enabled, "game")


# ─── اعضا ────────────────────────────────────────────────────────────────────

def manage_panel_text() -> str:
    return panel_header(
        "👥", "مدیریت اعضا",
        "برای افزودن/حذف روی پیام کاربر ریپلای کنید.",
    )


def manage_panel_kb() -> InlineKeyboardMarkup:
    return _nav(
        [_go("جوین اجباری گروه", "group_join")],
        [_go("ادمین‌ها", "admins"), _go("اعضای ویژه", "vip")],
        [_go("بن", "ban"), _go("سکوت", "mute")],
        [_cmd("تگ همه", "tag_all"), _cmd("اخطار من", "my_warnings")],
        [_cmd("مالک گروه", "owner_info"), _cmd("فیلتر کلمات", "filter_list")],
        parent="0",
    )


# ─── مالی ────────────────────────────────────────────────────────────────────

def finance_panel_text(s: dict | None = None) -> str:
    s = s or {}
    lines = [
        panel_header("💰", "مالی", "مدیریت موجودی، تسویه و گزارش."),
    ]
    if s.get("balance") is not None:
        lines.append(f"موجودی شما: <b>{int(s['balance']):,}</b> واحد")
    return "\n".join(lines)


def finance_panel_kb(s: dict | None = None) -> InlineKeyboardMarkup:
    s = s or {}
    rows = [
        [_act("درخواست افزایش", "pf:i"), _act("درخواست تسویه", "pf:w")],
        [_act("گزارش تراکنش", "pf:t"), _cmd("موجودی من", "my_balance")],
        [_act("باز کردن پنل مالی پیوی", "cmd:open_finance_pv")],
    ]
    if s.get("can_manage_finance") and s.get("can_see_sensitive", True):
        rows.append([_act("حساب ادمین‌ها", "pf:oa"), _act("فعالیت‌ها", "pf:oy")])
        rows.append([_act("حساب اعضا", "pf:oc")])
    if s.get("can_see_fee", True) and s.get("can_manage_finance"):
        rows.append([_act("حق واسطه", "pf:of")])
    elif s.get("can_see_fee", True):
        rows.append([_cmd("حق واسطه", "fee_show")])
    rows.append([_cmd("کارت مالک", "card_show")])
    return _nav(*rows, parent="0")


# ─── چالش ────────────────────────────────────────────────────────────────────

def challenges_panel_text() -> str:
    return panel_header(
        "🏆", "چالش‌ها",
        "ساخت و مدیریت چالش گروهی در پیوی ادامه می‌یابد.",
    )


def challenges_panel_kb() -> InlineKeyboardMarkup:
    return _nav(
        [_act("باز کردن پنل چالش", "pf:ch")],
        parent="0",
    )


# ─── ویژه مالک ───────────────────────────────────────────────────────────────

def owner_panel_text(s: dict) -> str:
    return "\n".join([
        panel_header("👑", "ویژه مالک", "تنظیمات خصوصی مالک گروه."),
        f"مخفی حق واسطه: <b>{'روشن' if s.get('fee_hidden') else 'خاموش'}</b>",
        f"دسترسی مالی ادمین: <b>{'روشن' if s.get('pv_admin_finance') else 'خاموش'}</b>",
    ])


def owner_panel_kb(s: dict) -> InlineKeyboardMarkup:
    rows = [
        [_act(
            toggle_label(bool(s.get("fee_hidden")), "مخفی حق واسطه"),
            "cmd:tgl_fee_hidden",
        )],
        [_act(
            toggle_label(bool(s.get("pv_admin_finance")), "دسترسی مالی ادمین"),
            "cmd:tgl_pv_admin_finance",
        )],
    ]
    if s.get("can_see_sensitive", True):
        rows.append([_act("حساب ادمین‌ها", "pf:oa"), _act("فعالیت‌ها", "pf:oy")])
        rows.append([_act("حق واسطه", "pf:of"), _act("حساب اعضا", "pf:oc")])
    return _nav(*rows, parent="0")


# ─── زیرصفحات ───────────────────────────────────────────────────────────────

def panel_admins() -> InlineKeyboardMarkup:
    return _nav(
        [_cmd("لیست ادمین‌ها", "admin_list"), _cmd("همگام‌سازی", "sync_admins")],
        parent="manage",
    )


def panel_vip() -> InlineKeyboardMarkup:
    return _nav(
        [_cmd("لیست ویژه", "vip_list"), _cmd("پاکسازی", "vip_clear")],
        parent="manage",
    )


def panel_ban() -> InlineKeyboardMarkup:
    return _nav([_cmd("لیست بن", "ban_list")], parent="manage")


def panel_mute() -> InlineKeyboardMarkup:
    return _nav([_cmd("لیست سکوت", "mute_list")], parent="manage")


def panel_stats() -> InlineKeyboardMarkup:
    return _nav(
        [_cmd("آمار تاس", "dice_stats"), _cmd("برترین‌ها", "top_users")],
        parent="game",
    )


# ─── نگاشت صفحات ─────────────────────────────────────────────────────────────

_LIVE_PAGES = {
    "locks", "1", "1.1", "settings", "game", "manage", "finance",
    "games", "fun", "owner", "challenges",
}

_STATIC_KB = {
    "": panel_main, "0": panel_main,
    "locks": lambda: locks_panel_kb({}),
    "1": lambda: locks_panel_kb({}), "1.1": lambda: locks_panel_kb({}),
    "settings": lambda: settings_panel_kb({}),
    "game": lambda: game_panel_kb({}),
    "manage": manage_panel_kb,
    "finance": lambda: finance_panel_kb({}),
    "challenges": challenges_panel_kb,
    "owner": lambda: owner_panel_kb({}),
    "admins": panel_admins, "vip": panel_vip,
    "ban": panel_ban, "mute": panel_mute,
    "games": lambda: games_panel_kb(set()), "stats": panel_stats,
    "fun": lambda: fun_panel_kb(set()),
    "cat_manage": manage_panel_kb, "cat_game": lambda: game_panel_kb({}),
    "cat_finance": lambda: finance_panel_kb({}), "cat_settings": lambda: settings_panel_kb({}),
    "2.1": panel_admins, "2.2": panel_admins, "2.3": panel_vip,
    "2.4": panel_ban, "2.5": panel_mute, "2.6": manage_panel_kb,
    "2.7": manage_panel_kb, "3": manage_panel_kb,
    "4.1": panel_stats, "4.2": lambda: games_panel_kb(set()), "4.3": panel_stats,
    "4.4": lambda: game_panel_kb({}),
    "5": manage_panel_kb, "6.1": lambda: game_panel_kb({}),
    "6.2": lambda: games_panel_kb(set()), "6.3": lambda: settings_panel_kb({}),
    "7": lambda: settings_panel_kb({}),
    "8.1": lambda: finance_panel_kb({}), "8.2": lambda: finance_panel_kb({}),
    "8.3": lambda: finance_panel_kb({}), "8.4": lambda: finance_panel_kb({}),
    "welcome": lambda: settings_panel_kb({}),
    "antispam": lambda: settings_panel_kb({}),
    "captcha": lambda: settings_panel_kb({}),
    "antiraid": lambda: settings_panel_kb({}),
}

_CAT_TEXTS = {
    "manage": manage_panel_text(),
    "finance": finance_panel_text(),
    "challenges": challenges_panel_text(),
    "admins": "👮 <b>ادمین‌ها</b>\n\nافزودن: ریپلای + <code>ادمین</code>",
    "vip": "⭐ <b>اعضای ویژه</b>\n\nافزودن: ریپلای + <code>ویژه</code>",
    "ban": "🚫 <b>بن</b>\n\nریپلای + <code>بن</code>",
    "mute": "🤫 <b>سکوت</b>\n\nریپلای + <code>سکوت</code>",
    "games": "🎯 <b>بازی‌ها</b>",
    "fun": "🎭 <b>سرگرمی</b>",
    "stats": "📊 <b>آمار</b>",
    "cat_manage": manage_panel_text(),
    "cat_game": panel_header("🎲", "بازی و سرگرمی"),
    "cat_finance": finance_panel_text(),
    "cat_settings": panel_header("⚙️", "تنظیمات گروه"),
}


def _wrap_static_kb(code: str, pv: bool = False, is_owner: bool = False):
    kb_fn = _STATIC_KB.get(code, panel_main)
    if code in ("", "0"):
        return panel_main(pv=pv, is_owner=is_owner)
    return kb_fn() if callable(kb_fn) else kb_fn


def is_live_page(code: str) -> bool:
    return code in _LIVE_PAGES


def get_static_panel(code: str, pv: bool = False, is_owner: bool = False):
    from bot.group_help import PAGES, ALIASES, _norm
    code = _norm(code).strip()
    if code not in PAGES and code in ALIASES:
        code = ALIASES[code]
    text = PAGES.get(code) or _CAT_TEXTS.get(code)
    if text is None:
        return None, None
    kb = _wrap_static_kb(code, pv=pv, is_owner=is_owner)
    return text, kb


def get_panel(code: str):
    return get_static_panel(code)
