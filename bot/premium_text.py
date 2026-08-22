"""
ارتقای خودکارِ ایموجیِ خروجی به پرمیوم — به‌صورت مرکزی روی همه‌ی پیام‌ها.

دو کار:
  ۱) در متنِ HTML، ایموجیِ literal را به `<tg-emoji emoji-id=...>` (پرمیوم) تبدیل می‌کند.
  ۲) در دکمه‌های اینلاین، ایموجیِ ابتدای متنِ دکمه را به `icon_custom_emoji_id` تبدیل و از
     متن حذف می‌کند (قانون طلایی: یا آیکون یا متن — نه هر دو).

نقشه‌ی `emoji → custom_emoji_id` از ست‌های پرمیومِ خودِ مالک ساخته می‌شود
(bot.button_emoji.OWNER_EMOJI_SETS). بات لازم نیست مالکِ ست باشد.

ایمنی: همه‌چیز در try/except؛ اگر ارتقا یا ارسالِ ارتقایافته خطا داد، پیامِ اصلی
دست‌نخورده فرستاده می‌شود (میدل‌ویر با restore + retry).
"""
from __future__ import annotations

import html
import logging
import re

logger = logging.getLogger(__name__)

VS16 = "️"

# emoji → custom_emoji_id
_EMOJI_MAP: dict[str, str] = {}
_PATTERN: re.Pattern | None = None
_LEADING_PATTERN: re.Pattern | None = None

# سقفِ تعدادِ ایموجیِ تبدیل‌شده در هر پیام (زیرِ محدودیتِ entityهای تلگرام)
MAX_PER_MESSAGE = 40


def _rebuild_patterns() -> None:
    global _PATTERN, _LEADING_PATTERN
    if not _EMOJI_MAP:
        _PATTERN = None
        _LEADING_PATTERN = None
        return
    # طولانی‌ترین اول، تا نسخه‌ی با VS16 قبل از بدونِ آن مچ شود
    keys = sorted(_EMOJI_MAP.keys(), key=len, reverse=True)
    alt = "|".join(re.escape(k) for k in keys)
    _PATTERN = re.compile(alt)
    _LEADING_PATTERN = re.compile(r"^\s*(" + alt + r")\s*")


# هم‌ارزهای هم‌شکل: گلیف‌هایی که در ست‌های مالک نیستند ولی معادلِ بصریِ نزدیک دارند.
# فقط جایگزین‌های واضح (فلش/دایره/بازخوانی) — تزئین‌های ظریف دست‌نخورده می‌مانند.
ALIASES: dict[str, str] = {
    "→": "➡️",
    "←": "⬅️",
    "↻": "🔄",
    "⟳": "🔄",
    "⬤": "⚫",
}


def apply_emoji_map(mapping: dict[str, str]) -> None:
    _EMOJI_MAP.clear()
    for emoji, eid in (mapping or {}).items():
        if emoji and str(eid).isdigit():
            _EMOJI_MAP[emoji] = str(eid)
            stripped = emoji.replace(VS16, "")
            if stripped and stripped != emoji:
                _EMOJI_MAP.setdefault(stripped, str(eid))
    # هم‌ارزها روی نقشه‌ی ساخته‌شده می‌نشینند
    for src, tgt in ALIASES.items():
        eid = _EMOJI_MAP.get(tgt) or _EMOJI_MAP.get(tgt.replace(VS16, ""))
        if eid and src not in _EMOJI_MAP:
            _EMOJI_MAP[src] = eid
    _rebuild_patterns()


def map_size() -> int:
    return len(_EMOJI_MAP)


