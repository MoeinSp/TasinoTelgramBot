"""گزارش‌ها و داشبورد پنل سازنده (/admin)."""
from __future__ import annotations

import html
import math
from collections import defaultdict
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.db.models import Avg, Count, Sum
from django.utils import timezone

_D6_MEAN = 3.5
_D6_STD = math.sqrt(35 / 12)  # ≈ 1.7078
_P6 = 1 / 6


def _z(mean: float, n: int) -> float:
    if n <= 0:
        return 0.0
    return (mean - _D6_MEAN) / (_D6_STD / math.sqrt(n))


def _z_six(p6: float, n: int) -> float:
    if n <= 0:
        return 0.0
    se = math.sqrt(_P6 * (1 - _P6) / n)
    return (p6 - _P6) / se if se else 0.0


def _risk_label(z_mean: float, z_six: float, win_rate: float | None, games: int) -> str:
    score = 0
    if z_mean >= 3.0 or z_six >= 3.0:
        score += 3
    elif z_mean >= 2.3 or z_six >= 2.3:
        score += 2
    elif z_mean >= 1.8 or z_six >= 1.8:
        score += 1
    if win_rate is not None and games >= 8 and win_rate >= 0.75:
        score += 2
    elif win_rate is not None and games >= 8 and win_rate >= 0.65:
        score += 1
    if score >= 4:
        return "🔴 بالا"
    if score >= 2:
        return "🟠 متوسط"
    if score >= 1:
        return "🟡 ضعیف"
    return "🟢 عادی"


@sync_to_async
def build_dashboard() -> str:
    from account.models import (
        BalanceIncreaseRequest,
        DiceRollStat,
        TelegramGroup,
        TelegramGroupMember,
        WithdrawalRequest,
    )
    from bot import cache as bot_cache

    now = timezone.now()
    day_ago = now - timedelta(days=1)
    groups = TelegramGroup.objects.count()
    members = TelegramGroupMember.objects.count()
    wallets = TelegramGroupMember.objects.aggregate(s=Sum("point"))["s"] or 0
    wd_open = WithdrawalRequest.objects.filter(status__in=("pending", "receipt")).count()
    inc_open = BalanceIncreaseRequest.objects.filter(status__in=("waiting_receipt", "pending")).count()
    rolls_24h = DiceRollStat.objects.filter(rolled_at__gte=day_ago).count()
    off_n = len(bot_cache.OFF_GROUP)
    muted_n = sum(len(v) for v in (bot_cache.MUTED_USERS or {}).values())

    live_g = live_pv = invites = searches = 0
    try:
        from bot.dice_game import ACTIVE_GAMES
        live_g = len(ACTIVE_GAMES)
    except Exception:
        pass
    try:
        from bot.pv_dice import GAMES, INVITES
        live_pv = len(GAMES)
        invites = sum(1 for i in INVITES.values() if i.get("status") == "pending")
    except Exception:
        pass
    try:
        from bot.pv_search import SEARCH_OFFERS
        searches = sum(1 for o in SEARCH_OFFERS.values() if o.get("status") == "pending")
    except Exception:
        pass

    return (
        "🏠 <b>داشبورد سازنده</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 گروه‌ها: <b>{groups:,}</b>\n"
        f"👤 اعضا (رکورد): <b>{members:,}</b>\n"
        f"💰 مجموع موجودی‌ها: <b>{int(wallets):,}</b>\n"
        f"🎲 تاس ۲۴ساعت: <b>{rolls_24h:,}</b>\n\n"
        f"🎮 بازی گروهی زنده: <b>{live_g}</b>\n"
        f"⚔️ بازی پیوی زنده: <b>{live_pv}</b>\n"
        f"📨 دعوت پیوی باز: <b>{invites}</b>\n"
        f"🔎 جستجوی حریف: <b>{searches}</b>\n\n"
        f"📥 تسویه باز: <b>{wd_open}</b>\n"
        f"💸 افزایش باز: <b>{inc_open}</b>\n"
        f"🔇 سکوت فعال: <b>{muted_n}</b> · گروه خاموش: <b>{off_n}</b>\n"
        f"🧠 کش: {'✅' if bot_cache.CACHE_LOADED else '❌'}"
    )


