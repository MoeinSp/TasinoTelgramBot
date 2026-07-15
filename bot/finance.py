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


def _log_tx(chat_id, user_id, tx_type, amount, balance_after, admin_id=None, description="", receipt_file_id="", receipt_note=""):
    from account.models import WalletTransaction
    WalletTransaction.objects.create(
        telegram_chat_id=chat_id,
        telegram_user_id=user_id,
        admin_id=admin_id,
        type=tx_type,
        amount=amount,
        balance_after=balance_after,
        description=description or "",
        receipt_file_id=receipt_file_id or "",
        receipt_note=receipt_note or "",
    )


def with_game_id(
    base: str,
    game_no: int | None,
    *,
    opponent_name: str | None = None,
    invite_id: str | None = None,
) -> str:
    """متن توضیح تراکنش با آیدی بازی مشترک برای وصل کسر/برد."""
    text = (base or "").strip() or "مسابقه تاس"
    name = (opponent_name or "").strip()[:40]
    if name:
        text = f"{text} · حریف: {name}"
    if invite_id:
        text = f"{text} · دعوت:{str(invite_id).strip()}"
    if game_no is None:
        return text[:250]
    return f"{text} · آیدی بازی {int(game_no)}"[:250]


@sync_to_async
def allocate_game_no(chat_id: int) -> int:
    """شماره یکتای ترتیبی بازی در این گروه."""
    from django.db.models import F
    from account.models import TelegramGroup

    g, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=int(chat_id), defaults={"name": ""},
    )
    TelegramGroup.objects.filter(pk=g.pk).update(game_seq=F("game_seq") + 1)
    g.refresh_from_db(fields=["game_seq"])
    return int(g.game_seq or 0)


@sync_to_async
def record_fee_income(
    chat_id: int, user_id: int, amount: int,
    admin_id: int | None = None, description: str | None = None,
) -> int:
    """
    فقط لاگ آماری حق واسطه — موجودی کیف پول ادمین/واسطه تغییر نمی‌کند.
    """
    from account.models import AdminAccounting

    amount = abs(int(amount or 0))
    if amount <= 0:
        return 0
    aid = int(admin_id or user_id)
    m = _get_or_create_member(chat_id, aid)
    bal = m.point or 0
    _log_tx(chat_id, aid, "fee", amount, bal, aid, description)
    AdminAccounting.objects.get_or_create(
        telegram_chat_id=int(chat_id),
        admin_id=aid,
        defaults={"share_percent": 50},
    )
    return bal


@sync_to_async
def get_balance(chat_id: int, user_id: int) -> int:
    from account.models import TelegramGroupMember
    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
    ).first()
    return (m.point or 0) if m else 0


@sync_to_async
def get_pending_withdrawal_sum(chat_id: int, user_id: int) -> int:
    from django.db.models import Sum
    from account.models import WithdrawalRequest

    total = (
        WithdrawalRequest.objects.filter(
            telegram_chat_id=int(chat_id),
            telegram_user_id=int(user_id),
            status__in=("pending", "receipt"),
        ).aggregate(total=Sum("amount"))["total"]
    )
    return int(total or 0)


async def get_playable_balance(chat_id: int, user_id: int) -> tuple[int, int, int]:
    """(موجودی کل، قابل استفاده، در انتظار تسویه)"""
    total = await get_balance(chat_id, user_id)
    pending = await get_pending_withdrawal_sum(chat_id, user_id)
    playable = max(0, total - pending)
    return total, playable, pending


