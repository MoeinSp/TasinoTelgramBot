"""پسوند نقطه برای دستورات مدیریتی (حالت پنهان).

.  → انجام دستور + حذف پیام دستور + بدون پاسخ ربات
.. → همان + حذف پیام ریپلای‌شده
"""
from __future__ import annotations

import re

_SILENT_EXACT = frozenset({
    "بن", "کیک", "سیک", "ریمو", "اخراج",
    "حذف ویژه",
    "سکوت", "میوت",
    "حذف سکوت", "آن سکوت", "ان سکوت", "آنسکوت", "انسکوت",
    "آن بن", "ان بن", "آنبن", "انبن", "حذف بن",
})

_SILENT_PREFIX_RE = re.compile(
    r"^(?:"
    r"بن\s+\d+"
    r"|سکوت\s+\S+"
    r"|میوت\s+\S+"
    r"|(?:آن\s*بن|ان\s*بن|آنبن|انبن|حذف\s*بن)\s+\S+"
    r")$"
)


_TRAILING_SILENT_RE = re.compile(r"^(.*?)\s*((?:\.{1,}|…+|۔+))\s*$")


def parse_silent_suffix(text: str | None) -> tuple[str, int]:
    """(متن بدون نقطهٔ پایانی, سطح: 0|1|2).

    فاصله قبل از نقطه هم مجاز است: «سیک ..» یا «سیک..» یا «سیک...»
    """
    raw = (text or "").rstrip()
    m = _TRAILING_SILENT_RE.match(raw)
    if not m:
        return raw, 0
    body = m.group(1).rstrip()
    suffix = m.group(2) or ""
    level = 2 if ("…" in suffix or "۔" in suffix or suffix.count(".") >= 2) else 1
    return body, level


def is_silentable_command(clean_text: str) -> bool:
    t = (clean_text or "").replace("\u200c", " ").strip()
    t = " ".join(t.split())
    if not t:
        return False
    if t in _SILENT_EXACT:
        return True
    return bool(_SILENT_PREFIX_RE.match(t))


def apply_silent_suffix(text: str | None) -> tuple[str, int]:
    clean, level = parse_silent_suffix(text)
    if level and is_silentable_command(clean):
        return clean, level
    return (text or ""), 0


async def apply_silent_deletes(bot, chat_id, cmd_message_id, reply_message_id, level: int) -> None:
    if level < 1:
        return
    if cmd_message_id is not None:
        try:
            await bot.delete_message(chat_id, cmd_message_id)
        except Exception:
            pass
    if level >= 2 and reply_message_id is not None:
        try:
            await bot.delete_message(chat_id, reply_message_id)
        except Exception:
            pass
