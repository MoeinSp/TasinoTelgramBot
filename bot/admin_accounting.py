from collections import defaultdict
from datetime import timedelta

import jdatetime
from asgiref.sync import sync_to_async
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from django.db.models import Count, Sum
from django.utils import timezone

from account.models import AdminAccounting, AdminActivitySession, TelegramGroupMember, WalletTransaction

PERSIAN_WEEKDAYS = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه")
DETAIL_PAGE_SIZE = 7
TIMELINE_PAGE_SIZE = 5
_report_context = {}


def period_bounds(mode="0"):
    now = timezone.now()
    if mode == "w":
        return now - timedelta(days=7), now
    try:
        days = max(0, min(6, int(mode)))
    except (TypeError, ValueError):
        days = 0
    local = timezone.localtime(now) - timedelta(days=days)
    start = timezone.make_aware(
        local.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    )
    return start, start + timedelta(days=1)


def period_label(mode="0"):
    start, end = period_bounds(mode)
    start_local = timezone.localtime(start)
    end_local = timezone.localtime(end - timedelta(seconds=1))
    if str(mode) == "w":
        return f"هفت روز اخیر — {start_local:%Y/%m/%d} تا {end_local:%Y/%m/%d}"
    try:
        days = max(0, min(6, int(mode)))
    except (TypeError, ValueError):
        days = 0
    day_name = "امروز" if days == 0 else f"{days} روز قبل"
    return f"{day_name} — یک روز کامل {start_local:%Y/%m/%d} (۰۰:۰۰ تا ۲۳:۵۹)"


def compute_financials(increase, settle, fee, share_percent):
    """
    تراز نقدی = افزایش − تسویه
    سهم ادمین از حق‌واسطه = طلب ادمین از مالک
    مبلغ نهایی (مثبت = ادمین → مالک | منفی = مالک → ادمین)
      = تراز_نقدی − سهم_ادمین
    """
    increase = abs(int(increase or 0))
    settle = abs(int(settle or 0))
    fee = abs(int(fee or 0))
    pct = max(0, min(100, int(share_percent or 0)))

    cash_balance = increase - settle
    admin_share = fee * pct // 100
    owner_fee = fee - admin_share
    net = cash_balance - admin_share

    if net > 0:
        settlement_kind = "admin_pays"
        settle_amount = net
    elif net < 0:
        settlement_kind = "owner_pays"
        settle_amount = abs(net)
    else:
        settlement_kind = "clear"
        settle_amount = 0

    return {
        "cash_balance": cash_balance,
        "admin_share": admin_share,
        "owner_fee": owner_fee,
        "net": net,
        "settle_amount": settle_amount,
        "settlement_kind": settlement_kind,
        "profit": net,
        "owner_due": settle_amount,
    }


def settlement_line(row):
    kind = row.get("settlement_kind")
    amount = row.get("settle_amount", row.get("owner_due", 0))
    if kind == "admin_pays":
        return f"🔻 ادمین باید به مالک بزند: {amount:,}"
    if kind == "owner_pays":
        return f"💸 مالک باید به ادمین بزند: {amount:,}"
    return "✅ تسویه دو طرفه: ۰ (هیچ‌کس بدهکار نیست)"


def settlement_line_signed(net: int) -> str:
    if net > 0:
        return f"🔻 ادمین باید به مالک بزند: {net:,}"
    if net < 0:
        return f"💸 مالک باید به ادمین بزند: {abs(net):,}"
    return "✅ تسویه دو طرفه: ۰ (هیچ‌کس بدهکار نیست)"


_SETTLE_TYPES = ("admin_decrease", "admin_clear")
_GAME_TX_TYPES = ("bet", "win", "game_bet", "game_win", "game_start")
_GAME_DESC_MARKERS = ("مسابقه تاس", "شرکت در مسابقه", "برنده مسابقه")


def _exclude_game_wallet_txs(qs):
    """
    ورودی/برد بازی نباید وارد تراز نقدی ادمین شود.
    حق‌واسطه (type=fee) هرگز حذف نمی‌شود.
    """
    qs = qs.exclude(type__in=_GAME_TX_TYPES)
    cash_types = ("admin_increase",) + _SETTLE_TYPES
    for marker in _GAME_DESC_MARKERS:
        qs = qs.exclude(type__in=cash_types, description__icontains=marker)
    return qs


def _group_total_balance(chat_id) -> int:
    return int(
        TelegramGroupMember.objects.filter(telegram_chat_id=int(chat_id)).aggregate(
            v=Sum("point")
        )["v"]
        or 0
    )


def _session_tx_stats(chat_id, admin_id, start, end):
    qs = WalletTransaction.objects.filter(
        telegram_chat_id=int(chat_id), created_at__gte=start, created_at__lt=end
    )
    active = _exclude_game_wallet_txs(qs.filter(admin_id=int(admin_id)))
    other = _exclude_game_wallet_txs(
        qs.exclude(admin_id=int(admin_id)).exclude(admin_id__isnull=True)
    )

    def _sum(q, types):
        return abs(q.filter(type__in=types).aggregate(v=Sum("amount"))["v"] or 0)

    increased = _sum(active, ("admin_increase",))
    settled = _sum(active, _SETTLE_TYPES)
    fee = _sum(active, ("fee",))
    other_inc = _sum(other, ("admin_increase",))
    other_settle = _sum(other, _SETTLE_TYPES)
    other_fee = _sum(other, ("fee",))
    return {
        "increase": increased,
        "settle": settled,
        "fee": fee,
        "other_increase": other_inc,
        "other_settle": other_settle,
        "other_fee": other_fee,
    }


def _session_challenge_stats(chat_id, admin_id, start, end) -> dict:
    from account.models import GroupChallenge

    qs = GroupChallenge.objects.filter(
        telegram_chat_id=int(chat_id),
        created_by=int(admin_id),
        created_at__gte=start,
        created_at__lt=end,
    ).exclude(status="cancelled")
    agg = qs.aggregate(n=Count("id"), total=Sum("prize_amount"))
    return {
        "challenge_count": int(agg["n"] or 0),
        "challenge_prize_total": int(agg["total"] or 0),
    }


def _session_league_stats(chat_id, start, end) -> dict:
    """جوایز لیگ در بازه فعالیت (از طرف مالک؛ در تسویه ادمین لحاظ نمی‌شود)."""
    qs = WalletTransaction.objects.filter(
        telegram_chat_id=int(chat_id),
        created_at__gte=start,
        created_at__lt=end,
        description__icontains="(لیگ پله",
    )
    agg = qs.aggregate(n=Count("id"), total=Sum("amount"))
    return {
        "league_prize_count": int(agg["n"] or 0),
        "league_prize_total": abs(int(agg["total"] or 0)),
    }


def make_offschedule_id(admin_id, day_key: str) -> str:
    return f"off_{admin_id}_{day_key}"


def parse_offschedule_id(session_id):
    """شناسه مجازی خارج از برنامه: off_{admin}_{YYYY-MM-DD}"""
    from datetime import datetime as _dt

    s = str(session_id or "")
    if not s.startswith("off_"):
        return None
    body = s[4:]
    if len(body) < 11 or body[-11] != "_":
        return None
    day_key = body[-10:]
    admin_raw = body[:-11]
    try:
        _dt.strptime(day_key, "%Y-%m-%d")
    except ValueError:
        return None
    if not admin_raw:
        return None
    try:
        admin_id = int(admin_raw)
    except (TypeError, ValueError):
        return None
    return admin_id, day_key


def _day_bounds(day_key: str):
    from datetime import datetime as _dt

    local = _dt.strptime(day_key, "%Y-%m-%d")
    start = timezone.make_aware(local.replace(hour=0, minute=0, second=0, microsecond=0))
    return start, start + timedelta(days=1)


def _exclude_admin_session_windows(qs, chat_id, admin_id):
    """تراکنش‌هایی که داخل بازه «شروع/پایان فعالیت» همان ادمین هستند حذف می‌شوند."""
    from django.db.models import Q

    now = timezone.now()
    windows = list(
        AdminActivitySession.objects.filter(
            telegram_chat_id=int(chat_id),
            admin_id=int(admin_id),
        ).values_list("started_at", "ended_at")
    )
    excl = Q()
    for started_at, ended_at in windows:
        excl |= Q(created_at__gte=started_at, created_at__lt=(ended_at or now))
    return qs.exclude(excl) if windows else qs


def _offschedule_tx_stats(chat_id, admin_id, start, end):
    qs = WalletTransaction.objects.filter(
        telegram_chat_id=int(chat_id),
        admin_id=int(admin_id),
        created_at__gte=start,
        created_at__lt=end,
    )
    qs = _exclude_game_wallet_txs(qs)
    qs = _exclude_admin_session_windows(qs, chat_id, admin_id)

    def _sum(types):
        return abs(qs.filter(type__in=types).aggregate(v=Sum("amount"))["v"] or 0)

    return {
        "increase": _sum(("admin_increase",)),
        "settle": _sum(_SETTLE_TYPES),
        "fee": _sum(("fee",)),
        "other_increase": 0,
        "other_settle": 0,
        "other_fee": 0,
    }


def _offschedule_hourly_stats(chat_id, admin_id, start, end):
    buckets = defaultdict(lambda: {"increase": 0, "settle": 0, "fee": 0, "games": 0})
    qs = WalletTransaction.objects.filter(
        telegram_chat_id=int(chat_id),
        admin_id=int(admin_id),
        created_at__gte=start,
        created_at__lt=end,
        type__in=("admin_increase", "fee") + _SETTLE_TYPES + ("bet", "game_bet", "game_start"),
    ).only("type", "amount", "created_at").order_by("created_at")
    qs = _exclude_admin_session_windows(qs, chat_id, admin_id)
    for tx in qs.iterator(chunk_size=500):
        hour = timezone.localtime(tx.created_at).strftime("%H:00")
        amt = abs(int(tx.amount or 0))
        if tx.type == "admin_increase":
            buckets[hour]["increase"] += amt
        elif tx.type in _SETTLE_TYPES:
            buckets[hour]["settle"] += amt
        elif tx.type == "fee":
            buckets[hour]["fee"] += amt
        elif tx.type in ("bet", "game_bet", "game_start"):
            buckets[hour]["games"] += 1
    return [{"hour": h, **buckets[h]} for h in sorted(buckets.keys())]