def format_balance_card(
    *,
    playable: int,
    pending: int = 0,
    time_str: str = "",
    viewer_name: str = "",
    viewing_other: bool = False,
    html: bool = False,
) -> str:
    """کارت موجودی — فقط اگر تسویه معلق باشد خط آن را نشان می‌دهد."""
    lines = ["💳 موجودی حساب", "━━━━━━━━━━━━━━━━━━"]
    if viewing_other and viewer_name:
        name = viewer_name if not html else viewer_name  # caller escapes if needed
        lines.append(f"👤 {name}")
    if playable < 0:
        lines.append(f"✅ موجودی مجاز: 🔻 {abs(playable):,} بدهکار")
    else:
        lines.append(f"✅ موجودی مجاز: {playable:,} واحد")
    if int(pending or 0) > 0:
        lines.append(f"⏳ در حال تسویه: {int(pending):,} واحد")
    lines.append("━━━━━━━━━━━━━━━━━━")
    if time_str:
        lines.append(f"🕒 {time_str}")
    if int(pending or 0) > 0 and not viewing_other:
        lines.append("")
        lines.append("💡 از ادمین بخواهید درخواست تسویه شما را تأیید کند.")
    return "\n".join(lines)


def format_insufficient_balance_message(
    *,
    entry_cost: int,
    total_balance: int,
    playable: int,
    pending: int,
    fee_line: str = "",
) -> str:
    if pending > 0:
        balance_lines = (
            f"💰 موجودی: {playable:,} واحد\n"
            f"⏳ موجودی در انتظار تسویه: {pending:,} واحد"
        )
        shortfall = entry_cost - playable
    else:
        balance_lines = f"💰 موجودی فعلی شما: {total_balance:,} واحد"
        shortfall = entry_cost - total_balance

    return (
        f"❌ موجودی ناکافی!\n\n"
        f"💳 هزینه ورودی: {entry_cost:,} واحد{fee_line}\n\n"
        f"{balance_lines}\n"
        f"🔻 کمبود: {shortfall:,} واحد\n\n"
        f"💡 برای افزایش موجودی با ادمین تماس بگیرید."
    )


@sync_to_async
def increase_wallet(
    chat_id: int, user_id: int, amount: int,
    admin_id: int | None = None, description: str | None = None,
    receipt_file_id: str | None = None, receipt_note: str | None = None,
) -> int:
    with db_transaction.atomic():
        m = _get_or_create_member(chat_id, user_id)
        m.point = (m.point or 0) + amount
        m.save(update_fields=["point"])
        _log_tx(chat_id, user_id, "admin_increase", amount, m.point, admin_id, description, receipt_file_id, receipt_note)
        try:
            if "جایزه چالش" not in (description or ""):
                from bot.challenges import record_increase_silent
                record_increase_silent(chat_id, user_id, amount)
        except Exception:
            pass
        return m.point


@sync_to_async
def decrease_wallet(
    chat_id: int, user_id: int, amount: int,
    admin_id: int | None = None, description: str | None = None,
    receipt_file_id: str | None = None, receipt_note: str | None = None,
) -> int:
    with db_transaction.atomic():
        m = _get_or_create_member(chat_id, user_id)
        m.point = (m.point or 0) - amount
        m.save(update_fields=["point"])
        _log_tx(chat_id, user_id, "admin_decrease", amount, m.point, admin_id, description, receipt_file_id, receipt_note)
        return m.point


@sync_to_async
def clear_wallet(chat_id: int, user_id: int, admin_id: int | None = None, receipt_file_id: str | None = None, receipt_note: str | None = None) -> int:
    with db_transaction.atomic():
        m = _get_or_create_member(chat_id, user_id)
        old = m.point or 0
        m.point = 0
        m.save(update_fields=["point"])
        if old != 0:
            _log_tx(chat_id, user_id, "admin_clear", abs(old), 0, admin_id, receipt_file_id=receipt_file_id, receipt_note=receipt_note)
        return old


