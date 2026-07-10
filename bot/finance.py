"""سیستم مالی — موجودی در point + لاگ WalletTransaction (مثل rubpy)."""
from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import transaction as db_transaction
from django.utils import timezone


def _get_or_create_member(chat_id: int, user_id: int):
    from account.models import TelegramGroup, TelegramGroupMember
    grp, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=chat_id, defaults={"name": ""},
    )
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id,
        telegram_user_id=user_id,
        defaults={"group": grp, "role": "member"},
    )
    return m


def _log_tx(chat_id, user_id, tx_type, amount, balance_after, admin_id=None, description=""):
    from account.models import WalletTransaction
    WalletTransaction.objects.create(
        telegram_chat_id=chat_id,
        telegram_user_id=user_id,
        admin_id=admin_id,
        type=tx_type,
        amount=amount,
        balance_after=balance_after,
        description=description or "",
    )


@sync_to_async
def record_fee_income(
    chat_id: int, user_id: int, amount: int,
    admin_id: int | None = None, description: str | None = None,
) -> int:
    """ثبت درآمد حق واسطه بدون تغییر موجودی کیف پول."""
    m = _get_or_create_member(chat_id, user_id)
    bal = m.point or 0
    _log_tx(chat_id, user_id, "fee", amount, bal, admin_id, description)
    return bal


@sync_to_async
def get_balance(chat_id: int, user_id: int) -> int:
    from account.models import TelegramGroupMember
    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
    ).first()
    return (m.point or 0) if m else 0


@sync_to_async
def increase_wallet(
    chat_id: int, user_id: int, amount: int,
    admin_id: int | None = None, description: str | None = None,
) -> int:
    with db_transaction.atomic():
        m = _get_or_create_member(chat_id, user_id)
        m.point = (m.point or 0) + amount
        m.save(update_fields=["point"])
        _log_tx(chat_id, user_id, "admin_increase", amount, m.point, admin_id, description)
        return m.point


@sync_to_async
def decrease_wallet(
    chat_id: int, user_id: int, amount: int,
    admin_id: int | None = None, description: str | None = None,
) -> int:
    with db_transaction.atomic():
        m = _get_or_create_member(chat_id, user_id)
        m.point = (m.point or 0) - amount
        m.save(update_fields=["point"])
        _log_tx(chat_id, user_id, "admin_decrease", amount, m.point, admin_id, description)
        return m.point


@sync_to_async
def clear_wallet(chat_id: int, user_id: int, admin_id: int | None = None) -> int:
    with db_transaction.atomic():
        m = _get_or_create_member(chat_id, user_id)
        old = m.point or 0
        m.point = 0
        m.save(update_fields=["point"])
        if old != 0:
            _log_tx(chat_id, user_id, "admin_clear", abs(old), 0, admin_id)
        return old


@sync_to_async
def record_game_bet(chat_id: int, user_id: int, amount: int) -> int:
    with db_transaction.atomic():
        m = _get_or_create_member(chat_id, user_id)
        m.point = (m.point or 0) - amount
        m.save(update_fields=["point"])
        _log_tx(chat_id, user_id, "bet", amount, m.point)
        return m.point


@sync_to_async
def record_game_win(chat_id: int, user_id: int, amount: int) -> int:
    with db_transaction.atomic():
        m = _get_or_create_member(chat_id, user_id)
        m.point = (m.point or 0) + amount
        m.save(update_fields=["point"])
        _log_tx(chat_id, user_id, "win", amount, m.point)
        return m.point


@sync_to_async
def get_active_accounts(chat_id: int) -> list[dict]:
    from account.models import TelegramGroupMember
    qs = (
        TelegramGroupMember.objects
        .filter(telegram_chat_id=chat_id)
        .exclude(point=0)
        .exclude(point__isnull=True)
        .order_by("-point")
    )
    return list(qs.values("telegram_user_id", "alias", "point"))


@sync_to_async
def get_transactions(chat_id: int, user_id: int, limit: int = 5, offset: int = 0) -> list:
    from account.models import WalletTransaction
    return list(
        WalletTransaction.objects.filter(
            telegram_chat_id=chat_id, telegram_user_id=user_id,
        ).order_by("-id")[offset:offset + limit]
    )


@sync_to_async
def get_transactions_count(chat_id: int, user_id: int) -> int:
    from account.models import WalletTransaction
    return WalletTransaction.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
    ).count()


@sync_to_async
def clear_all_wallets(chat_id: int, admin_id: int | None = None) -> list[tuple[int, int]]:
    """تسویه همه — برمی‌گرداند [(user_id, cleared_amount), ...]"""
    from account.models import TelegramGroupMember
    results = []
    with db_transaction.atomic():
        members = list(
            TelegramGroupMember.objects.filter(telegram_chat_id=chat_id)
            .exclude(point=0).exclude(point__isnull=True)
        )
        for m in members:
            old = m.point or 0
            m.point = 0
            m.save(update_fields=["point"])
            _log_tx(chat_id, m.telegram_user_id, "admin_clear", abs(old), 0, admin_id)
            results.append((m.telegram_user_id, old))
    return results


@sync_to_async
def get_fee_report(
    chat_id: int,
    days: int = 7,
    target_user_id: int | None = None,
    day_offset: int | None = None,
) -> dict:
    from datetime import timedelta
    from account.models import WalletTransaction

    today = timezone.localdate()
    qs = WalletTransaction.objects.filter(
        telegram_chat_id=chat_id,
        type="fee",
    )
    if day_offset is not None:
        target_date = today - timedelta(days=day_offset)
        qs = qs.filter(created_at__date=target_date)
        start_date = end_date = target_date
    else:
        start_date = today - timedelta(days=max(0, days - 1))
        end_date = today
        qs = qs.filter(created_at__date__gte=start_date)
    if target_user_id:
        qs = qs.filter(telegram_user_id=target_user_id)

    per_day = {}
    per_admin = {}
    total_fee = 0

    for tx in qs.order_by("created_at"):
        d = timezone.localtime(tx.created_at).date().isoformat()
        per_day[d] = per_day.get(d, 0) + int(tx.amount or 0)
        aid = int(tx.telegram_user_id)
        per_admin[aid] = per_admin.get(aid, 0) + int(tx.amount or 0)
        total_fee += int(tx.amount or 0)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_fee": total_fee,
        "per_day": per_day,
        "per_admin": per_admin,
    }