def _build_offschedule_row(chat_id, admin_id, day_key: str, *, detail: bool = False):
    start, day_end = _day_bounds(day_key)
    now = timezone.now()
    is_today = timezone.localtime(now).strftime("%Y-%m-%d") == day_key
    query_end = min(now, day_end) if is_today else day_end
    stats = _offschedule_tx_stats(chat_id, admin_id, start, query_end)
    cfg = AdminAccounting.objects.filter(
        telegram_chat_id=int(chat_id), admin_id=int(admin_id)
    ).first()
    pct = int(cfg.share_percent) if cfg else 50
    fin = compute_financials(stats["increase"], stats["settle"], stats["fee"], pct)
    hourly = (
        _offschedule_hourly_stats(chat_id, admin_id, start, query_end) if detail else []
    )
    challenge_stats = _session_challenge_stats(chat_id, admin_id, start, query_end)
    league_stats = _session_league_stats(chat_id, start, query_end)
    ended_local = None if is_today else timezone.localtime(day_end - timedelta(seconds=1))
    return {
        "id": make_offschedule_id(admin_id, day_key),
        "is_offschedule": True,
        "admin_id": int(admin_id),
        "admin_name": _admin_name(chat_id, admin_id),
        "started_at": timezone.localtime(start),
        "ended_at": ended_local,
        "is_active": is_today,
        "start_group_balance": None,
        "end_group_balance": None,
        "percent": pct,
        "hourly": hourly,
        **stats,
        **fin,
        **challenge_stats,
        **league_stats,
        "balance_delta": 0,
        "session_net": fin["net"],
        "session_settlement_kind": fin["settlement_kind"],
        "session_settle_amount": fin["settle_amount"],
    }


def _admins_for_offschedule_day(chat_id, day_key: str) -> set[int]:
    """فقط ادمین‌هایی که همان روز تراکنش یا بازه دارند — نه کل AdminAccounting."""
    start, end = _day_bounds(day_key)
    ids: set[int] = set(
        AdminActivitySession.objects.filter(
            telegram_chat_id=int(chat_id),
            started_at__gte=start,
            started_at__lt=end,
        ).values_list("admin_id", flat=True)
    )
    ids.update(
        WalletTransaction.objects.filter(
            telegram_chat_id=int(chat_id),
            admin_id__isnull=False,
            created_at__gte=start,
            created_at__lt=end,
            type__in=("admin_increase", "fee") + _SETTLE_TYPES,
        ).values_list("admin_id", flat=True)
    )
    return {int(x) for x in ids if x is not None}


def list_offschedule_for_day(chat_id, day_key: str, *, detail: bool = False) -> list[dict]:
    """بازه خارج از برنامه هر ادمین در یک روز — فقط اگر تراکنش یا بازه رسمی داشته باشد."""
    start, end = _day_bounds(day_key)
    session_admins = {
        int(x)
        for x in AdminActivitySession.objects.filter(
            telegram_chat_id=int(chat_id),
            started_at__gte=start,
            started_at__lt=end,
        ).values_list("admin_id", flat=True)
    }
    rows = []
    for aid in _admins_for_offschedule_day(chat_id, day_key):
        row = _build_offschedule_row(chat_id, aid, day_key, detail=detail)
        has_session = int(aid) in session_admins
        has_tx = bool(row["increase"] or row["settle"] or row["fee"])
        if has_session or has_tx:
            rows.append(row)
    rows.sort(key=lambda r: (r.get("admin_name") or "", r["admin_id"]))
    return rows


def _activity_cash_days(chat_id, lookback_days: int = 30) -> set[str]:
    """روزهای دارای تراکنش نقدی ادمین — بدون اسکن پنجره‌به‌پنجره."""
    since = timezone.now() - timedelta(days=lookback_days)
    days: set[str] = set()
    qs = WalletTransaction.objects.filter(
        telegram_chat_id=int(chat_id),
        admin_id__isnull=False,
        created_at__gte=since,
        type__in=("admin_increase", "fee") + _SETTLE_TYPES,
    )
    for ts in qs.datetimes("created_at", "day", tzinfo=timezone.get_current_timezone()):
        days.add(timezone.localtime(ts).strftime("%Y-%m-%d"))
    return days


def compute_session_balance_settlement(start_balance: int, end_balance: int) -> dict:
    balance_delta = int(end_balance or 0) - int(start_balance or 0)
    return {"balance_delta": balance_delta}


def _session_hourly_stats(chat_id, admin_id, start, end):
    buckets = defaultdict(lambda: {"increase": 0, "settle": 0, "fee": 0, "games": 0})
    qs = WalletTransaction.objects.filter(
        telegram_chat_id=int(chat_id),
        admin_id=int(admin_id),
        created_at__gte=start,
        created_at__lt=end,
        type__in=("admin_increase", "fee") + _SETTLE_TYPES + ("bet", "game_bet", "game_start"),
    ).only("type", "amount", "created_at").order_by("created_at")
    for tx in qs.iterator(chunk_size=500):
        hour = timezone.localtime(tx.created_at).strftime("%H:00")
        amt = abs(int(tx.amount or 0))
        if tx.type == "admin_increase":
            buckets[hour]["increase"] += amt
        elif tx.type in _SETTLE_TYPES:
            buckets[hour]["settle"] += amt
        elif tx.type == "fee":
            buckets[hour]["fee"] += amt
        elif tx.type in ("bet", "game_bet", "game_start"):
            buckets[hour]["games"] += 1
    return [{"hour": h, **buckets[h]} for h in sorted(buckets.keys())]


def _build_session_row(chat_id, session, *, end_override=None, detail: bool = False, meta_only: bool = False):
    """
    meta_only: فقط شناسه/زمان/ادمین برای لیست روزها.
    detail=False: مالی + چالش/لیگ برای لیست همان روز (بدون hourly).
    detail=True: گزارش کامل یک بازه.
    """
    if meta_only:
        return {
            "id": session.id,
            "admin_id": session.admin_id,
            "admin_name": _admin_name(chat_id, session.admin_id),
            "started_at": timezone.localtime(session.started_at),
            "ended_at": timezone.localtime(session.ended_at) if session.ended_at else None,
            "is_active": session.ended_at is None,
            "increase": 0,
            "settle": 0,
            "fee": 0,
            "session_net": 0,
            "challenge_count": 0,
            "challenge_prize_total": 0,
            "league_prize_count": 0,
            "league_prize_total": 0,
            "hourly": [],
        }

    end = end_override or session.ended_at or timezone.now()
    stats = _session_tx_stats(chat_id, session.admin_id, session.started_at, end)
    cfg = AdminAccounting.objects.filter(
        telegram_chat_id=int(chat_id), admin_id=session.admin_id
    ).first()
    pct = int(cfg.share_percent) if cfg else 50
    fin = compute_financials(stats["increase"], stats["settle"], stats["fee"], pct)
    start_bal = int(session.start_group_balance or 0)
    if session.end_group_balance is not None:
        end_bal = int(session.end_group_balance)
    elif detail and session.ended_at is None:
        end_bal = int(_group_total_balance(chat_id))
    else:
        end_bal = start_bal
    balance_info = compute_session_balance_settlement(start_bal, end_bal)
    hourly = (
        _session_hourly_stats(chat_id, session.admin_id, session.started_at, end)
        if detail
        else []
    )
    challenge_stats = _session_challenge_stats(
        chat_id, session.admin_id, session.started_at, end
    )
    league_stats = _session_league_stats(chat_id, session.started_at, end)
    return {
        "id": session.id,
        "admin_id": session.admin_id,
        "admin_name": _admin_name(chat_id, session.admin_id),
        "started_at": timezone.localtime(session.started_at),
        "ended_at": timezone.localtime(session.ended_at) if session.ended_at else None,
        "is_active": session.ended_at is None,
        "start_group_balance": start_bal,
        "end_group_balance": end_bal,
        "percent": pct,
        "hourly": hourly,
        **stats,
        **fin,
        **balance_info,
        **challenge_stats,
        **league_stats,
        "session_net": fin["net"],
        "session_settlement_kind": fin["settlement_kind"],
        "session_settle_amount": fin["settle_amount"],
    }


def _fmt_money(n):
    n = int(n or 0)
    sign = "+" if n > 0 else ""
    return f"{sign}{n:,}"


_SEP = "━━━━━━━━━━━━━━━━━━"
_SUB = "────────"


def _settlement_parties(net: int, admin_name: str = "ادمین") -> list[str]:
    n = int(net or 0)
    name = (admin_name or "ادمین").strip()
    if n > 0:
        return [f"  🔻 {name} → مالک: {n:,}"]
    if n < 0:
        return [f"  💸 مالک → {name}: {abs(n):,}"]
    return ["  ✅ تسویه صفر"]


def _settlement_footer(net: int, admin_name: str = "ادمین") -> str:
    n = int(net or 0)
    name = (admin_name or "ادمین").strip()
    if n > 0:
        return f"  📌 {name} → مالک | {n:,}"
    if n < 0:
        return f"  📌 مالک → {name} | {abs(n):,}"
    return "  📌 تسویه صفر"


def _session_time_line(session: dict) -> str:
    start = session["started_at"]
    end = session.get("ended_at")
    weekday = PERSIAN_WEEKDAYS[start.weekday()]
    jdate = jdatetime.datetime.fromgregorian(datetime=start).strftime("%Y/%m/%d")
    if session.get("is_offschedule"):
        times = "۰۰:۰۰ → الان" if session.get("is_active") else "۰۰:۰۰ → ۲۳:۵۹"
        return f"{weekday} {jdate} · {times}"
    times = f"{start:%H:%M} → {end:%H:%M}" if end else f"{start:%H:%M} → الان"
    return f"{weekday} {jdate} · {times}"


def _amount_lines(items: list[tuple[str, int]], *, empty: str) -> list[str]:
    nonzero = [(label, val) for label, val in items if int(val or 0) != 0]
    if not nonzero:
        return [f"  {empty}"]
    return [f"  {label}: {int(val):,}" for label, val in nonzero]


