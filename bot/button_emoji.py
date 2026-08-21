"""
آیکون ایموجی پرمیوم (custom emoji) برای دکمه‌های شیشه‌ای (inline).

مکانیک تلگرام:
  InlineKeyboardButton یک فیلد `icon_custom_emoji_id` دارد که یک ایموجی پرمیوم را
  *قبل از* متن دکمه نشان می‌دهد (نیازمند Premium مالک؛ کلاینت‌های خیلی قدیمی فقط متن
  را می‌بینند).

قانون طلایی:
  یک دکمه یا `icon_custom_emoji_id` دارد یا ایموجی literal داخل متن — هیچ‌وقت هر دو،
  چون تلگرام آیکون را قبل از متن می‌کشد و دوتا نشان داده می‌شود. برای همین `btn()` یک
  `emoji_key` می‌گیرد، نه یک label از پیش‌ایموجی‌دار.

منبع داده:
  مدل bot_setting.ButtonEmojiOverride (key → custom_emoji_id, placeholder).
  نبودِ ردیف = فقط فالبک یونیکد از BUTTON_EMOJI_DEFS.

کش:
  overrideها در همین پراسس در `_OVERRIDES` کش می‌شوند. هر تغییر باید کش را رفرش کند
  (set/clear این کار را می‌کنند). اگر تغییر از پراسس دیگری (مثلاً وب/management) اعمال
  شود، پراسس بات باید ری‌استارت شود تا کش را دوباره از DB بخواند.
"""
from __future__ import annotations

from asgiref.sync import sync_to_async
from aiogram.types import InlineKeyboardButton, Message


# ─── A) رجیستری دکمه‌ها ────────────────────────────────────────────────────
# key → (label, unicode_fallback, category)
# category فقط برای دسته‌بندی در پنل است.
BUTTON_EMOJI_DEFS: dict[str, tuple[str, str, str]] = {
    # nav — ناوبری منوی اصلی
    "btn_games":       ("بازی‌ها", "🎮", "nav"),
    "btn_help":        ("راهنما", "📚", "nav"),
    "btn_channels":    ("کانال‌ها", "📣", "nav"),
    "btn_support":     ("پشتیبانی", "💬", "nav"),
    "btn_back":        ("بازگشت", "🔙", "nav"),
    "btn_home":        ("خانه", "🏠", "nav"),

    # games — بازی‌ها
    "game_dice":       ("تاس", "🎲", "games"),
    "game_dart":       ("دارت", "🎯", "games"),
    "game_basketball": ("بسکتبال", "🏀", "games"),
    "game_penalty":    ("پنالتی", "⚽", "games"),
    "game_bowling":    ("بولینگ", "🎳", "games"),
    "game_slots":      ("اسلات", "🎰", "games"),
    "game_coin":       ("سکه", "🪙", "games"),
    "game_rps":        ("سنگ کاغذ قیچی", "✂️", "games"),
    "game_luck":       ("شانس", "🍀", "games"),

    # help — دسته‌های راهنما
    "help_locks":      ("قفل‌ها", "🔒", "help"),
    "help_members":    ("اعضا", "👥", "help"),
    "help_warnings":   ("اخطارها", "⚠️", "help"),
    "help_mute":       ("سکوت", "🔇", "help"),
    "help_games":      ("بازی‌ها", "🎮", "help"),
    "help_filter":     ("فیلتر کلمه", "🔤", "help"),

    # panel — پنل مدیریت گروه
    "panel_locks":     ("قفل‌ها", "🔒", "panel"),
    "panel_settings":  ("تنظیمات", "⚙️", "panel"),
    "panel_game":      ("بازی", "🎲", "panel"),
    "panel_games":     ("بازی‌ها", "🎮", "panel"),
    "panel_fun":       ("سرگرمی", "🎉", "panel"),
    "panel_manage":    ("مدیریت", "🛠", "panel"),
    "panel_finance":   ("مالی", "💰", "panel"),
    "panel_challenges":("چالش‌ها", "🏆", "panel"),
    "panel_owner":     ("مالک", "👑", "panel"),
}

# ست‌های custom-emoji پرمیومِ مالک — منبعِ پیش‌فرضِ کشف برای assign خودکار.
# بات لازم نیست مالکِ این ست‌ها باشد؛ getStickerSet با نام، برای هر بات کار می‌کند.
OWNER_EMOJI_SETS: list[str] = [
    "MeowieQ",
    "NewsEmoji",
    "DecorationEmojiPack",
    "pk_2128353_by_EmojiRuBot",
    "mamali01_by_TgEmojis_bot",
    "yandex_adv",
    "pack_90fb6_by_TgEmojis_bot",
]

# ─── مپ اختیاری key → ایموجیِ بهترِ خودکارسازی ──────────────────────────────
# اگر فالبکِ رجیستری بهترین انتخاب برای auto-assign نباشد، این‌جا override کن.
# نبود key در این مپ = از فالبکِ BUTTON_EMOJI_DEFS استفاده می‌شود.
PREFERRED: dict[str, str] = {
    "btn_support": "💬",
    "panel_owner": "👑",
    "panel_finance": "💰",
    "panel_challenges": "🏆",
}


# ─── F) کش in-memory ───────────────────────────────────────────────────────
# key → {"id": custom_emoji_id, "placeholder": str}
_OVERRIDES: dict[str, dict] = {}