@sync_to_async
def charge_pv_invite_bets(
    chat_id: int,
    charges: list[tuple[int, str]],
    amount: int,
    *,
    invite_id: str,
    game_no: int | None = None,
    description: str = "ورودی مسابقه پیوی",
) -> str:
    """
    کسر اتمیک ورودی هر دو بازیکن برای یک دعوت پیوی.
    خروجی: "charged" | "already"
    """
    from account.models import WalletTransaction

    cid = int(chat_id)
    invite_id = str(invite_id).strip()
    amount = int(amount)
    if amount <= 0 or not invite_id:
        raise ValueError("invalid pv charge")

    tag = f"دعوت:{invite_id}"
    players = [(int(uid), (opp or "").strip()) for uid, opp in charges]
    if not players:
        raise ValueError("no players")

    with db_transaction.atomic():
        existing = {
            int(sid)
            for sid in WalletTransaction.objects.filter(
                telegram_chat_id=cid, type="bet", description__contains=tag,
            ).values_list("telegram_user_id", flat=True)
        }
        needed = {uid for uid, _ in players}
        if needed and needed.issubset(existing):
            return "already"
        if existing & needed:
            raise RuntimeError(
                f"partial pv invite charge exists for {invite_id}; refuse double charge"
            )

        for uid, opp_name in players:
            m = _get_or_create_member(cid, uid)
            from account.models import TelegramGroupMember
            m = TelegramGroupMember.objects.select_for_update().get(pk=m.pk)
            m.point = (m.point or 0) - amount
            m.save(update_fields=["point"])
            _log_tx(
                cid, uid, "bet", amount, m.point,
                description=with_game_id(
                    description, game_no,
                    opponent_name=opp_name, invite_id=invite_id,
                ),
            )

    for uid, _ in players:
        try:
            from bot.challenges import record_bet_silent
            record_bet_silent(cid, uid, amount)
        except Exception:
            pass
    return "charged"


@sync_to_async
def refund_pv_invite_bets(chat_id: int, user_ids, amount: int, *, invite_id: str) -> int:
    from account.models import WalletTransaction, TelegramGroupMember

    cid = int(chat_id)
    invite_id = str(invite_id).strip()
    amount = int(amount)
    tag = f"دعوت:{invite_id}"
    refund_tag = f"بازگشت دعوت:{invite_id}"
    refunded = 0
    with db_transaction.atomic():
        for raw in user_ids:
            uid = int(raw)
            has_bet = WalletTransaction.objects.filter(
                telegram_chat_id=cid, telegram_user_id=uid, type="bet",
                description__contains=tag,
            ).exists()
            if not has_bet:
                continue
            if WalletTransaction.objects.filter(
                telegram_chat_id=cid, telegram_user_id=uid,
                description__contains=refund_tag,
            ).exists():
                continue
            m = _get_or_create_member(cid, uid)
            m = TelegramGroupMember.objects.select_for_update().get(pk=m.pk)
            m.point = (m.point or 0) + amount
            m.save(update_fields=["point"])
            _log_tx(
                cid, uid, "admin_increase", amount, m.point,
                description=f"بازگشت ورودی بازی پیوی · {refund_tag}",
            )
            refunded += 1
    return refunded


@sync_to_async
def record_game_bet(
    chat_id: int,
    user_id: int,
    amount: int,
    *,
    description: str | None = None,
    game_no: int | None = None,
    opponent_name: str | None = None,
    invite_id: str | None = None,
) -> int:
    from account.models import WalletTransaction

    desc = with_game_id(
        description or "ورودی مسابقه",
        game_no,
        opponent_name=opponent_name,
        invite_id=invite_id,
    )
    with db_transaction.atomic():
        if invite_id:
            tag = f"دعوت:{str(invite_id).strip()}"
            exists = WalletTransaction.objects.filter(
                telegram_chat_id=int(chat_id),
                telegram_user_id=int(user_id),
                type="bet",
                description__contains=tag,
            ).exists()
            if exists:
                m = _get_or_create_member(chat_id, user_id)
                return int(m.point or 0)

        m = _get_or_create_member(chat_id, user_id)
        m.point = (m.point or 0) - amount
        m.save(update_fields=["point"])
        _log_tx(
            chat_id, user_id, "bet", amount, m.point,
            description=desc,
        )
        bal = m.point
    try:
        from bot.challenges import record_bet_silent
        record_bet_silent(chat_id, user_id, amount)
    except Exception:
        pass
    return bal


@sync_to_async
def record_game_win(
    chat_id: int,
    user_id: int,
    amount: int,
    *,
    description: str | None = None,
    game_no: int | None = None,
    opponent_name: str | None = None,
) -> int:
    with db_transaction.atomic():
        m = _get_or_create_member(chat_id, user_id)
        m.point = (m.point or 0) + amount
        m.save(update_fields=["point"])
        _log_tx(
            chat_id, user_id, "win", amount, m.point,
            description=with_game_id(
                description or "برد مسابقه",
                game_no,
                opponent_name=opponent_name,
            ),
        )
        return m.point