def _calc_row(value: int, label: str, *, op: str = "") -> str:
    v = int(value or 0)
    if op == "-":
        text = f"−{v:,}" if v else "0"
    elif op == "=":
        text = f"= {v:+,}" if v else "= 0"
    elif op == "+":
        text = f"+{v:,}" if v else "0"
    else:
        text = f"{v:+,}" if v else "0"
    return f"  {text:>10}  {label}"


def _render_session_calc(session: dict, admin_name: str) -> list[str]:
    pct = int(session.get("percent") or 0)
    session_net = int(session.get("session_net", 0))
    return [
        "🧮 محاسبه",
        _SUB,
        _calc_row(session.get("increase", 0), "افزایش", op="+"),
        _calc_row(session.get("settle", 0), "تسویه", op="-"),
        _calc_row(session.get("admin_share", 0), f"سهم ادمین ({pct}٪)", op="-"),
        "  ─────────",
        _calc_row(session_net, "جمع", op="="),
        _settlement_footer(session_net, admin_name),
    ]


def _admin_name(chat_id, admin_id):
    stored = (
        TelegramGroupMember.objects.filter(
            telegram_chat_id=chat_id, telegram_user_id=admin_id
        )
        .values_list("alias", flat=True)
        .first()
        or ""
    ).strip()
    return stored or str(admin_id)


def _report_bounds(mode="0", session_id=None):
    if session_id:
        parsed = parse_offschedule_id(session_id)
        if parsed:
            admin_id, day_key = parsed
            start, end = _day_bounds(day_key)
            now = timezone.now()
            if timezone.localtime(now).strftime("%Y-%m-%d") == day_key:
                end = min(end, now)
            return start, end, ("off", admin_id, day_key)
        session = AdminActivitySession.objects.get(id=int(session_id))
        return session.started_at, session.ended_at or timezone.now(), session
    start, end = period_bounds(mode)
    return start, end, None


@sync_to_async
def report(chat_id, mode="0", admin_id=None, session_id=None):
    start, end, session = _report_bounds(mode, session_id)
    qs = WalletTransaction.objects.filter(
        telegram_chat_id=chat_id, created_at__gte=start, created_at__lt=end
    )
    ids = set(qs.exclude(admin_id__isnull=True).values_list("admin_id", flat=True))
    off_meta = None
    if isinstance(session, tuple) and session and session[0] == "off":
        off_meta = session
        ids = {session[1]}
        qs = _exclude_admin_session_windows(qs, chat_id, session[1])
    elif session and not isinstance(session, tuple):
        ids = {session.admin_id}
    if admin_id is not None:
        ids = {int(admin_id)}

    rows = []
    for aid in ids:
        aq = _exclude_game_wallet_txs(qs.filter(admin_id=aid))
        if off_meta:
            aq = _exclude_admin_session_windows(aq, chat_id, aid)
        inc = abs(aq.filter(type="admin_increase").aggregate(v=Sum("amount"))["v"] or 0)
        settle = abs(
            aq.filter(type__in=("admin_decrease", "admin_clear")).aggregate(v=Sum("amount"))["v"] or 0
        )
        fee = abs(aq.filter(type="fee").aggregate(v=Sum("amount"))["v"] or 0)
        cfg, _ = AdminAccounting.objects.get_or_create(
            telegram_chat_id=chat_id,
            admin_id=aid,
            defaults={"share_percent": 50},
        )
        fin = compute_financials(inc, settle, fee, cfg.share_percent)
        if not (inc or settle or fee) and not (session or admin_id is not None):
            continue
        rows.append(
            {
                "admin_id": aid,
                "admin_name": _admin_name(chat_id, aid),
                "increase": inc,
                "settle": settle,
                "fee": fee,
                "percent": int(cfg.share_percent or 0),
                **fin,
            }
        )
    return sorted(
        rows,
        key=lambda x: (abs(x.get("net", 0)), x.get("fee", 0), x.get("increase", 0)),
        reverse=True,
    )


@sync_to_async
def set_share(chat_id, admin_id, percent):
    percent = max(0, min(100, int(percent)))
    obj, _ = AdminAccounting.objects.get_or_create(
        telegram_chat_id=chat_id, admin_id=int(admin_id)
    )
    obj.share_percent = percent
    obj.save(update_fields=["share_percent"])
    return percent


# انتظار ورود درصد دلخواه سهم ادمین از پیوی مالک
_share_wait: dict[int, dict] = {}


def set_share_wait(owner_id: int, *, chat_id: int, admin_id: int, session_id: str | None = None) -> None:
    _share_wait[int(owner_id)] = {
        "chat_id": int(chat_id),
        "admin_id": int(admin_id),
        "session_id": session_id or None,
    }


def is_waiting_share_percent(owner_id: int) -> bool:
    return int(owner_id) in _share_wait


def pop_share_wait(owner_id: int) -> dict | None:
    return _share_wait.pop(int(owner_id), None)


async def handle_share_custom_text(message, bot) -> bool:
    """پردازش عدد دلخواه سهم ادمین در پیوی."""
    from bot.cache_manager import is_owner
    from bot.utils import normalize_numbers

    uid = int(message.from_user.id)
    data = pop_share_wait(uid)
    if not data:
        return False

    text = (message.text or "").strip()
    if text in ("لغو", "انصراف", "cancel", "Cancel"):
        await message.answer("❌ تنظیم درصد لغو شد.")
        return True

    chat_id = int(data["chat_id"])
    admin_id = int(data["admin_id"])
    session_id = data.get("session_id")
    if not is_owner(chat_id, uid):
        await message.answer("❌ فقط مالک می‌تواند سهم ادمین را تغییر دهد.")
        return True

    raw = normalize_numbers(text).replace("%", "").replace("٪", "").strip()
    try:
        percent = int(raw)
    except ValueError:
        set_share_wait(uid, chat_id=chat_id, admin_id=admin_id, session_id=session_id)
        await message.answer(
            "⚠️ یک عدد بین ۰ تا ۱۰۰ بنویسید.\n"
            "مثال: <code>45</code>\n"
            "برای لغو: لغو",
            parse_mode="HTML",
        )
        return True

    if not (0 <= percent <= 100):
        set_share_wait(uid, chat_id=chat_id, admin_id=admin_id, session_id=session_id)
        await message.answer("⚠️ درصد باید بین ۰ تا ۱۰۰ باشد.")
        return True

    new_pct = await set_share(chat_id, admin_id, percent)
    await message.answer(
        f"✅ سهم ادمین روی {new_pct}٪ تنظیم شد.\n"
        "گزارش‌های بعدی با درصد جدید محاسبه می‌شوند."
    )
    if session_id:
        session = await get_activity_session(chat_id, session_id)
        if session:
            kb = report_keyboard(
                chat_id, [], session_id=session_id,
                selected_admin=session["admin_id"], session=session,
            )
            await _send_fresh_message(bot, uid, render_session_card(session), kb)
            return True
    rows = await report(chat_id, "0")
    await _send_fresh_message(
        bot, uid, render(rows, "0"),
        report_keyboard(chat_id, rows, "0", selected_admin=admin_id),
    )
    return True


@sync_to_async
def get_admin_share_percent(chat_id, admin_id) -> int:
    cfg = AdminAccounting.objects.filter(
        telegram_chat_id=int(chat_id), admin_id=int(admin_id)
    ).first()
    return int(cfg.share_percent) if cfg else 50


@sync_to_async
def start_activity(chat_id, admin_id):
    now = timezone.now()
    cid = int(chat_id)
    aid = int(admin_id)
    start_bal = _group_total_balance(cid)

    open_session = (
        AdminActivitySession.objects.filter(telegram_chat_id=cid, ended_at__isnull=True)
        .order_by("-started_at")
        .first()
    )
    if open_session and int(open_session.admin_id) == aid:
        return {
            "already_active": True,
            "admin_id": aid,
            "session_id": open_session.id,
            "start_group_balance": int(open_session.start_group_balance or start_bal),
            "closed_session": None,
        }

    closed_summary = None
    if open_session:
        open_session.ended_at = now
        open_session.end_group_balance = start_bal
        open_session.save(update_fields=["ended_at", "end_group_balance"])
        closed_summary = _build_session_row(cid, open_session, detail=False)

    AdminAccounting.objects.filter(telegram_chat_id=cid, is_active_cashier=True).update(
        is_active_cashier=False
    )
    obj, _ = AdminAccounting.objects.get_or_create(telegram_chat_id=cid, admin_id=aid)
    obj.is_active_cashier = True
    obj.activity_started_at = now
    obj.save(update_fields=["is_active_cashier", "activity_started_at"])
    session = AdminActivitySession.objects.create(
        telegram_chat_id=cid,
        admin_id=aid,
        started_at=now,
        start_group_balance=start_bal,
    )
    return {
        "already_active": False,
        "admin_id": aid,
        "session_id": session.id,
        "start_group_balance": start_bal,
        "closed_session": closed_summary,
    }


@sync_to_async
def end_activity(chat_id):
    now = timezone.now()
    cid = int(chat_id)
    end_bal = _group_total_balance(cid)
    active = (
        AdminAccounting.objects.filter(telegram_chat_id=cid, is_active_cashier=True)
        .values("admin_id")
        .first()
    )
    session = (
        AdminActivitySession.objects.filter(telegram_chat_id=cid, ended_at__isnull=True)
        .order_by("-started_at")
        .first()
    )
    closed = 0
    closed_summary = None
    if session:
        session.ended_at = now
        session.end_group_balance = end_bal
        session.save(update_fields=["ended_at", "end_group_balance"])
        closed = 1
        closed_summary = _build_session_row(cid, session, detail=False)
    AdminAccounting.objects.filter(telegram_chat_id=cid, is_active_cashier=True).update(
        is_active_cashier=False, activity_started_at=None
    )
    admin_id = active["admin_id"] if active else None
    return {
        "had_active": bool(active or session),
        "admin_id": admin_id,
        "admin_name": _admin_name(cid, admin_id) if admin_id else None,
        "closed_sessions": closed,
        "end_group_balance": end_bal,
        "closed_session": closed_summary,
    }