async def load_emoji_map(bot) -> int:
    """نقشه را از ست‌های مالک می‌سازد (در startup). تعدادِ ایموجی را برمی‌گرداند."""
    from bot.button_emoji import OWNER_EMOJI_SETS
    mapping: dict[str, str] = {}
    for name in OWNER_EMOJI_SETS:
        try:
            ss = await bot.get_sticker_set(name)
        except Exception as exc:
            logger.warning("load_emoji_map: getStickerSet(%s) failed: %s", name, exc)
            continue
        for s in ss.stickers:
            emoji = getattr(s, "emoji", None)
            cid = getattr(s, "custom_emoji_id", None)
            if emoji and cid:
                mapping.setdefault(emoji, str(cid))
    apply_emoji_map(mapping)
    logger.info("Premium text emoji map loaded: %d emojis", map_size())
    return map_size()


def get_id_for(emoji: str) -> str | None:
    return _EMOJI_MAP.get(emoji) or _EMOJI_MAP.get((emoji or "").replace(VS16, ""))


# ─── ارتقای متن ────────────────────────────────────────────────────────────
def upgrade_html_text(text: str | None) -> str | None:
    """ایموجیِ literal را در متنِ HTML به tg-emoji تبدیل می‌کند (فقط ایموجی‌های نقشه)."""
    if not text or _PATTERN is None:
        return text
    if "<tg-emoji" in text:
        return text  # قبلاً پرمیوم‌دار/دست‌ساز — دست نزن

    count = 0

    def _sub(m: re.Match) -> str:
        nonlocal count
        if count >= MAX_PER_MESSAGE:
            return m.group(0)
        emoji = m.group(0)
        eid = _EMOJI_MAP.get(emoji)
        if not eid:
            return emoji
        count += 1
        return f'<tg-emoji emoji-id="{eid}">{emoji}</tg-emoji>'

    return _PATTERN.sub(_sub, text)


def has_mapped_emoji(text: str | None) -> bool:
    """آیا متن حداقل یک ایموجیِ موجود در نقشه دارد؟"""
    if not text or _PATTERN is None:
        return False
    return _PATTERN.search(text) is not None


def upgrade_plain_text(text: str | None) -> str | None:
    """
    متنِ ساده (parse_mode=None) را به HTML امن تبدیل می‌کند: کلِ متن escape می‌شود
    (پس < & > همان‌طور literal می‌مانند) و ایموجی‌ها به tg-emoji تبدیل می‌شوند.
    اگر ایموجیِ قابل‌ارتقا نباشد None برمی‌گرداند (یعنی دست نزن).
    """
    if not has_mapped_emoji(text):
        return None
    escaped = html.escape(text, quote=False)
    return upgrade_html_text(escaped)


# ─── ارتقای دکمه‌ها ────────────────────────────────────────────────────────
def _split_leading_emoji(text: str) -> tuple[str, str] | None:
    """(emoji, rest) اگر متن با ایموجیِ نقشه شروع شود و rest غیرخالی باشد."""
    if not text or _LEADING_PATTERN is None:
        return None
    m = _LEADING_PATTERN.match(text)
    if not m:
        return None
    emoji = m.group(1)
    rest = text[m.end():]
    if not rest.strip():
        return None  # دکمه‌ی فقط‌ایموجی (مثل ◀️) — نباید متن خالی شود
    return emoji, rest


def upgrade_inline_markup(markup) -> bool:
    """
    روی InlineKeyboardMarkup: دکمه‌هایی که آیکون ندارند و متنشان با ایموجیِ نقشه شروع
    می‌شود را به icon_custom_emoji_id تبدیل می‌کند. True اگر چیزی عوض شد.
    """
    rows = getattr(markup, "inline_keyboard", None)
    if not rows:
        return False
    changed = False
    for row in rows:
        for btn in row:
            if getattr(btn, "icon_custom_emoji_id", None):
                continue
            split = _split_leading_emoji(getattr(btn, "text", "") or "")
            if not split:
                continue
            emoji, rest = split
            eid = get_id_for(emoji)
            if not eid:
                continue
            try:
                btn.text = rest.strip()
                btn.icon_custom_emoji_id = eid
                changed = True
            except Exception:
                # اگر مدل قابل‌تغییر نبود، بی‌خیالِ این دکمه شو
                continue
    return changed
