"""سکوت علت‌دار با تشدید: ۳۰ دقیقه → ۶ ساعت → ۲۴ ساعت."""
from __future__ import annotations

REASON_MUTE_MINUTES = (30, 6 * 60, 24 * 60)


def _strike_key(chat_id: int, user_id: int) -> str:
    return f"mute_strike:{int(chat_id)}:{int(user_id)}"


def get_strike_level(chat_id: int, user_id: int) -> int:
    try:
        from django.core.cache import cache
        raw = cache.get(_strike_key(chat_id, user_id))
        return max(0, int(raw or 0))
    except Exception:
        return 0


def bump_strike(chat_id: int, user_id: int) -> int:
    level = get_strike_level(chat_id, user_id)
    try:
        from django.core.cache import cache
        cache.set(_strike_key(chat_id, user_id), level + 1, timeout=None)
    except Exception:
        pass
    return level


def minutes_for_strike(level: int) -> int:
    idx = min(max(0, int(level)), len(REASON_MUTE_MINUTES) - 1)
    return int(REASON_MUTE_MINUTES[idx])


def format_reason_mute_user_text(reason: str, minutes: int, level: int) -> str:
    reason = (reason or "تخلف").strip() or "تخلف"
    if minutes >= 60 and minutes % 60 == 0:
        dur = f"{minutes // 60} ساعت"
    else:
        dur = f"{minutes} دقیقه"
    if level <= 0:
        next_hint = "در صورت تکرار مدت سکوت به ۶ ساعت افزایش پیدا می‌کند."
    elif level == 1:
        next_hint = "در صورت تکرار مدت سکوت به ۲۴ ساعت افزایش پیدا می‌کند."
    else:
        next_hint = "در صورت تکرار مجدد، سکوت ۲۴ ساعته اعمال می‌شود."
    return (
        f"کاربر عزیز، به علت «{reason}» تا {dur} سکوت شدید.\n"
        f"{next_hint}"
    )


def format_reason_mute_group_text(mention: str, reason: str, minutes: int, level: int) -> str:
    reason = (reason or "تخلف").strip() or "تخلف"
    if minutes >= 60 and minutes % 60 == 0:
        dur = f"{minutes // 60} ساعت"
    else:
        dur = f"{minutes} دقیقه"
    return (
        f"› {mention}\n\n"
        f"›› به علت «{reason}» به مدت [ {dur} ] سکوت شد.\n"
        f"›› سطح تکرار: {level + 1}"
    )


def apply_reason_mute(chat_id: int, user_id: int, reason: str) -> dict:
    level = bump_strike(chat_id, user_id)
    minutes = minutes_for_strike(level)
    reason = (reason or "").strip()
    return {
        "minutes": minutes,
        "level": level,
        "reason": reason,
        "user_text": format_reason_mute_user_text(reason, minutes, level),
    }