def _resolve_active_cashier_id(chat_id):
    """آخرین ادمینی که «شروع فعالیت» زده (نشست باز)."""
    session_admin = (
        AdminActivitySession.objects.filter(telegram_chat_id=chat_id, ended_at__isnull=True)
        .order_by("-started_at")
        .values_list("admin_id", flat=True)
        .first()
    )
    if session_admin:
        return session_admin
    return (
        AdminAccounting.objects.filter(telegram_chat_id=chat_id, is_active_cashier=True)
        .order_by("-activity_started_at")
        .values_list("admin_id", flat=True)
        .first()
    )


def _first_member_card(member) -> str:
    if not member:
        return ""
    for field in ("card_number", "card_number2", "card_number3"):
        val = (getattr(member, field, None) or "").strip()
        if val:
            return val
    return ""


@sync_to_async
def active_cashier(chat_id):
    return _resolve_active_cashier_id(chat_id)


@sync_to_async
def active_cashier_payment_info(chat_id):
    admin_id = _resolve_active_cashier_id(chat_id)
    if not admin_id:
        owner = TelegramGroupMember.objects.filter(
            telegram_chat_id=chat_id, is_owner=True,
        ).first()
        if not owner:
            owner = TelegramGroupMember.objects.filter(
                telegram_chat_id=chat_id, role="owner",
            ).first()
        if not owner or not _first_member_card(owner):
            return None
        return {
            "admin_id": owner.telegram_user_id,
            "card": _first_member_card(owner),
            "name": (owner.card_name or "").strip(),
            "is_owner": True,
        }
    member = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=admin_id,
    ).first()
    return {
        "admin_id": admin_id,
        "card": _first_member_card(member),
        "name": (member.card_name or "").strip() if member else "",
        "is_owner": False,
    }


def _filter_spurious_sessions(rows: list[dict]) -> list[dict]:
    skip_ids: set = set()
    for r in rows:
        if r.get("is_active") or not r.get("ended_at"):
            continue
        if r.get("increase") or r.get("settle") or r.get("fee"):
            continue
        if (r["ended_at"] - r["started_at"]).total_seconds() > 120:
            continue
        start_key = r["started_at"].strftime("%Y-%m-%d %H:%M")
        aid = str(r["admin_id"])
        for other in rows:
            if other["id"] == r["id"] or str(other["admin_id"]) != aid:
                continue
            if other["started_at"].strftime("%Y-%m-%d %H:%M") == start_key:
                if other["started_at"] >= r["started_at"]:
                    skip_ids.add(r["id"])
                    break
    return [r for r in rows if r["id"] not in skip_ids]


@sync_to_async
def get_active_session_live(chat_id):
    session = (
        AdminActivitySession.objects.filter(
            telegram_chat_id=int(chat_id), ended_at__isnull=True,
        )
        .order_by("-started_at")
        .first()
    )
    if not session:
        return None
    return _build_session_row(chat_id, session, detail=True)


@sync_to_async
def list_activity_sessions(chat_id, limit=40):
    """سبک: فقط متا برای انتخاب روز — بدون اسکن تراکنش/ساعتی."""
    sessions = list(
        AdminActivitySession.objects.filter(telegram_chat_id=int(chat_id)).order_by("-started_at")[
            :limit
        ]
    )
    return [_build_session_row(chat_id, s, meta_only=True) for s in sessions]


@sync_to_async
def list_activity_sessions_for_day(chat_id, day_key: str):
    """مالی همان روز بدون hourly — برای صفحهٔ روز."""
    start, end = _day_bounds(day_key)
    sessions = list(
        AdminActivitySession.objects.filter(
            telegram_chat_id=int(chat_id),
            started_at__gte=start,
            started_at__lt=end,
        ).order_by("started_at")
    )
    rows = [_build_session_row(chat_id, s, detail=False) for s in sessions]
    return _filter_spurious_sessions(rows)


@sync_to_async
def list_offschedule_day(chat_id, day_key: str):
    return list_offschedule_for_day(chat_id, day_key, detail=False)


@sync_to_async
def list_activity_day_keys(chat_id, limit=14):
    """روزهای دارای بازه رسمی یا تراکنش نقدی ادمین."""
    sessions = list(
        AdminActivitySession.objects.filter(telegram_chat_id=int(chat_id))
        .order_by("-started_at")
        .values_list("started_at", flat=True)[:200]
    )
    days = {timezone.localtime(s).strftime("%Y-%m-%d") for s in sessions}
    days |= _activity_cash_days(chat_id, lookback_days=max(30, limit + 5))
    today = timezone.localtime().strftime("%Y-%m-%d")
    days.add(today)
    return sorted(days, reverse=True)[:limit]


@sync_to_async
def get_activity_session(chat_id, session_id):
    parsed = parse_offschedule_id(session_id)
    if parsed:
        admin_id, day_key = parsed
        return _build_offschedule_row(chat_id, admin_id, day_key, detail=True)
    session = AdminActivitySession.objects.filter(
        telegram_chat_id=int(chat_id), id=int(session_id)
    ).first()
    if not session:
        return None
    return _build_session_row(chat_id, session, detail=True)


def session_title(session_id, sessions=None):
    if sessions:
        for s in sessions:
            if str(s["id"]) == str(session_id):
                return _format_session_header(s)
    parsed = parse_offschedule_id(session_id)
    if parsed:
        _, day_key = parsed
        return f"خارج از برنامه — {day_key}"
    return f"بازه فعالیت #{session_id}"


def _format_session_header(session):
    start = session["started_at"]
    end = session["ended_at"]
    weekday = PERSIAN_WEEKDAYS[start.weekday()]
    jdate = jdatetime.datetime.fromgregorian(datetime=start).strftime("%Y/%m/%d")
    if session.get("is_offschedule"):
        status = "🟠 خارج از برنامه"
        time_part = "۰۰:۰۰ → الان" if session.get("is_active") else "۰۰:۰۰ → ۲۳:۵۹"
        return f"{status} | {weekday} {jdate} | {time_part} | {session.get('admin_name', '')}"
    time_part = f"{start:%H:%M}"
    if end:
        time_part += f" → {end:%H:%M}"
    else:
        time_part += " → الان"
    status = "🟢 فعال" if session.get("is_active") else "⚫ بسته"
    return f"{status} | {weekday} {jdate} | {time_part} | {session.get('admin_name', '')}"


def render(rows, title=None):
    if title is None:
        title = "گزارش مالی"
    elif str(title) in {"0", "1", "2", "3", "4", "5", "6", "w"}:
        title = period_label(title)

    total_inc = sum(r["increase"] for r in rows)
    total_settle = sum(r["settle"] for r in rows)
    total_fee = sum(r["fee"] for r in rows)
    total_admin_share = sum(r["admin_share"] for r in rows)
    total_owner_fee = sum(r.get("owner_fee", r["fee"] - r["admin_share"]) for r in rows)
    total_admin_pays = sum(
        r.get("settle_amount", 0) for r in rows if r.get("settlement_kind") == "admin_pays"
    )
    total_owner_pays = sum(
        r.get("settle_amount", 0) for r in rows if r.get("settlement_kind") == "owner_pays"
    )

    lines = [
        "📊 گزارش مالی ادمین‌ها",
        f"📅 {title}",
        _SEP,
        f"👥 {len(rows)} ادمین",
        f"➕ افزایش: {total_inc:,}   🧾 تسویه: {total_settle:,}",
        f"💹 حق واسطه: {total_fee:,}  (ادمین {total_admin_share:,} · مالک {total_owner_fee:,})",
        f"🏁 ادمین→مالک: {total_admin_pays:,}  |  مالک→ادمین: {total_owner_pays:,}",
    ]
    if not rows:
        return "\n".join(lines + ["", "در این بازه تراکنشی ثبت نشده است."])

    for i, r in enumerate(rows, 1):
        pct = int(r.get("percent") or 0)
        lines += [
            "",
            f"{i}) 👤 {html_escape(r.get('admin_name') or r['admin_id'])}",
            f"   ➕{r['increase']:,}  🧾{r['settle']:,}  💹{r['fee']:,}  💼{pct}٪→{r['admin_share']:,}",
            f"   {settlement_line(r)}",
        ]
    return "\n".join(lines)


def html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_activities_list(sessions, day_keys: list[str] | None = None):
    keys = day_keys
    if keys is None:
        grouped = defaultdict(list)
        for s in sessions:
            grouped[s["started_at"].strftime("%Y-%m-%d")].append(s)
        keys = sorted(grouped.keys(), reverse=True)
    if not keys:
        return (
            "📋 بازه‌های فعالیت\n\n"
            "هنوز بازه‌ای ثبت نشده.\n"
            "با «شروع فعالیت» اولین بازه ساخته می‌شود."
        )
    grouped = defaultdict(list)
    for s in sessions:
        grouped[s["started_at"].strftime("%Y-%m-%d")].append(s)
    lines = ["📋 بازه‌های فعالیت", _SEP]
    for day_key in keys:
        day_sessions = grouped.get(day_key) or []
        try:
            from datetime import datetime as _dt
            sample_dt = timezone.make_aware(_dt.strptime(day_key, "%Y-%m-%d"))
            sample_local = timezone.localtime(sample_dt)
        except Exception:
            sample_local = timezone.localtime()
        weekday = PERSIAN_WEEKDAYS[sample_local.weekday()]
        jdate = jdatetime.datetime.fromgregorian(datetime=sample_local).strftime("%Y/%m/%d")
        n = len(day_sessions)
        active_cnt = sum(1 for s in day_sessions if s.get("is_active"))
        if n:
            extra = f"{n} بازه"
            if active_cnt:
                extra += f" · 🟢{active_cnt}"
        else:
            extra = "خارج از برنامه"
        lines.append(f"📆 {weekday} {jdate} — {extra}")
    return "\n".join(lines)


