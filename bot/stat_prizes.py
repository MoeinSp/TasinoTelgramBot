"""جوایز آمار روزانه و رتبه‌های پایان هفته لیگ — تلگرام."""
from __future__ import annotations

import logging
import re
from typing import Any

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

_PRIZE_SPECS: list[tuple[str, str, str]] = [
    ("بیشترین شرط", "prize_stat_max_bet", "آمار · بیشترین شرط"),
    ("تعداد", "prize_stat_games", "آمار · تعداد/پربازی‌ترین"),
    ("اول", "prize_week_1", "لیگ هفته · رتبه ۱"),
    ("دوم", "prize_week_2", "لیگ هفته · رتبه ۲"),
    ("سوم", "prize_week_3", "لیگ هفته · رتبه ۳"),
]

_FIELD_NAMES = [f for _, f, _ in _PRIZE_SPECS]


def prize_label(amount: int) -> str:
    n = int(amount or 0)
    if n <= 0:
        return ""
    return f" · 🎁 {n:,}"


def format_week_prizes_line(cfg: dict, *, html: bool = True) -> str:
    p1 = int(cfg.get("prize_week_1") or 0)
    p2 = int(cfg.get("prize_week_2") or 0)
    p3 = int(cfg.get("prize_week_3") or 0)
    if p1 <= 0 and p2 <= 0 and p3 <= 0:
        return ""
    parts = []
    if p1 > 0:
        parts.append(f"🥇 {p1:,}")
    if p2 > 0:
        parts.append(f"🥈 {p2:,}")
    if p3 > 0:
        parts.append(f"🥉 {p3:,}")
    body = " · ".join(parts)
    if html:
        return f"🎁 جوایز پایان هفته: <b>{body}</b>"
    return f"🎁 جوایز پایان هفته: {body}"


def format_daily_prizes_line(cfg: dict, *, html: bool = True) -> str:
    g = int(cfg.get("prize_stat_games") or 0)
    b = int(cfg.get("prize_stat_max_bet") or 0)
    if g <= 0 and b <= 0:
        return ""
    parts = []
    if g > 0:
        parts.append(f"🎮 تعداد {g:,}")
    if b > 0:
        parts.append(f"💎 بیشترین شرط {b:,}")
    body = " · ".join(parts)
    if html:
        return f"🎁 جوایز آمار روزانه: <b>{body}</b>"
    return f"🎁 جوایز آمار روزانه: {body}"


def format_prizes_status(cfg: dict) -> str:
    return (
        "🎁 وضعیت جوایز\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 آمار روزانه (ساعت ۱۲):\n"
        f"• تعداد / پربازی‌ترین: <code>{int(cfg.get('prize_stat_games') or 0):,}</code>\n"
        f"• بیشترین شرط: <code>{int(cfg.get('prize_stat_max_bet') or 0):,}</code>\n\n"
        "🏁 لیگ هفتگی (شنبه ۱۲):\n"
        f"• رتبه اول: <code>{int(cfg.get('prize_week_1') or 0):,}</code>\n"
        f"• رتبه دوم: <code>{int(cfg.get('prize_week_2') or 0):,}</code>\n"
        f"• رتبه سوم: <code>{int(cfg.get('prize_week_3') or 0):,}</code>\n\n"
        "۰ = بدون جایزه\n\n"
        "دستورات:\n"
        "• <code>تنظیم جایزه تعداد ۵۰۰</code>\n"
        "• <code>تنظیم جایزه بیشترین شرط ۵۰۰</code>\n"
        "• <code>تنظیم جایزه اول ۵۰۰۰</code>\n"
        "• <code>تنظیم جایزه دوم ۲۰۰۰</code>\n"
        "• <code>تنظیم جایزه سوم ۱۰۰۰</code>\n"
        "• <code>تنظیم جایزه وضعیت</code>"
    )


def compute_daily_prize_winners(records) -> dict[str, Any]:
    games_count: dict = {}
    max_bet: dict = {}
    for rec in records:
        uid = getattr(rec, "telegram_user_id", None)
        if uid is None:
            uid = getattr(rec, "user_id", None)
        if uid is None:
            continue
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            pass
        games_count[uid] = games_count.get(uid, 0) + 1
        bet = int(getattr(rec, "bet_amount", 0) or 0)
        if bet > int(max_bet.get(uid) or 0):
            max_bet[uid] = bet

    def _top(d: dict):
        if not d:
            return None
        uid, val = max(d.items(), key=lambda x: (int(x[1]), str(x[0])))
        if int(val) <= 0:
            return None
        return {"user_id": uid, "value": int(val)}

    return {"games": _top(games_count), "max_bet": _top(max_bet)}


@sync_to_async
def get_group_prizes(chat_id: int) -> dict:
    from account.models import TelegramGroup

    g = TelegramGroup.objects.filter(telegram_chat_id=int(chat_id)).only(*_FIELD_NAMES).first()
    out = {f: 0 for f in _FIELD_NAMES}
    if not g:
        return out
    for f in _FIELD_NAMES:
        out[f] = int(getattr(g, f, 0) or 0)
    return out