@sync_to_async
def settle_dice_game_wallets(
    chat_id: int,
    player_ids,
    entry_amount: int,
    winner_id: int,
    winner_amount: int,
    *,
    game_no: int | None = None,
) -> bool:
    """تسویه اتمیک شرط بازی — بدون ثبت چالش داخل تراکنش کیف."""
    entry_amount = int(entry_amount)
    winner_amount = int(winner_amount)
    winner_id = int(winner_id)
    players = []
    seen = set()
    for p in player_ids or []:
        uid = int(p)
        if uid not in seen:
            seen.add(uid)
            players.append(uid)
    if not players or entry_amount <= 0 or winner_amount <= 0 or winner_id not in seen:
        raise ValueError("invalid settle params")

    with db_transaction.atomic():
        for uid in players:
            m = _get_or_create_member(chat_id, uid)
            m.point = (m.point or 0) - entry_amount
            m.save(update_fields=["point"])
            _log_tx(
                chat_id, uid, "bet", entry_amount, m.point,
                description=with_game_id("ورودی مسابقه گروهی", game_no),
            )
        wm = _get_or_create_member(chat_id, winner_id)
        wm.point = (wm.point or 0) + winner_amount
        wm.save(update_fields=["point"])
        _log_tx(
            chat_id, winner_id, "win", winner_amount, wm.point,
            description=with_game_id("برد مسابقه گروهی", game_no),
        )

    for uid in players:
        try:
            from bot.challenges import record_bet_silent
            record_bet_silent(chat_id, uid, entry_amount)
        except Exception:
            pass
    return True


@sync_to_async
def transfer_wallet(
    chat_id: int,
    from_user_id: int,
    to_user_id: int,
    amount: int,
) -> dict:
    """
    انتقال موجودی بین دو عضو گروه.
    فقط «موجودی مجاز» (کل − در حال تسویه) قابل انتقال است.
    بازگشت: {ok, error?, from_balance?, to_balance?, pending?}
    """
    from django.db.models import Sum
    from account.models import WithdrawalRequest

    amount = int(amount)
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}
    if int(from_user_id) == int(to_user_id):
        return {"ok": False, "error": "self_transfer"}

    with db_transaction.atomic():
        sender = _get_or_create_member(chat_id, from_user_id)
        receiver = _get_or_create_member(chat_id, to_user_id)
        sender_bal = int(sender.point or 0)
        pending = int(
            WithdrawalRequest.objects.filter(
                telegram_chat_id=int(chat_id),
                telegram_user_id=int(from_user_id),
                status__in=("pending", "receipt"),
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        playable = max(0, sender_bal - pending)
        if playable < amount:
            return {
                "ok": False,
                "error": "insufficient",
                "from_balance": playable,
                "pending": pending,
                "total_balance": sender_bal,
            }

        sender.point = sender_bal - amount
        sender.save(update_fields=["point"])
        receiver.point = (receiver.point or 0) + amount
        receiver.save(update_fields=["point"])

        peer_out = str(to_user_id)
        peer_in = str(from_user_id)
        _log_tx(
            chat_id, from_user_id, "transfer_out", amount, sender.point,
            admin_id=to_user_id,
            description=f"انتقال به کاربر {peer_out}",
        )
        _log_tx(
            chat_id, to_user_id, "transfer_in", amount, receiver.point,
            admin_id=from_user_id,
            description=f"انتقال از کاربر {peer_in}",
        )
        return {
            "ok": True,
            "from_balance": sender.point,
            "to_balance": receiver.point,
        }


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
    return list(qs.values("telegram_user_id", "alias", "point", "balance_hidden"))


@sync_to_async
def is_balance_hidden(chat_id: int, user_id: int) -> bool:
    from account.models import TelegramGroupMember
    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
    ).first()
    return bool(m and m.balance_hidden)


@sync_to_async
def set_balance_hidden(chat_id: int, user_id: int, hidden: bool) -> bool:
    m = _get_or_create_member(chat_id, user_id)
    m.balance_hidden = bool(hidden)
    m.save(update_fields=["balance_hidden"])
    return m.balance_hidden


@sync_to_async
def is_accounts_hidden(chat_id: int, user_id: int) -> bool:
    from account.models import TelegramGroupMember
    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
    ).first()
    return bool(m and getattr(m, "accounts_hidden", False))


