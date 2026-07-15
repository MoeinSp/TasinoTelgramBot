"""الگوی یکدست UI پنل‌ها — هدر کوتاه و تیک‌های خوانا."""
from __future__ import annotations

from bot.constants import CREATOR_USER_ID

SEP = "━━━━━━━━━━━━━━━━━━"


def panel_header(icon: str, title: str, subtitle: str = "") -> str:
    lines = [f"{icon} <b>{title}</b>", SEP]
    if subtitle:
        lines.append(subtitle)
        lines.append("")
    return "\n".join(lines)


def toggle_label(on: bool, name: str) -> str:
    """برچسب تیک: «روشن · نام» / «خاموش · نام»"""
    state = "روشن" if on else "خاموش"
    return f"{state} · {name}"


def lock_label(on: bool, name: str) -> str:
    return f"{'قفل' if on else 'باز'} · {name}"


def is_creator(user_id) -> bool:
    try:
        return int(user_id) == int(CREATOR_USER_ID)
    except (TypeError, ValueError):
        return False


def is_admin_sensitive_hidden() -> bool:
    from bot import cache
    return bool(cache.SITE_CONFIG.get("admin_sensitive_hidden", False))


def can_see_sensitive_finance(
    user_id,
    chat_id,
    *,
    is_owner_flag: bool | None = None,
    fee_hidden: bool = False,
) -> bool:
    """
    حق واسطه / فعالیت / حساب ادمین / گزارش مالک.
    مالک و سازنده همیشه؛ ادمین فقط اگر پرچم سازنده خاموش باشد.
    """
    from bot.cache_manager import is_owner as _is_owner

    if is_creator(user_id):
        return True
    owner = bool(is_owner_flag) if is_owner_flag is not None else _is_owner(chat_id, user_id)
    if owner:
        return True
    if is_admin_sensitive_hidden():
        return False
    return True


def can_see_fee(
    user_id,
    chat_id,
    *,
    is_owner_flag: bool | None = None,
    fee_hidden: bool = False,
) -> bool:
    """حق واسطه: مخفی مالک OR مخفی سازنده → ادمین نمی‌بیند."""
    from bot.cache_manager import is_owner as _is_owner

    if is_creator(user_id):
        return True
    owner = bool(is_owner_flag) if is_owner_flag is not None else _is_owner(chat_id, user_id)
    if owner:
        return True
    if fee_hidden or is_admin_sensitive_hidden():
        return False
    return True