@sync_to_async
def build_cheat_report(days: int = 7) -> str:
    from account.models import DiceGameHistory, DiceRollStat, TelegramGroupMember

    days = 7 if days not in (7, 30) else days
    since = timezone.now() - timedelta(days=days)
    rolls = (
        DiceRollStat.objects.filter(rolled_at__gte=since)
        .values("telegram_user_id", "value")
        .annotate(n=Count("id"))
    )
    by_user: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for row in rolls:
        by_user[int(row["telegram_user_id"])][int(row["value"])] = int(row["n"])

    from django.db.models import Q

    games = (
        DiceGameHistory.objects.filter(created_at__gte=since)
        .values("telegram_user_id")
        .annotate(
            g=Count("id"),
            w=Count("id", filter=Q(winner=True)),
            avg=Avg("average"),
            won=Sum("amount_won"),
        )
    )
    game_map = {int(r["telegram_user_id"]): r for r in games}

    flags = []
    for uid, faces in by_user.items():
        n = sum(faces.values())
        if n < 30:
            continue
        total = sum(v * c for v, c in faces.items())
        mean = total / n
        sixes = faces.get(6, 0)
        p6 = sixes / n
        zm = _z(mean, n)
        zs = _z_six(p6, n)
        ginfo = game_map.get(uid) or {}
        gcount = int(ginfo.get("g") or 0)
        wins = int(ginfo.get("w") or 0)
        wr = (wins / gcount) if gcount else None
        risk = _risk_label(zm, zs, wr, gcount)
        if risk == "🟢 عادی":
            continue
        flags.append((risk, zm + zs, uid, n, mean, p6, zm, zs, gcount, wins, wr))

    flags.sort(key=lambda x: -x[1])
    flags = flags[:18]

    names = {}
    if flags:
        ids = [f[2] for f in flags]
        for m in TelegramGroupMember.objects.filter(telegram_user_id__in=ids).only(
            "telegram_user_id", "alias"
        ):
            if m.alias and m.telegram_user_id not in names:
                names[m.telegram_user_id] = m.alias

    lines = [
        f"🕵️ <b>گزارش چیت / تاس مشکوک</b> — {days} روز",
        "━━━━━━━━━━━━━━━━━━━━",
        "معیار: میانگین تاس (انتظار ۳.۵)، درصد ۶، نرخ برد مسابقه.",
        "حداقل ۳۰ تاس برای آمار چهره. z≥۲.۳ یعنی انحراف معنادار.",
        "",
    ]
    if not flags:
        lines.append("✅ مورد مشکوک با آستانه فعلی پیدا نشد.")
        return "\n".join(lines)

    for i, (risk, _s, uid, n, mean, p6, zm, zs, gcount, wins, wr) in enumerate(flags, 1):
        name = html.escape(str(names.get(uid) or uid))
        wr_s = f"{wins}/{gcount} ({wr:.0%})" if wr is not None and gcount else "—"
        lines.append(
            f"{i}. {risk} {name}  <code>{uid}</code>\n"
            f"   تاس {n} · میانگین {mean:.2f} (z {zm:+.1f}) · شش {p6:.0%} (z {zs:+.1f})\n"
            f"   برد مسابقه: {wr_s}"
        )
    lines.append("\n🔎 برای جزئیات: دکمه «بررسی کاربر» یا بفرست <code>کاربر 123456</code>")
    return "\n".join(lines)


@sync_to_async
def build_progress_report() -> str:
    from account.models import DiceGameHistory, TelegramGroupMember

    since = timezone.now() - timedelta(days=7)
    top_msg = list(
        TelegramGroupMember.objects.order_by("-message_count")
        .values("telegram_user_id", "alias", "message_count", "level", "point")[:12]
    )
    top_bal = list(
        TelegramGroupMember.objects.order_by("-point")
        .values("telegram_user_id", "alias", "point", "telegram_chat_id")[:12]
    )
    top_win = list(
        DiceGameHistory.objects.filter(created_at__gte=since, winner=True)
        .values("telegram_user_id")
        .annotate(w=Count("id"), profit=Sum("amount_won"))
        .order_by("-w")[:12]
    )

    def _nm(row):
        return html.escape(str(row.get("alias") or row["telegram_user_id"]))

    lines = [
        "📈 <b>پیشرفت اعضا</b> (سراسری)",
        "━━━━━━━━━━━━━━━━━━━━\n",
        "<b>فعال‌ترین‌ها (پیام):</b>",
    ]
    for i, r in enumerate(top_msg, 1):
        lines.append(
            f"{i}. {_nm(r)} · {int(r['message_count'] or 0):,} پیام · "
            f"Lv{int(r['level'] or 1)} · موجودی {int(r['point'] or 0):,}"
        )
    lines.append("\n<b>بیشترین موجودی:</b>")
    for i, r in enumerate(top_bal, 1):
        lines.append(
            f"{i}. {_nm(r)} · {int(r['point'] or 0):,} "
            f"(گپ <code>{r['telegram_chat_id']}</code>)"
        )
    lines.append("\n<b>بیشترین برد مسابقه ۷روز:</b>")
    if not top_win:
        lines.append("— هنوز مسابقه‌ای ثبت نشده.")
    else:
        for i, r in enumerate(top_win, 1):
            lines.append(
                f"{i}. <code>{r['telegram_user_id']}</code> · "
                f"{int(r['w'] or 0)} برد · سود {int(r['profit'] or 0):,}"
            )
    return "\n".join(lines)