@sync_to_async
def set_accounts_hidden(chat_id: int, user_id: int, hidden: bool) -> bool:
    m = _get_or_create_member(chat_id, user_id)
    m.accounts_hidden = bool(hidden)
    m.save(update_fields=["accounts_hidden"])
    return m.accounts_hidden


@sync_to_async
def save_telegram_user(user_id: int, chat_id: int) -> None:
    from account.models import TelegramUser
    obj, created = TelegramUser.objects.get_or_create(
        telegram_chat_id=chat_id,
        defaults={"telegram_user_id": user_id},
    )
    if not created and obj.telegram_user_id != user_id:
        obj.telegram_user_id = user_id
        obj.save(update_fields=["telegram_user_id"])


_ALIAS_PLACEHOLDERS = frozenset({"کاربر", "user", "unknown", "کاربر ناشناس"})


def _alias_needs_name(alias: str | None) -> bool:
    a = (alias or "").strip()
    return not a or a.lower() in _ALIAS_PLACEHOLDERS


@sync_to_async
def sync_member_aliases_from_name(user_id: int, name: str) -> int:
    """اگر عضو در گروه‌ها alias ندارد، نام پروفایل را ثبت می‌کند."""
    from django.db.models import Q
    from account.models import TelegramGroupMember

    clean = (name or "").strip()[:255]
    if not clean or clean.lower() in _ALIAS_PLACEHOLDERS:
        return 0
    q = Q(alias__isnull=True) | Q(alias="")
    for ph in _ALIAS_PLACEHOLDERS:
        q |= Q(alias__iexact=ph)
    return TelegramGroupMember.objects.filter(
        telegram_user_id=user_id,
    ).filter(q).update(alias=clean)


async def register_pv_user(user_id: int, chat_id: int, display_name: str = "") -> None:
    await save_telegram_user(user_id, chat_id)
    name = (display_name or "").strip()
    if name:
        await sync_member_aliases_from_name(user_id, name)


@sync_to_async
def has_started_bot(user_id: int) -> bool:
    from account.models import TelegramUser
    return TelegramUser.objects.filter(telegram_user_id=user_id).exists()


@sync_to_async
def get_transactions(chat_id: int, user_id: int, limit: int = 5, offset: int = 0) -> list:
    from account.models import WalletTransaction
    return list(
        WalletTransaction.objects.filter(
            telegram_chat_id=chat_id, telegram_user_id=user_id,
        ).exclude(type="fee").order_by("-id")[offset:offset + limit]
    )


@sync_to_async
def get_transactions_count(chat_id: int, user_id: int) -> int:
    from account.models import WalletTransaction
    return WalletTransaction.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
    ).exclude(type="fee").count()


@sync_to_async
def clear_all_wallets(chat_id: int, admin_id: int | None = None, receipt_file_id: str | None = None, receipt_note: str | None = None) -> list[tuple[int, int]]:
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
            _log_tx(chat_id, m.telegram_user_id, "admin_clear", abs(old), 0, admin_id, receipt_file_id=receipt_file_id, receipt_note=receipt_note)
            results.append((m.telegram_user_id, old))
    return results


@sync_to_async
def get_fee_report(
    chat_id: int,
    days: int = 7,
    target_user_id: int | None = None,
    day_offset: int | None = None,
    this_week: bool = False,
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
    elif this_week:
        days_since_saturday = (today.weekday() - 5) % 7
        start_date = today - timedelta(days=days_since_saturday)
        end_date = today
        qs = qs.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
    else:
        start_date = today - timedelta(days=max(0, days - 1))
        end_date = today
        qs = qs.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
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