def render_day_sessions(sessions, day_key: str, offs: list[dict] | None = None):
    day_sessions = [s for s in sessions if s["started_at"].strftime("%Y-%m-%d") == day_key]
    offs = offs or []
    if not day_sessions and not offs:
        return "📭 در این روز بازه‌ای ثبت نشده است."
    try:
        from datetime import datetime as _dt
        sample = timezone.localtime(timezone.make_aware(_dt.strptime(day_key, "%Y-%m-%d")))
    except Exception:
        sample = (day_sessions or offs)[0]["started_at"]
    weekday = PERSIAN_WEEKDAYS[sample.weekday()]
    jdate = jdatetime.datetime.fromgregorian(datetime=sample).strftime("%Y/%m/%d")
    lines = [f"📆 {weekday} — {jdate}", _SEP]
    if day_sessions:
        for s in sorted(day_sessions, key=lambda x: x["started_at"]):
            status = "🟢" if s.get("is_active") else "⚫"
            end_txt = s["ended_at"].strftime("%H:%M") if s.get("ended_at") else "..."
            lines.append(
                f"{status} {s['started_at']:%H:%M}→{end_txt} | {html_escape(s.get('admin_name', ''))}"
            )
            lines.append(f"   {settlement_line_signed(s.get('session_net', s.get('net', 0)))}")
            bits = []
            ch_n = int(s.get("challenge_count") or 0)
            if ch_n > 0:
                bits.append(f"🏆{ch_n}")
            lg_n = int(s.get("league_prize_count") or 0)
            if lg_n > 0:
                bits.append(f"🏅{lg_n}")
            if bits:
                lines.append(f"   {' · '.join(bits)}")
    if offs:
        if day_sessions:
            lines.append("")
        lines.append("🟠 خارج از برنامه")
        for o in offs:
            active = " · امروز" if o.get("is_active") else ""
            lines.append(
                f"🟠 {html_escape(o.get('admin_name', ''))}{active}"
            )
            lines.append(f"   {settlement_line_signed(o.get('session_net', o.get('net', 0)))}")
    return "\n".join(lines)


def render_session_card(session: dict) -> str:
    """کپشن کامل بازه — دکمه‌ها فقط برای ریز/عملیات."""
    from html import escape as html_escape
    admin_name_raw = session.get("admin_name") or session.get("admin_id")
    admin_name = html_escape(admin_name_raw)
    session_net = int(session.get("session_net", 0))
    pct = int(session.get("percent") or 0)
    if session.get("is_offschedule"):
        status = "🟠 خارج از برنامه" + (" · باز" if session.get("is_active") else "")
        title = "📊 خارج از برنامه"
    else:
        status = "🟢 فعال" if session.get("is_active") else "⚫ بسته"
        title = "📊 بازه فعالیت"

    lines = [
        title,
        _SEP,
        f"👤 {admin_name}",
        f"📅 {_session_time_line(session)}",
        f"📌 {status}",
        "",
        "📦 عملکرد",
        f"  ➕ افزایش: {int(session.get('increase', 0) or 0):,}",
        f"  🧾 تسویه: {int(session.get('settle', 0) or 0):,}",
        f"  💹 حق واسطه: {int(session.get('fee', 0) or 0):,}",
        f"  💼 سهم ادمین ({pct}٪): {int(session.get('admin_share', 0) or 0):,}",
        f"  💵 تراز نقدی: {_fmt_money(session.get('cash_balance', 0))}",
    ]
    if not session.get("is_offschedule"):
        end_bal = session.get("end_group_balance")
        end_txt = f"{int(end_bal):,}" if end_bal is not None else "—"
        lines.append(
            f"  🏦 تراز گروه: {int(session.get('start_group_balance', 0) or 0):,} → {end_txt}"
        )
    ch_n = int(session.get("challenge_count") or 0)
    lg_n = int(session.get("league_prize_count") or 0)
    if ch_n or lg_n:
        lines.append("")
        if ch_n:
            lines.append(
                f"🏆 چالش: {ch_n} · {int(session.get('challenge_prize_total') or 0):,} واحد"
            )
        if lg_n:
            lines.append(
                f"🏅 لیگ: {lg_n} · {int(session.get('league_prize_total') or 0):,} واحد"
            )
    lines += ["", "🏁 نتیجه", _settlement_footer(session_net, str(admin_name_raw))]
    return "\n".join(lines)


def _end_balance_label(session: dict) -> str:
    return "الان" if session.get("is_active") else "پایان"


def _settle_direction_label(net: int) -> str:
    n = int(net or 0)
    if n > 0:
        return f"ادمین→مالک: {n:,}"
    if n < 0:
        return f"مالک→ادمین: {abs(n):,}"
    return "تسویه: ۰"


def render_session_balances_info(session: dict) -> str:
    if session.get("is_offschedule"):
        return "\n".join([
            "💼 تراز کل گروه",
            _SUB,
            "  ℹ️ برای بازه خارج از برنامه ثبت نمی‌شود.",
            "  فقط افزایش/تسویه/حق‌واسطه همین ادمین خارج از شیفت محاسبه می‌شود.",
        ])
    end_bal = session.get("end_group_balance")
    end_lbl = _end_balance_label(session)
    end_txt = f"{end_bal:,}" if end_bal is not None else "—"
    return "\n".join([
        "💼 تراز کل گروه (اطلاعاتی)",
        _SUB,
        f"  شروع: {session.get('start_group_balance', 0):,}",
        f"  {end_lbl}: {end_txt}",
        f"  تغییر: {_fmt_money(session.get('balance_delta', 0))}",
        "  ℹ️ در تسویه این ادمین لحاظ نمی‌شود",
    ])


def render_session_activity_info(session: dict) -> str:
    pct = int(session.get("percent") or 0)
    title = "📦 فعالیت خارج از برنامه" if session.get("is_offschedule") else "📦 فعالیت این ادمین"
    lines = [title, _SUB]
    lines.extend(_amount_lines([
        ("➕ افزایش", session.get("increase", 0)),
        ("🧾 تسویه", session.get("settle", 0)),
        ("💹 حق واسطه", session.get("fee", 0)),
        (f"💼 سهم ادمین ({pct}٪)", session.get("admin_share", 0)),
        ("👑 سهم مالک", session.get("owner_fee", 0)),
        ("💵 تراز نقدی", session.get("cash_balance", 0)),
    ], empty="بدون تراکنش مستقیم"))
    lines.append(f"🏆 تعداد چالش: {int(session.get('challenge_count') or 0)}")
    lines.append(
        f"🎁 جمع واحد چالش‌ها: {int(session.get('challenge_prize_total') or 0):,}"
    )
    lines.append(f"🏅 تعداد جایزه لیگ: {int(session.get('league_prize_count') or 0)}")
    lines.append(
        f"🎁 جمع جایزه لیگ: {int(session.get('league_prize_total') or 0):,}"
    )
    lines.append("  ℹ️ جوایز لیگ از طرف مالک است و در افزایش ادمین لحاظ نمی‌شود")
    return "\n".join(lines)


def render_session_others_info(session: dict) -> str:
    other_items = [
        ("➕ افزایش", session.get("other_increase", 0)),
        ("🧾 تسویه", session.get("other_settle", 0)),
    ]
    lines = ["👥 سایر ادمین‌ها (اطلاعاتی)", _SUB]
    if any(int(v or 0) for _, v in other_items):
        lines.extend(_amount_lines(other_items, empty="بدون فعالیت"))
        lines.append("  ℹ️ در تسویه این ادمین لحاظ نمی‌شود")
    else:
        lines.append("  بدون فعالیت سایر ادمین‌ها")
    other_fee = int(session.get("other_fee", 0) or 0)
    if other_fee:
        lines.append(
            f"  ℹ️ حق‌واسطه سایرین ({other_fee:,}) فقط بین همان ادمین و مالک است"
        )
    return "\n".join(lines)


def render_session_hourly_info(session: dict) -> str:
    hourly = session.get("hourly") or []
    lines = ["🕒 ریز ساعتی", _SUB]
    if not hourly:
        lines.append("  بدون داده ساعتی")
        return "\n".join(lines)
    for h in hourly:
        lines.append(
            f"  {h['hour']}  ➕{h['increase']:,}  🧾{h['settle']:,}  "
            f"💹{h['fee']:,}  🎲{h['games']}"
        )
    return "\n".join(lines)


def _status_phrase(net: int, admin_name: str = "ادمین") -> str:
    n = int(net or 0)
    name = (admin_name or "ادمین").strip()
    if n > 0:
        return f"ادمین ({name}) → مالک | {n:,}"
    if n < 0:
        return f"مالک → ادمین ({name}) | {abs(n):,}"
    return "تسویه صفر"


def _fee_event_reason(amount: int, description: str = "") -> str:
    """عنوان رویداد حق واسطه: پیوی/گروهی + نوع شرط (فیکس/اضافه)."""
    desc = (description or "").strip()
    dlow = desc.lower()
    if "پیوی" in desc or "pv" in dlow:
        channel = "پیوی"
    else:
        channel = "گروهی"
    if "فیکس" in desc or "fixed" in dlow:
        mode = "فیکس"
    elif "اضافه" in desc or "extra" in dlow:
        mode = "اضافه"
    else:
        mode = ""
    if mode:
        return f"حق واسطه بازی {channel} · {mode} (+{amount:,})"
    return f"حق واسطه بازی {channel} (+{amount:,})"


def build_settlement_timeline(
    chat_id, admin_id, start, end, share_percent, admin_name="ادمین", *, offschedule=False,
):
    qs = _exclude_game_wallet_txs(
        WalletTransaction.objects.filter(
            telegram_chat_id=int(chat_id),
            admin_id=int(admin_id),
            created_at__gte=start,
            created_at__lt=end,
            type__in=("admin_increase", "fee") + _SETTLE_TYPES,
        )
    )
    if offschedule:
        qs = _exclude_admin_session_windows(qs, chat_id, admin_id)
    qs = qs.order_by("created_at", "id")

    inc = settle = fee = 0
    prev_net = 0
    events = []
    for tx in qs:
        amt = abs(int(tx.amount or 0))
        desc = (tx.description or "").strip()
        if tx.type == "admin_increase":
            inc += amt
            reason = f"افزایش موجودی عضو (+{amt:,})"
        elif tx.type in _SETTLE_TYPES:
            settle += amt
            reason = f"تسویه/کاهش عضو (−{amt:,})"
        elif tx.type == "fee":
            fee += amt
            reason = _fee_event_reason(amt, desc)
        else:
            continue
        fin = compute_financials(inc, settle, fee, share_percent)
        net = int(fin["net"])
        events.append({
            "time": timezone.localtime(tx.created_at),
            "reason": reason,
            "delta": net - prev_net,
            "net": net,
            "increase": inc,
            "settle": settle,
            "fee": fee,
            "admin_share": fin["admin_share"],
            "owner_fee": fin["owner_fee"],
            "description": desc,
        })
        prev_net = net
    return events