def build_live_games() -> str:
    lines = ["🎮 <b>بازی‌های زنده</b>", "━━━━━━━━━━━━━━━━━━━━\n"]
    try:
        from bot.dice_game import ACTIVE_GAMES, GAME_PROGRESS
        if not ACTIVE_GAMES:
            lines.append("گروهی: هیچ بازی فعالی نیست.")
        else:
            lines.append(f"گروهی: <b>{len(ACTIVE_GAMES)}</b> بازی")
            for cid, g in list(ACTIVE_GAMES.items())[:12]:
                st = g.get("status") or "?"
                n = len(g.get("players") or [])
                bet = int(g.get("bet_amount") or 0)
                prog = GAME_PROGRESS.get(cid) or {}
                lines.append(
                    f"• گپ <code>{cid}</code> · {st} · {n} نفر · شرط {bet:,}"
                    + (f" · پیشرفت {len(prog)}" if prog else "")
                )
    except Exception as e:
        lines.append(f"گروهی: خطا ({html.escape(str(e)[:80])})")

    try:
        from bot.pv_dice import GAMES, INVITES
        lines.append(f"\nپیوی: <b>{len(GAMES)}</b> بازی")
        for gid, g in list(GAMES.items())[:12]:
            names = g.get("names") or {}
            a, b = (g.get("players") or [0, 0])[:2]
            na = html.escape(str(names.get(a) or a))
            nb = html.escape(str(names.get(b) or b))
            lines.append(
                f"• {na} vs {nb} · {g.get('status')} · ورودی {int(g.get('entry') or 0):,}"
            )
        pend = [i for i in INVITES.values() if i.get("status") == "pending"]
        lines.append(f"\nدعوت باز: <b>{len(pend)}</b>")
    except Exception as e:
        lines.append(f"پیوی: خطا ({html.escape(str(e)[:80])})")

    try:
        from bot.pv_search import SEARCH_OFFERS
        pend = [o for o in SEARCH_OFFERS.values() if o.get("status") == "pending"]
        lines.append(f"جستجوی حریف: <b>{len(pend)}</b>")
    except Exception:
        pass
    return "\n".join(lines)