def apply_button_emoji_cache(rows: list[dict] | None) -> None:
    """کش را از یک لیست ردیف ({key,id,placeholder}) می‌سازد."""
    _OVERRIDES.clear()
    for row in rows or []:
        key = str(row.get("key") or "").strip()
        eid = str(row.get("custom_emoji_id") or row.get("id") or "").strip()
        if key and eid.isdigit():
            _OVERRIDES[key] = {
                "id": eid,
                "placeholder": str(row.get("placeholder") or "").strip(),
            }


def get_override(emoji_key: str) -> dict | None:
    return _OVERRIDES.get((emoji_key or "").strip())


def fallback_of(emoji_key: str) -> str:
    row = BUTTON_EMOJI_DEFS.get(emoji_key)
    return row[1] if row else ""


# ─── C) سازنده دکمه ────────────────────────────────────────────────────────
def btn(label: str, emoji_key: str | None = None, **kwargs) -> InlineKeyboardButton:
    """
    یک InlineKeyboardButton می‌سازد.

    - اگر emoji_key داده شود و override پرمیوم داشته باشد → icon_custom_emoji_id ست
      می‌شود و ایموجی literal به label اضافه نمی‌شود.
    - در غیر این صورت فالبکِ یونیکد قبل از label اضافه می‌شود.
    - اگر emoji_key نامعتبر/None باشد، دقیقاً همان label ساخته می‌شود (بدون تغییر).
    """
    if emoji_key:
        override = get_override(emoji_key)
        if override:
            return InlineKeyboardButton(
                text=label,
                icon_custom_emoji_id=override["id"],
                **kwargs,
            )
        fallback = fallback_of(emoji_key)
        if fallback:
            label = f"{fallback} {label}"
    return InlineKeyboardButton(text=label, **kwargs)


# ─── B/F) لایه دیتابیس ─────────────────────────────────────────────────────
@sync_to_async
def load_button_emoji_from_db() -> None:
    """کش را از DB بارگذاری می‌کند (در startup و بعد از هر تغییر)."""
    from bot_setting.models import ButtonEmojiOverride
    rows = list(
        ButtonEmojiOverride.objects.values("key", "custom_emoji_id", "placeholder")
    )
    apply_button_emoji_cache(rows)


def _reload_cache_sync() -> None:
    from bot_setting.models import ButtonEmojiOverride
    rows = list(
        ButtonEmojiOverride.objects.values("key", "custom_emoji_id", "placeholder")
    )
    apply_button_emoji_cache(rows)


@sync_to_async
def set_button_emoji(key: str, custom_emoji_id: str, placeholder: str = "") -> bool:
    """override را ذخیره/به‌روزرسانی و کش همین پراسس را رفرش می‌کند."""
    from bot_setting.models import ButtonEmojiOverride
    key = (key or "").strip()
    eid = (custom_emoji_id or "").strip()
    if not key or not eid.isdigit() or key not in BUTTON_EMOJI_DEFS:
        return False
    ButtonEmojiOverride.objects.update_or_create(
        key=key,
        defaults={"custom_emoji_id": eid, "placeholder": (placeholder or "").strip()[:16]},
    )
    _reload_cache_sync()
    return True


@sync_to_async
def clear_button_emoji(key: str) -> bool:
    """override را حذف (بازگشت به فالبک) و کش را رفرش می‌کند."""
    from bot_setting.models import ButtonEmojiOverride
    key = (key or "").strip()
    deleted, _ = ButtonEmojiOverride.objects.filter(key=key).delete()
    _reload_cache_sync()
    return bool(deleted)


# ─── D) استخراج ایموجی پرمیوم از پیام ──────────────────────────────────────
def extract_first_custom_emoji(message: Message) -> tuple[str | None, str | None]:
    """
    اولین entity از نوع custom_emoji را برمی‌گرداند: (custom_emoji_id, placeholder).
    placeholder = متنِ زیرِ entity (همان ایموجی پایه).
    """
    entities = list(message.entities or []) + list(message.caption_entities or [])
    text = message.text or message.caption or ""
    for ent in entities:
        if getattr(ent, "type", None) != "custom_emoji":
            continue
        eid = getattr(ent, "custom_emoji_id", None)
        if not eid:
            continue
        try:
            chunk = text.encode("utf-16-le")
            start = ent.offset * 2
            end = (ent.offset + ent.length) * 2
            placeholder = chunk[start:end].decode("utf-16-le")
        except Exception:
            placeholder = ""
        return str(eid), placeholder
    return None, None


# ─── کمکی‌های پنل ──────────────────────────────────────────────────────────
CATEGORY_LABELS: dict[str, str] = {
    "nav": "🧭 ناوبری",
    "games": "🎮 بازی‌ها",
    "help": "📚 راهنما",
    "panel": "🛠 پنل مدیریت",
}


def categories() -> list[str]:
    seen: list[str] = []
    for _, _, cat in BUTTON_EMOJI_DEFS.values():
        if cat not in seen:
            seen.append(cat)
    return seen


def keys_in_category(category: str) -> list[str]:
    return [k for k, (_, _, cat) in BUTTON_EMOJI_DEFS.items() if cat == category]


def button_status(key: str) -> dict:
    row = BUTTON_EMOJI_DEFS.get(key)
    label = row[0] if row else key
    fallback = row[1] if row else "⭐"
    override = get_override(key)
    return {
        "key": key,
        "label": label,
        "fallback": fallback,
        "id": override["id"] if override else None,
        "placeholder": (override or {}).get("placeholder") or fallback,
        "set": bool(override),
    }