def render_settlement_timeline(session: dict, events: list, page: int = 1) -> tuple[str, int, int]:
    admin_name = session.get("admin_name") or session.get("admin_id") or "ادمین"
    pct = int(session.get("percent") or 0)
    total = len(events or [])
    pages = max(1, (total + TIMELINE_PAGE_SIZE - 1) // TIMELINE_PAGE_SIZE) if total else 1
    page = max(1, min(int(page or 1), pages))
    start = (page - 1) * TIMELINE_PAGE_SIZE
    chunk = (events or [])[start : start + TIMELINE_PAGE_SIZE]

    lines = [
        "📟 گزارش تسویه لحظه‌ای با مالک",
        _SEP,
        f"👤 ادمین: {admin_name}",
        f"📅 {_session_time_line(session)}",
        f"💼 سهم ادمین از حق‌واسطه: {pct}٪",
        f"📄 صفحه {page} از {pages}" + (f" — {total} رویداد" if total else ""),
        "",
        "هر ردیف بعد از یک تراکنش مرتبط با این ادمین است.",
        "مبلغ «تا این لحظه» همان بدهی/طلب بین مالک و ادمین است.",
        _SUB,
    ]
    if not events:
        lines += ["", "هنوز تراکنشی برای محاسبه تسویه ثبت نشده است."]
        return "\n".join(lines), page, pages
    for ev in chunk:
        t = ev["time"].strftime("%H:%M")
        delta = int(ev["delta"])
        delta_txt = f"+{delta:,}" if delta > 0 else f"{delta:,}"
        extra = f"\n  📝 {ev['description']}" if ev.get("description") else ""
        lines += [
            "",
            f"🕒 {t}",
            f"  📌 رویداد: {ev['reason']}{extra}",
            f"  🔄 تغییر وضعیت: {delta_txt}",
            f"  💹 تا این لحظه: {_status_phrase(ev['net'], admin_name)}",
            f"  📦 افزایش {ev['increase']:,} | تسویه {ev['settle']:,} | حق‌واسطه {ev['fee']:,}",
            f"  ✂️ سهم ادمین {ev['admin_share']:,} | سهم مالک {ev['owner_fee']:,}",
        ]
    last = events[-1]
    lines += [
        "",
        _SEP,
        "🏁 وضعیت نهایی کل بازه",
        f"  {_status_phrase(last['net'], admin_name)}",
    ]
    if page < pages:
        lines.append(f"⬇️ ادامه در صفحه بعد ({page + 1}/{pages})")
    return "\n".join(lines), page, pages


def timeline_keyboard(chat_id, session_id, page: int, pages: int):
    chat_id = int(chat_id)
    prefix = f"aareport:{chat_id}:act:{session_id}:live"
    kb = [
        [
            InlineKeyboardButton(text="⏪", callback_data=f"{prefix}:{max(1, page - 2)}"),
            InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{max(1, page - 1)}"),
            InlineKeyboardButton(text=f"📄 {page}/{pages}"[:40], callback_data=f"{prefix}:go"),
            InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{min(pages, page + 1)}"),
            InlineKeyboardButton(text="⏩", callback_data=f"{prefix}:{min(pages, page + 2)}"),
        ],
        [InlineKeyboardButton(text="🔙 بازه", callback_data=f"aareport:{chat_id}:act:{session_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def timeline_pages_keyboard(chat_id, session_id, page: int, pages: int):
    chat_id = int(chat_id)
    prefix = f"aareport:{chat_id}:act:{session_id}:live"
    kb = []
    row = []
    for p in range(1, pages + 1):
        label = f"•{p}•" if p == page else str(p)
        row.append(InlineKeyboardButton(text=label, callback_data=f"{prefix}:{p}"))
        if len(row) == 5:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به گزارش", callback_data=f"{prefix}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@sync_to_async
def get_settlement_timeline(chat_id, session_id):
    parsed = parse_offschedule_id(session_id)
    if parsed:
        admin_id, day_key = parsed
        row = _build_offschedule_row(chat_id, admin_id, day_key, detail=True)
        start, end = _day_bounds(day_key)
        now = timezone.now()
        if timezone.localtime(now).strftime("%Y-%m-%d") == day_key:
            end = min(end, now)
        events = build_settlement_timeline(
            chat_id, admin_id, start, end,
            row.get("percent") or 50, row.get("admin_name") or "ادمین",
            offschedule=True,
        )
        return row, events
    session = AdminActivitySession.objects.filter(
        telegram_chat_id=int(chat_id), id=int(session_id)
    ).first()
    if not session:
        return None, []
    row = _build_session_row(chat_id, session, detail=True)
    end = session.ended_at or timezone.now()
    events = build_settlement_timeline(
        chat_id, session.admin_id, session.started_at, end,
        row.get("percent") or 50, row.get("admin_name") or "ادمین",
    )
    return row, events


def render_session_detail(session: dict) -> str:
    admin_name = session.get("admin_name") or session.get("admin_id")
    parts = [
        render_session_card(session),
        "",
        render_session_balances_info(session),
        "",
        render_session_activity_info(session),
    ]
    if any(int(session.get(k, 0) or 0) for k in ("other_increase", "other_settle", "other_fee")):
        parts += ["", render_session_others_info(session)]
    parts += ["", *_render_session_calc(session, str(admin_name))]
    if session.get("hourly"):
        parts += ["", render_session_hourly_info(session)]
    return "\n".join(parts)


def format_closed_session_summary(session: dict | None) -> str:
    if not session:
        return ""
    lines = [
        "",
        "📋 خلاصه بازه بسته‌شده",
        f"👤 {session.get('admin_name') or session.get('admin_id')}",
        f"💼 تراز: {session.get('start_group_balance', 0):,} → {session.get('end_group_balance', 0):,}",
        settlement_line_signed(session.get("session_net", 0)),
    ]
    lg_n = int(session.get("league_prize_count") or 0)
    if lg_n > 0:
        lines.append(
            f"🏅 لیگ: {lg_n} جایزه · {int(session.get('league_prize_total') or 0):,} واحد (مالک)"
        )
    return "\n".join(lines)


def format_start_activity_group(result: dict) -> str:
    if result.get("already_active"):
        return "ℹ️ فعالیت شما از قبل فعال است."
    msg = "✅ فعالیت شروع شد.\n"
    if result.get("closed_session"):
        msg += "📲 جزئیات مالی بازه قبلی به پیوی مدیران ارسال شد."
    return msg


def format_end_activity_group(result: dict) -> str:
    if not result.get("had_active"):
        return (
            "ℹ️ فعالیت فعالی وجود نداشت.\n"
            "💳 دستور «کارت» هم‌اکنون کارت مالک را نشان می‌دهد."
        )
    return (
        "✅ فعالیت پایان یافت.\n"
        "📲 جزئیات مالی بازه به پیوی مدیران ارسال شد.\n"
        "💳 از این پس «کارت»، کارت مالک را نشان می‌دهد."
    )


async def notify_all_admins_pm(bot, chat_id, text: str, *, reply_markup=None) -> int:
    from bot.cache_manager import is_admin, is_owner

    try:
        admins = await bot.get_chat_administrators(int(chat_id))
    except Exception:
        return 0
    delivered = 0
    sent = set()
    for adm in admins:
        uid = adm.user.id
        if uid in sent or adm.user.is_bot:
            continue
        if not (is_owner(int(chat_id), uid) or is_admin(int(chat_id), uid)):
            continue
        sent.add(uid)
        try:
            await bot.send_message(
                uid,
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
            delivered += 1
        except Exception:
            pass
    return delivered


async def deliver_closed_session_pm(bot, chat_id, session: dict | None) -> int:
    if not session:
        return 0
    kb = report_keyboard(
        chat_id, [], session_id=session["id"], selected_admin=session["admin_id"], session=session,
    )
    return await notify_all_admins_pm(
        bot, chat_id, render_session_card(session), reply_markup=kb,
    )


async def deliver_active_session_pm(bot, chat_id, session: dict | None) -> int:
    if not session:
        return 0
    kb = report_keyboard(
        chat_id, [], session_id=session["id"], selected_admin=session["admin_id"], session=session,
    )
    return await notify_all_admins_pm(
        bot, chat_id, render_session_card(session), reply_markup=kb,
    )


def format_activity_so_far_group(session: dict | None) -> str:
    if not session:
        return "ℹ️ فعالیت فعالی وجود ندارد."
    name = session.get("admin_name") or session.get("admin_id")
    return (
        f"📲 گزارش لحظه‌ای بازه «{name}» به پیوی همه مدیران ارسال شد.\n"
        "ℹ️ بازه هنوز باز است — برای بستن: «پایان فعالیت»"
    )


def remember_context(chat_id, viewer_id):
    _report_context[str(viewer_id)] = int(chat_id)


def report_keyboard(chat_id, rows, mode="0", selected_admin=None, session_id=None, session=None):
    chat_id = int(chat_id)
    kb = []
    if session_id:
        snap = session or {}
        pct_now = int(snap.get("percent", 50) or 50)
        prefix = f"aareport:{chat_id}:act:{session_id}"
        admin_for_share = selected_admin or snap.get("admin_id")
        # فقط عملیات — اعداد داخل کپشن
        kb.append([
            InlineKeyboardButton(text="➕ ریز افزایش", callback_data=f"{prefix}:{admin_for_share}:increase" if admin_for_share else f"{prefix}:info:act"),
            InlineKeyboardButton(text="🧾 ریز تسویه", callback_data=f"{prefix}:{admin_for_share}:settle" if admin_for_share else f"{prefix}:info:act"),
        ])
        if admin_for_share:
            kb.append([
                InlineKeyboardButton(text="💹 حق واسطه", callback_data=f"{prefix}:{admin_for_share}:fee"),
                InlineKeyboardButton(text="🎲 بازی‌ها", callback_data=f"{prefix}:{admin_for_share}:games"),
            ])
        kb.append([
            InlineKeyboardButton(text="📦 جزئیات ادمین", callback_data=f"{prefix}:info:act"),
            InlineKeyboardButton(text="🕒 ساعتی", callback_data=f"{prefix}:info:hour"),
        ])
        kb.append([
            InlineKeyboardButton(text="📟 تسویه لحظه‌ای", callback_data=f"{prefix}:live"),
        ])
        kb.append([
            InlineKeyboardButton(
                text=f"💼 سهم {pct_now}٪"[:40],
                callback_data=f"aareport:{chat_id}:share:{admin_for_share}:{session_id}" if admin_for_share else prefix,
            ),
        ])
        kb.append([
            InlineKeyboardButton(text="🔄", callback_data=prefix),
            InlineKeyboardButton(text="📋 بازه‌ها", callback_data=f"aareport:{chat_id}:actlist"),
        ])
        return InlineKeyboardMarkup(inline_keyboard=kb)

    kb.append(
        [
            InlineKeyboardButton(text="امروز", callback_data=f"aareport:{chat_id}:0"),
            InlineKeyboardButton(text="دیروز", callback_data=f"aareport:{chat_id}:1"),
            InlineKeyboardButton(text="پریروز", callback_data=f"aareport:{chat_id}:2"),
            InlineKeyboardButton(text="هفتگی", callback_data=f"aareport:{chat_id}:w"),
        ]
    )
    kb.append(
        [
            InlineKeyboardButton(text="🔄", callback_data=f"aareport:{chat_id}:{mode}"),
            InlineKeyboardButton(text="📋 بازه‌ها", callback_data=f"aareport:{chat_id}:actlist"),
        ]
    )

    prefix = f"aareport:{chat_id}:{mode}"
    for i in range(0, len(rows), 2):
        row_btns = []
        for r in rows[i : i + 2]:
            name = (r.get("admin_name") or str(r["admin_id"]))[:20]
            row_btns.append(
                InlineKeyboardButton(
                    text=name, callback_data=f"{prefix}:{r['admin_id']}"
                )
            )
        kb.append(row_btns)

    if selected_admin:
        kb.append(
            [
                InlineKeyboardButton(text="🧾 تسویه", callback_data=f"{prefix}:{selected_admin}:settle"),
                InlineKeyboardButton(text="➕ افزایش", callback_data=f"{prefix}:{selected_admin}:increase"),
            ]
        )
        kb.append(
            [
                InlineKeyboardButton(text="💹 حق واسطه", callback_data=f"{prefix}:{selected_admin}:fee"),
                InlineKeyboardButton(text="🎲 بازی‌ها", callback_data=f"{prefix}:{selected_admin}:games"),
            ]
        )
        kb.append([
            InlineKeyboardButton(
                text="💼 سهم ادمین",
                callback_data=f"aareport:{chat_id}:share:{selected_admin}",
            ),
        ])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def activities_keyboard(chat_id, sessions, *, day_key: str | None = None, session_id=None, offs=None, day_keys=None):
    chat_id = int(chat_id)
    kb = []
    if day_key:
        day_sessions = [
            s for s in sessions if s["started_at"].strftime("%Y-%m-%d") == day_key
        ]
        for s in sorted(day_sessions, key=lambda x: x["started_at"]):
            start = s["started_at"]
            label = f"{'🟢' if s['is_active'] else '⚫'} {start:%H:%M} {s['admin_name'][:12]}"
            kb.append(
                [InlineKeyboardButton(text=label[:40], callback_data=f"aareport:{chat_id}:act:{s['id']}")]
            )
        for o in (offs or []):
            label = f"🟠 {(str(o.get('admin_name') or o['admin_id']))[:14]}"
            kb.append(
                [InlineKeyboardButton(text=label[:40], callback_data=f"aareport:{chat_id}:act:{o['id']}")]
            )
        kb.append([
            InlineKeyboardButton(text="📋 روزها", callback_data=f"aareport:{chat_id}:actlist"),
            InlineKeyboardButton(text="📊 امروز", callback_data=f"aareport:{chat_id}:0"),
        ])
        return InlineKeyboardMarkup(inline_keyboard=kb)

    keys = day_keys
    if keys is None:
        grouped = defaultdict(list)
        for s in sessions:
            grouped[s["started_at"].strftime("%Y-%m-%d")].append(s)
        keys = sorted(grouped.keys(), reverse=True)[:14]
    grouped = defaultdict(list)
    for s in sessions:
        grouped[s["started_at"].strftime("%Y-%m-%d")].append(s)
    row_btns = []
    for dk in keys[:14]:
        sample = grouped[dk][0]["started_at"] if grouped.get(dk) else None
        if sample:
            label = f"📆 {sample:%m/%d}"
            if grouped[dk]:
                label += f" ({len(grouped[dk])})"
        else:
            label = f"📆 {dk[5:]}"
        row_btns.append(
            InlineKeyboardButton(text=label[:40], callback_data=f"aareport:{chat_id}:actday:{dk}")
        )
        if len(row_btns) == 2:
            kb.append(row_btns)
            row_btns = []
    if row_btns:
        kb.append(row_btns)
    kb.append([InlineKeyboardButton(text="📊 گزارش امروز", callback_data=f"aareport:{chat_id}:0")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@sync_to_async
def admin_detail_report(chat_id, admin_id, mode, kind, page=1, session_id=None):
    start, end, session_meta = _report_bounds(mode, session_id)
    type_map = {
        "settle": ("admin_decrease", "admin_clear"),
        "increase": ("admin_increase",),
        "fee": ("fee",),
        "games": ("bet", "game_bet", "game_start"),
    }
    qs = WalletTransaction.objects.filter(
        telegram_chat_id=chat_id,
        admin_id=int(admin_id),
        created_at__gte=start,
        created_at__lt=end,
        type__in=type_map.get(kind, ()),
    ).order_by("-created_at", "-id")
    if isinstance(session_meta, tuple) and session_meta and session_meta[0] == "off":
        qs = _exclude_admin_session_windows(qs, chat_id, admin_id)
    total = qs.count()
    total_pages = max(1, (total + DETAIL_PAGE_SIZE - 1) // DETAIL_PAGE_SIZE)
    page = max(1, min(int(page or 1), total_pages))
    items = []
    for tx in qs[(page - 1) * DETAIL_PAGE_SIZE : page * DETAIL_PAGE_SIZE]:
        member_name = (
            TelegramGroupMember.objects.filter(
                telegram_chat_id=chat_id, telegram_user_id=tx.telegram_user_id
            )
            .values_list("alias", flat=True)
            .first()
            or ""
        ).strip()
        items.append(
            {
                "user_id": tx.telegram_user_id,
                "member_name": member_name,
                "amount": abs(tx.amount or 0),
                "balance_after": tx.balance_after or 0,
                "description": (tx.description or "").strip(),
                "created_at": timezone.localtime(tx.created_at),
            }
        )
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": total_pages,
        "admin_id": int(admin_id),
        "admin_name": _admin_name(chat_id, admin_id),
    }


def render_detail_report(data, mode, kind, session_id=None):
    labels = {
        "settle": "تسویه‌ها",
        "increase": "افزایش موجودی‌ها",
        "fee": "حق واسطه‌ها",
        "games": "بازی‌های شروع‌شده",
    }
    period = session_title(session_id) if session_id else period_label(mode)
    lines = [
        f"📑 ریز {labels.get(kind, 'فعالیت‌ها')}",
        f"📅 {period}",
        f"👤 {html_escape(data.get('admin_name') or data['admin_id'])}",
        f"🆔 <code>{data['admin_id']}</code>",
        f"📄 صفحه {data['page']} از {data['pages']} — کل: {data['total']}",
        "━━━━━━━━━━━━━━━━━━",
    ]
    if not data["items"]:
        lines.append("موردی در این بازه ثبت نشده است.")
        return "\n".join(lines)
    base = (data["page"] - 1) * DETAIL_PAGE_SIZE
    for index, item in enumerate(data["items"], base + 1):
        lines.extend(
            [
                f"\n{index}) {html_escape(item['member_name'] or item['user_id'])}",
                f"🆔 <code>{item['user_id']}</code>",
                f"🕒 {item['created_at']:%H:%M:%S}",
                f"💰 {item['amount']:,}",
                f"👛 موجودی بعد: {item['balance_after']:,}",
            ]
        )
        if item["description"]:
            lines.append(f"📝 {html_escape(item['description'])}")
    return "\n".join(lines)


def detail_keyboard(chat_id, mode, admin_id, kind, page, pages, session_id=None):
    chat_id = int(chat_id)
    prefix = f"aareport:{chat_id}:act:{session_id}" if session_id else f"aareport:{chat_id}:{mode}"
    row = []
    if page > 1:
        row.append(
            InlineKeyboardButton(
                text="◀️ قبل", callback_data=f"{prefix}:{admin_id}:{kind}:{page - 1}"
            )
        )
    if page < pages:
        row.append(
            InlineKeyboardButton(
                text="بعد ▶️", callback_data=f"{prefix}:{admin_id}:{kind}:{page + 1}"
            )
        )
    kb = [row] if row else []
    back = f"{prefix}:{admin_id}" if session_id else f"aareport:{chat_id}:{mode}:{admin_id}"
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=back)])
    if session_id:
        kb.append(
            [InlineKeyboardButton(text="📋 لیست بازه‌ها", callback_data=f"aareport:{chat_id}:actlist")]
        )
    return InlineKeyboardMarkup(inline_keyboard=kb)


async def _send_fresh_message(bot, user_id, text, reply_markup=None):
    ts = timezone.localtime().strftime("%H:%M:%S")
    await bot.send_message(
        user_id,
        f"🔄 {ts}\n\n{text}",
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def handle_report_callback(call, bot):
    parts = call.data.split(":")
    if len(parts) < 3 or parts[0] != "aareport":
        return False
    chat_id = int(parts[1])
    mode = parts[2]
    uid = call.from_user.id
    detail_kinds = {"settle", "increase", "fee", "games"}

    if mode == "actlist":
        sessions = await list_activity_sessions(chat_id)
        day_keys = await list_activity_day_keys(chat_id)
        text = render_activities_list(sessions, day_keys)
        kb = activities_keyboard(chat_id, sessions, day_keys=day_keys)
        await _send_fresh_message(bot, uid, text, kb)
        await call.answer()
        return True

    if mode == "share":
        from bot.cache_manager import is_owner
        if not is_owner(chat_id, uid):
            await call.answer("فقط مالک", show_alert=True)
            return True
        # aareport:chat:share:admin
        # aareport:chat:share:admin:sid
        # aareport:chat:share:admin:set:PCT
        # aareport:chat:share:admin:sid:set:PCT
        # aareport:chat:share:admin:custom
        # aareport:chat:share:admin:sid:custom
        admin_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
        if admin_id is None:
            await call.answer("ادمین نامعتبر", show_alert=True)
            return True

        session_id = None
        set_pct = None
        want_custom = False
        if len(parts) >= 6 and parts[-2] == "set":
            set_pct = int(parts[-1])
            if len(parts) >= 7:
                session_id = parts[4]
        elif len(parts) >= 5 and parts[4] == "set" and len(parts) >= 6:
            set_pct = int(parts[5])
        elif len(parts) >= 5 and parts[-1] == "custom":
            want_custom = True
            if len(parts) >= 6:
                session_id = parts[4]
        elif len(parts) >= 5:
            session_id = parts[4]

        if set_pct is not None:
            new_pct = await set_share(chat_id, admin_id, set_pct)
            pop_share_wait(uid)
            await call.answer(f"سهم {new_pct}٪ شد", show_alert=True)
            if session_id:
                session = await get_activity_session(chat_id, session_id)
                if session:
                    kb = report_keyboard(
                        chat_id, [], session_id=session_id,
                        selected_admin=session["admin_id"], session=session,
                    )
                    await _send_fresh_message(bot, uid, render_session_card(session), kb)
                    return True
            rows = await report(chat_id, "0")
            await _send_fresh_message(
                bot, uid, render(rows, "0"),
                report_keyboard(chat_id, rows, "0", selected_admin=admin_id),
            )
            return True

        if want_custom:
            set_share_wait(uid, chat_id=chat_id, admin_id=admin_id, session_id=session_id)
            await _send_fresh_message(
                bot, uid,
                "✏️ درصد دلخواه سهم ادمین را بنویسید\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "عدد بین ۰ تا ۱۰۰\n"
                "مثال: <code>45</code>\n\n"
                "برای لغو: لغو",
            )
            await call.answer()
            return True

        back = f"aareport:{chat_id}:act:{session_id}" if session_id else f"aareport:{chat_id}:0:{admin_id}"
        set_prefix = (
            f"aareport:{chat_id}:share:{admin_id}:{session_id}:set"
            if session_id else f"aareport:{chat_id}:share:{admin_id}:set"
        )
        custom_cb = (
            f"aareport:{chat_id}:share:{admin_id}:{session_id}:custom"
            if session_id else f"aareport:{chat_id}:share:{admin_id}:custom"
        )
        cur_pct = await get_admin_share_percent(chat_id, admin_id)
        admin_name = str(admin_id)
        try:
            u = await bot.get_chat(admin_id)
            admin_name = (u.full_name or u.first_name or "").strip() or str(admin_id)
        except Exception:
            pass
        if session_id:
            session = await get_activity_session(chat_id, session_id)
            if session and session.get("admin_name"):
                admin_name = session["admin_name"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="0٪", callback_data=f"{set_prefix}:0"),
                InlineKeyboardButton(text="30٪", callback_data=f"{set_prefix}:30"),
                InlineKeyboardButton(text="50٪", callback_data=f"{set_prefix}:50"),
            ],
            [
                InlineKeyboardButton(text="70٪", callback_data=f"{set_prefix}:70"),
                InlineKeyboardButton(text="100٪", callback_data=f"{set_prefix}:100"),
            ],
            [InlineKeyboardButton(text="✏️ عدد دلخواه", callback_data=custom_cb)],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=back)],
        ])
        await _send_fresh_message(
            bot, uid,
            "💼 تغییر سهم ادمین از حق‌واسطه\n\n"
            f"ادمین: {admin_name}\n"
            f"درصد فعلی: {cur_pct}٪\n\n"
            "درصد دلخواه را از دکمه‌ها انتخاب کنید\n"
            "یا «✏️ عدد دلخواه» را بزنید.",
            kb,
        )
        await call.answer()
        return True

    if mode == "actday":
        day_key = parts[3] if len(parts) > 3 else None
        if not day_key:
            await call.answer("روز نامعتبر", show_alert=True)
            return True
        sessions = await list_activity_sessions_for_day(chat_id, day_key)
        offs = await list_offschedule_day(chat_id, day_key)
        text = render_day_sessions(sessions, day_key, offs)
        kb = activities_keyboard(chat_id, sessions, day_key=day_key, offs=offs)
        await _send_fresh_message(bot, uid, text, kb)
        await call.answer()
        return True

    if mode == "act":
        session_id = parts[3] if len(parts) > 3 else None
        if not session_id:
            sessions = await list_activity_sessions(chat_id)
            day_keys = await list_activity_day_keys(chat_id)
            await _send_fresh_message(
                bot, uid,
                render_activities_list(sessions, day_keys),
                activities_keyboard(chat_id, sessions, day_keys=day_keys),
            )
            await call.answer()
            return True

        selected_admin = None
        kind = None
        page = 1
        info_kind = None
        live_page = None
        live_go = False
        if len(parts) > 4 and parts[4] == "info":
            info_kind = parts[5] if len(parts) > 5 else "bal"
        elif len(parts) > 4 and parts[4] == "live":
            # aareport:chat:act:sid:live
            # aareport:chat:act:sid:live:PAGE
            # aareport:chat:act:sid:live:go
            if len(parts) > 5 and parts[5] == "go":
                live_go = True
                live_page = 1
            elif len(parts) > 5 and parts[5].isdigit():
                live_page = int(parts[5])
            else:
                live_page = 1
            info_kind = "live"
        elif len(parts) > 4 and parts[4].isdigit():
            selected_admin = int(parts[4])
            if len(parts) > 5 and parts[5] in detail_kinds:
                kind = parts[5]
                try:
                    page = int(parts[6]) if len(parts) > 6 else 1
                except (TypeError, ValueError):
                    page = 1

        if info_kind:
            session = await get_activity_session(chat_id, session_id)
            if not session:
                await call.answer("بازه یافت نشد", show_alert=True)
                return True
            admin_name = str(session.get("admin_name") or session.get("admin_id") or "ادمین")
            kb = None
            if info_kind == "bal":
                text = render_session_balances_info(session)
            elif info_kind == "net":
                text = "🏁 نتیجه تسویه\n" + _SUB + "\n" + "\n".join(
                    _settlement_parties(int(session.get("session_net", 0)), admin_name)
                )
            elif info_kind == "act":
                text = render_session_activity_info(session)
            elif info_kind == "calc":
                text = "\n".join(_render_session_calc(session, admin_name))
            elif info_kind == "other":
                text = render_session_others_info(session)
            elif info_kind == "live":
                row, events = await get_settlement_timeline(chat_id, session_id)
                text, page_n, pages_n = render_settlement_timeline(
                    row or session, events, live_page or 1,
                )
                if live_go:
                    text = (
                        f"📄 انتخاب صفحه\n\n"
                        f"صفحه فعلی: {page_n} از {pages_n}\n"
                        "شماره صفحه را بزنید."
                    )
                    kb = timeline_pages_keyboard(chat_id, session_id, page_n, pages_n)
                else:
                    kb = timeline_keyboard(chat_id, session_id, page_n, pages_n)
            else:
                text = render_session_hourly_info(session)
            await _send_fresh_message(bot, uid, text, kb)
            await call.answer()
            return True

        if kind and selected_admin:
            detail = await admin_detail_report(
                chat_id, selected_admin, "0", kind, page, session_id=session_id
            )
            text = render_detail_report(detail, "0", kind, session_id=session_id)
            kb = detail_keyboard(chat_id, "0", selected_admin, kind, detail["page"], detail["pages"], session_id)
            await _send_fresh_message(bot, uid, text, kb)
            await call.answer()
            return True

        session = await get_activity_session(chat_id, session_id)
        if session:
            kb = report_keyboard(
                chat_id,
                [],
                session_id=session_id,
                selected_admin=session["admin_id"],
                session=session,
            )
            await _send_fresh_message(bot, uid, render_session_card(session), kb)
            await call.answer()
            return True

        rows = await report(chat_id, session_id=session_id)
        if selected_admin:
            rows = [r for r in rows if r["admin_id"] == int(selected_admin)]
        title = session_title(session_id)
        full_rows = await report(chat_id, session_id=session_id)
        await _send_fresh_message(
            bot,
            uid,
            render(rows, title),
            report_keyboard(chat_id, full_rows, session_id=session_id, selected_admin=selected_admin),
        )
        await call.answer()
        return True

    selected_admin = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
    if selected_admin and len(parts) > 4 and parts[4] in detail_kinds:
        try:
            page = int(parts[5]) if len(parts) > 5 else 1
        except (TypeError, ValueError):
            page = 1
        detail = await admin_detail_report(chat_id, selected_admin, mode, parts[4], page)
        text = render_detail_report(detail, mode, parts[4])
        kb = detail_keyboard(chat_id, mode, selected_admin, parts[4], detail["page"], detail["pages"])
        await _send_fresh_message(bot, uid, text, kb)
        await call.answer()
        return True

    rows = await report(chat_id, mode)
    if selected_admin:
        rows = [r for r in rows if r["admin_id"] == selected_admin]
    full_rows = await report(chat_id, mode)
    await _send_fresh_message(
        bot,
        uid,
        render(rows, mode),
        report_keyboard(chat_id, full_rows, mode, selected_admin=selected_admin),
    )
    await call.answer()
    return True