@sync_to_async
def build_groups_page(page: int = 0) -> tuple[str, int]:
    from account.models import TelegramGroup, TelegramGroupMember

    page = max(0, int(page))
    per = 10
    qs = TelegramGroup.objects.order_by("name", "telegram_chat_id")
    total = qs.count()
    pages = max(1, math.ceil(total / per))
    page = min(page, pages - 1)
    rows = list(qs[page * per : (page + 1) * per])
    lines = [
        f"👥 <b>گروه‌ها</b> — صفحه {page + 1}/{pages} ({total})",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if not rows:
        lines.append("گروهی ثبت نشده.")
        return "\n".join(lines), page
    ids = [g.telegram_chat_id for g in rows]
    counts = dict(
        TelegramGroupMember.objects.filter(telegram_chat_id__in=ids)
        .values("telegram_chat_id")
        .annotate(n=Count("id"))
        .values_list("telegram_chat_id", "n")
    )
    bals = dict(
        TelegramGroupMember.objects.filter(telegram_chat_id__in=ids)
        .values("telegram_chat_id")
        .annotate(s=Sum("point"))
        .values_list("telegram_chat_id", "s")
    )
    from bot import cache as bot_cache
    for g in rows:
        cid = g.telegram_chat_id
        name = html.escape((g.name or "").strip() or str(cid))
        mark = " ⏸" if cid in bot_cache.OFF_GROUP else ""
        lines.append(
            f"• {name}{mark}\n"
            f"  <code>{cid}</code> · {int(counts.get(cid) or 0)} عضو · "
            f"موجودی {int(bals.get(cid) or 0):,}"
        )
    return "\n".join(lines), page


@sync_to_async
def build_rich_list() -> str:
    from account.models import TelegramGroupMember
    rows = list(
        TelegramGroupMember.objects.order_by("-point")
        .values("telegram_user_id", "alias", "point", "telegram_chat_id")[:20]
    )
    lines = ["💰 <b>ثروتمندترین‌ها</b>", "━━━━━━━━━━━━━━━━━━━━"]
    if not rows:
        lines.append("خالی است.")
        return "\n".join(lines)
    for i, r in enumerate(rows, 1):
        name = html.escape(str(r.get("alias") or r["telegram_user_id"]))
        lines.append(
            f"{i}. {name} · {int(r['point'] or 0):,} "
            f"(<code>{r['telegram_user_id']}</code> / گپ <code>{r['telegram_chat_id']}</code>)"
        )
    return "\n".join(lines)


@sync_to_async
def build_open_finance() -> str:
    from account.models import BalanceIncreaseRequest, WithdrawalRequest

    wds = list(
        WithdrawalRequest.objects.filter(status__in=("pending", "receipt"))
        .order_by("-created_at")[:15]
    )
    incs = list(
        BalanceIncreaseRequest.objects.filter(status__in=("waiting_receipt", "pending"))
        .order_by("-created_at")[:15]
    )
    lines = ["📥 <b>درخواست‌های مالی باز</b>", "━━━━━━━━━━━━━━━━━━━━\n", "<b>تسویه:</b>"]
    if not wds:
        lines.append("— موردی نیست.")
    for w in wds:
        lines.append(
            f"• <code>{w.telegram_user_id}</code> · {int(w.amount):,} · {w.status} · گپ <code>{w.telegram_chat_id}</code>"
        )
    lines.append("\n<b>افزایش موجودی:</b>")
    if not incs:
        lines.append("— موردی نیست.")
    for r in incs:
        lines.append(
            f"• <code>{r.telegram_user_id}</code> · {int(r.amount):,} · {r.status} · گپ <code>{r.telegram_chat_id}</code>"
        )
    return "\n".join(lines)


@sync_to_async
def build_user_watch(user_id: int) -> str:
    from account.models import (
        DiceGameHistory,
        DiceRollStat,
        TelegramGroupMember,
        WalletTransaction,
    )

    uid = int(user_id)
    since = timezone.now() - timedelta(days=30)
    members = list(
        TelegramGroupMember.objects.filter(telegram_user_id=uid)
        .values("telegram_chat_id", "alias", "point", "message_count", "level", "warnings", "role")
    )
    face_rows = (
        DiceRollStat.objects.filter(telegram_user_id=uid, rolled_at__gte=since)
        .values("value")
        .annotate(n=Count("id"))
    )
    faces = {int(r["value"]): int(r["n"]) for r in face_rows}
    n = sum(faces.values())
    mean = (sum(v * c for v, c in faces.items()) / n) if n else 0
    p6 = (faces.get(6, 0) / n) if n else 0
    zm = _z(mean, n) if n else 0
    zs = _z_six(p6, n) if n else 0

    from django.db.models import Q
    gqs = DiceGameHistory.objects.filter(telegram_user_id=uid, created_at__gte=since)
    gcount = gqs.count()
    wins = gqs.filter(winner=True).count()
    profit = gqs.aggregate(s=Sum("amount_won"))["s"] or 0
    wr = (wins / gcount) if gcount else None
    risk = _risk_label(zm, zs, wr, gcount) if n >= 20 else "⚪ داده کم"

    dist = " ".join(f"{i}={faces.get(i, 0)}" for i in range(1, 7)) if n else "—"
    name = html.escape(str((members[0]["alias"] if members else None) or uid))
    lines = [
        f"🔎 <b>پرونده کاربر</b> {name}",
        f"<code>{uid}</code> · ریسک ۳۰روز: {risk}",
        "━━━━━━━━━━━━━━━━━━━━\n",
        f"🎲 تاس: {n} · میانگین {mean:.2f} (z {zm:+.1f})",
        f"شش: {p6:.0%} (z {zs:+.1f}) · توزیع: {dist}",
        f"🏆 مسابقه: {wins}/{gcount} برد · سود {int(profit):,}",
        "",
        "<b>عضویت / موجودی:</b>",
    ]
    if not members:
        lines.append("— عضوی در دیتابیس نیست.")
    for m in members[:12]:
        lines.append(
            f"• گپ <code>{m['telegram_chat_id']}</code> · {m.get('role') or 'member'} · "
            f"Lv{int(m['level'] or 1)} · {int(m['message_count'] or 0)} پیام · "
            f"{int(m['point'] or 0):,} · اخطار {int(m['warnings'] or 0)}"
        )
    txs = list(
        WalletTransaction.objects.filter(telegram_user_id=uid).order_by("-created_at")[:8]
    )
    lines.append("\n<b>آخرین تراکنش‌ها:</b>")
    if not txs:
        lines.append("—")
    for t in txs:
        lines.append(
            f"• {t.type} {int(t.amount):,} · بعد {int(t.balance_after):,} · گپ <code>{t.telegram_chat_id}</code>"
        )
    return "\n".join(lines)


@sync_to_async
def build_moderation_report() -> str:
    from account.models import FinanceRequestBan, TelegramGroupMember
    from bot import cache as bot_cache

    warned = list(
        TelegramGroupMember.objects.filter(warnings__gt=0)
        .order_by("-warnings")
        .values("telegram_user_id", "alias", "warnings", "telegram_chat_id", "role")[:18]
    )
    bans = list(FinanceRequestBan.objects.order_by("-created_at")[:12])
    lines = ["⚠️ <b>اخطار / میوت / بن مالی</b>", "━━━━━━━━━━━━━━━━━━━━\n", "<b>اخطار:</b>"]
    if not warned:
        lines.append("— بدون اخطار.")
    for r in warned:
        name = html.escape(str(r.get("alias") or r["telegram_user_id"]))
        lines.append(
            f"• {name} <code>{r['telegram_user_id']}</code> · "
            f"{int(r['warnings'] or 0)} اخطار · گپ <code>{r['telegram_chat_id']}</code>"
        )
    lines.append("\n<b>میوت فعال:</b>")
    muted_n = 0
    for cid, users in list((bot_cache.MUTED_USERS or {}).items())[:20]:
        ids = list(users or [])
        if not ids:
            continue
        muted_n += len(ids)
        shown = ", ".join(f"<code>{u}</code>" for u in ids[:8])
        extra = f" +{len(ids) - 8}" if len(ids) > 8 else ""
        lines.append(f"• گپ <code>{cid}</code> · {len(ids)} نفر: {shown}{extra}")
    if muted_n == 0:
        lines.append("— کسی میوت نیست.")
    lines.append("\n<b>بن مالی:</b>")
    if not bans:
        lines.append("— موردی نیست.")
    for b in bans:
        lines.append(
            f"• <code>{b.telegram_user_id}</code> · گپ <code>{b.telegram_chat_id}</code>"
            + (f" · {html.escape((b.reason or '')[:40])}" if b.reason else "")
        )
    return "\n".join(lines)


@sync_to_async
def build_activity_report() -> str:
    from account.models import DiceRollStat, TelegramGroup

    since = timezone.now() - timedelta(hours=24)
    rows = list(
        DiceRollStat.objects.filter(rolled_at__gte=since)
        .values("telegram_chat_id")
        .annotate(n=Count("id"))
        .order_by("-n")[:18]
    )
    names = {}
    if rows:
        ids = [r["telegram_chat_id"] for r in rows]
        for g in TelegramGroup.objects.filter(telegram_chat_id__in=ids).only("telegram_chat_id", "name"):
            names[g.telegram_chat_id] = g.name
    total = sum(int(r["n"] or 0) for r in rows)
    lines = [
        "🎲 <b>تاس ۲۴ ساعت</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"مجموع در این گروه‌ها: <b>{total:,}</b>\n",
    ]
    if not rows:
        lines.append("در ۲۴ ساعت گذشته تاسی ثبت نشده.")
        return "\n".join(lines)
    for i, r in enumerate(rows, 1):
        cid = r["telegram_chat_id"]
        name = html.escape(str(names.get(cid) or cid))
        lines.append(f"{i}. {name} · {int(r['n'] or 0):,}  <code>{cid}</code>")
    return "\n".join(lines)


def groups_nav_kb(page: int, Btn, Markup):
    prev_p = max(0, page - 1)
    next_p = page + 1
    return Markup(inline_keyboard=[
        [
            Btn(text="◀️", callback_data=f"cr:groups:{prev_p}"),
            Btn(text="▶️", callback_data=f"cr:groups:{next_p}"),
        ],
        [Btn(text="🔙 پنل ادمین", callback_data="cr:open")],
    ])