@sync_to_async
def set_group_prize(chat_id: int, field: str, amount: int) -> int:
    from account.models import TelegramGroup

    if field not in _FIELD_NAMES:
        raise ValueError(field)
    g, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=int(chat_id), defaults={"name": ""},
    )
    val = max(0, int(amount))
    setattr(g, field, val)
    g.save(update_fields=[field])
    return val


@sync_to_async
def pay_prize_credit(chat_id: int, user_id: int, amount: int, description: str) -> str:
    from django.db import transaction
    from account.models import TelegramGroupMember, WalletTransaction
    from bot.finance import _get_or_create_member, _idemp_exists

    cid = int(chat_id)
    uid = int(user_id)
    amt = int(amount or 0)
    if amt <= 0:
        return "skip"
    desc = (description or "جایزه")[:200]
    try:
        with transaction.atomic():
            if _idemp_exists(cid, uid, desc):
                return "already"
            owner_id = (
                TelegramGroupMember.objects.filter(
                    telegram_chat_id=cid, is_owner=True,
                ).values_list("telegram_user_id", flat=True).first()
            )
            m = _get_or_create_member(cid, uid, for_update=True)
            if _idemp_exists(cid, uid, desc):
                return "already"
            m.point = int(m.point or 0) + amt
            m.save(update_fields=["point"])
            WalletTransaction.objects.create(
                telegram_chat_id=cid,
                telegram_user_id=uid,
                admin_id=int(owner_id) if owner_id else None,
                type="win",
                amount=amt,
                balance_after=m.point,
                description=desc,
            )
        return "paid"
    except Exception:
        logger.exception("pay_prize_credit failed chat=%s user=%s", cid, uid)
        return "skip"


async def pay_and_format_daily_prizes(
    bot, chat_id, records, name_map: dict, *, day_key: str | None = None, pay: bool = True,
) -> str:
    from django.utils import timezone as dj_tz

    cfg = await get_group_prizes(chat_id)
    winners = compute_daily_prize_winners(records)
    lines: list[str] = []
    day_key = day_key or dj_tz.localdate().strftime("%Y-%m-%d")

    async def _pay_one(kind: str, field: str, label: str) -> None:
        amount = int(cfg.get(field) or 0)
        info = winners.get(kind)
        if amount <= 0 or not info:
            return
        uid = info["user_id"]
        name = name_map.get(uid) or name_map.get(int(uid)) or f'<a href="tg://user?id={uid}">کاربر</a>'
        if not pay:
            lines.append(f"🧪 {label}: {name} · {amount:,} واحد (تست — واریز نشد)")
            return
        desc = f"جایزه آمار روزانه · {label} #idemp:daily:{day_key}:{kind}:{uid}"
        status = await pay_prize_credit(int(chat_id), int(uid), amount, desc[:200])
        if status == "paid":
            lines.append(f"✅ {label}: {name} · <b>{amount:,}</b> واحد (مقدار: {info['value']:,})")
        elif status == "already":
            lines.append(f"✅ {label}: {name} · <b>{amount:,}</b> واحد (قبلاً واریز شده)")
        else:
            lines.append(f"⚠️ {label}: پرداخت به {name} ناموفق بود.")

    await _pay_one("games", "prize_stat_games", "پربازی‌ترین")
    await _pay_one("max_bet", "prize_stat_max_bet", "بیشترین شرط")
    if not lines:
        return ""
    return "\n".join(["", "🎁 جوایز آمار روزانه واریز شد:", *lines])


async def pay_and_annotate_week_leaders(
    chat_id: int, leaders: list[dict], *, season_id: str | None = None,
) -> list[dict]:
    from bot.league import previous_season_id

    cfg = await get_group_prizes(chat_id)
    rank_fields = {1: "prize_week_1", 2: "prize_week_2", 3: "prize_week_3"}
    season_id = season_id or previous_season_id()
    out = []
    for row in leaders:
        r = dict(row)
        rank = int(r.get("rank") or 0)
        field = rank_fields.get(rank)
        amount = int(cfg.get(field) or 0) if field else 0
        r["prize"] = amount
        uid = r.get("user_id")
        if amount > 0 and uid is not None:
            desc = f"جایزه لیگ هفتگی · رتبه {rank} #idemp:week:{season_id}:{rank}:{uid}"
            status = await pay_prize_credit(int(chat_id), int(uid), amount, desc[:200])
            r["prize_paid"] = status in ("paid", "already")
        else:
            r["prize_paid"] = False
        out.append(r)
    return out


def parse_prize_setting_command(text: str) -> tuple[str, Any] | None:
    raw = (text or "").strip()
    raw = re.sub(r"\s+", " ", raw)
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    raw = raw.translate(trans)

    if not raw.startswith("تنظیم جایزه"):
        return None
    rest = raw[len("تنظیم جایزه"):].strip()
    if not rest or rest in ("وضعیت", "status", "?"):
        return ("status", None)

    for label, field, title in _PRIZE_SPECS:
        if rest == label or rest.startswith(label + " "):
            tail = rest[len(label):].strip()
            if not tail:
                return ("help", None)
            if not re.fullmatch(r"\d{1,12}", tail):
                return ("help", None)
            return ("set", (field, int(tail), title))
    return ("help", None)
