"""مسدودسازی مالی — فقط درخواست افزایش/تسویه؛ چت گروه آزاد است."""
from __future__ import annotations

from asgiref.sync import sync_to_async

FINANCE_BAN_USER_TEXT = (
    "🚫 دسترسی شما برای ثبت درخواست افزایش موجودی و تسویه در این گروه مسدود است.\n"
    "می‌توانید در گروه چت کنید؛ برای رفع مسدودی با مدیر هماهنگ کنید."
)

_block_reason_wait: dict[int, int] = {}  # admin_id → request_id


def set_block_reason_wait(admin_id: int, request_id: int) -> None:
    _block_reason_wait[int(admin_id)] = int(request_id)


def pop_block_reason_wait(admin_id: int) -> int | None:
    return _block_reason_wait.pop(int(admin_id), None)


def is_waiting_block_reason(admin_id: int) -> bool:
    return int(admin_id) in _block_reason_wait


@sync_to_async
def is_finance_banned(chat_id: int, user_id: int) -> bool:
    from account.models import FinanceRequestBan
    return FinanceRequestBan.objects.filter(
        telegram_chat_id=int(chat_id), telegram_user_id=int(user_id),
    ).exists()


@sync_to_async
def get_finance_ban(chat_id: int, user_id: int) -> dict | None:
    from account.models import FinanceRequestBan
    row = FinanceRequestBan.objects.filter(
        telegram_chat_id=int(chat_id), telegram_user_id=int(user_id),
    ).first()
    if not row:
        return None
    return {
        "chat_id": int(row.telegram_chat_id),
        "user_id": int(row.telegram_user_id),
        "banned_by": int(row.banned_by) if row.banned_by else None,
        "reason": (row.reason or "").strip(),
    }


@sync_to_async
def ban_finance(chat_id: int, user_id: int, banned_by: int | None, reason: str) -> dict:
    from account.models import FinanceRequestBan
    obj, _ = FinanceRequestBan.objects.update_or_create(
        telegram_chat_id=int(chat_id),
        telegram_user_id=int(user_id),
        defaults={
            "banned_by": int(banned_by) if banned_by is not None else None,
            "reason": (reason or "").strip()[:500],
        },
    )
    return {
        "chat_id": int(obj.telegram_chat_id),
        "user_id": int(obj.telegram_user_id),
        "banned_by": int(obj.banned_by) if obj.banned_by else None,
        "reason": (obj.reason or "").strip(),
    }


@sync_to_async
def unban_finance(chat_id: int, user_id: int) -> bool:
    from account.models import FinanceRequestBan
    deleted, _ = FinanceRequestBan.objects.filter(
        telegram_chat_id=int(chat_id), telegram_user_id=int(user_id),
    ).delete()
    return deleted > 0


def format_group_finance_ban_announce(*, user_display: str, reason: str, admin_display: str) -> str:
    reason = (reason or "").strip() or "بدون دلیل"
    return (
        "🚫 بلاک مالی کاربر\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 کاربر: {user_display}\n"
        f"📝 دلیل: {reason}\n"
        f"🛡 توسط: {admin_display}\n\n"
        "این کاربر دیگر نمی‌تواند از پیوی درخواست افزایش یا تسویه بدهد.\n"
        "برای رفع: روی پیام کاربر ریپلای کنید و «انبلاک» بفرستید."
    )


def format_group_finance_unban_announce(*, user_display: str, admin_display: str) -> str:
    return (
        "🔓 انبلاک مالی کاربر\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 کاربر: {user_display}\n"
        f"🛡 توسط: {admin_display}\n\n"
        "دسترسی درخواست افزایش و تسویه باز شد."
    )
