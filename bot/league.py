"""
لیگ شرط گروهی — بر اساس مجموع مبلغ شرط (هفتگی، نسخه تلگرام).

هفته: شنبه ۰۰:۰۰ تا جمعه ۲۳:۵۹ (Asia/Tehran) — در شنبه نیمه‌شب ریست می‌شود.

تبدیل واحد:
  «میلیون» در آستانه = هزار واحد  →  ۳ میلیون = ۳٬۰۰۰ واحد
  «هزار تومن» در جایزه = واحد     → ۱۰۰ هزار تومن = ۱۰۰ واحد
"""
from __future__ import annotations

import html as _html
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Tehran")

# فقط همین شناسه روبیکا؛ در تلگرام برای روشن/خاموش مچ نمی‌شود مگر بعداً آیدی عددی اضافه شود
LEAGUE_ALLOWED_IDS = frozenset({"u0CARTT00c63658e48028f34fd06b2cb"})

LEAGUE_TIERS: list[dict[str, Any]] = [
    {"level": 1, "name": "لیگ برنزی", "threshold": 3_000, "prize": 100},
    {"level": 2, "name": "لیگ نقره‌ای", "threshold": 13_000, "prize": 250},
    {"level": 3, "name": "لیگ طلایی", "threshold": 33_000, "prize": 500},
    {"level": 4, "name": "لیگ الماسی", "threshold": 83_000, "prize": 1_000},
    {"level": 5, "name": "لیگ افسانه‌ای", "threshold": 183_000, "prize": 2_000},
]

_PENDING_UNLOCKS: list[dict] = []
_PENDING_RANKS: list[dict] = []
_CACHE_KEY = "league_enabled:{}"
_WEEKDAY_FA = {
    0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنجشنبه",
    4: "جمعه", 5: "شنبه", 6: "یکشنبه",
}

_RANK_META = {
    1: {
        "medal": "🥇",
        "title": "رتبه ۱",
        "sticker": "🏆👑✨\n🥇  قهرمان لیگ  🥇\n✨👑🏆",
        "banner": "┏━━━━━━━━━━━━━━┓\n┃  🥇  قهرمان هفته  🥇  ┃\n┗━━━━━━━━━━━━━━┛",
        "line": "تبریک! شما رتبه ۱ شدید",
        "cheer": "تاج لیگ مال شماست — نگهش دار قهرمان 👑🔥",
    },
    2: {
        "medal": "🥈",
        "title": "رتبه ۲",
        "sticker": "💎⚡✨\n🥈  سکوی دوم  🥈\n✨⚡💎",
        "banner": "┏━━━━━━━━━━━━━━┓\n┃  🥈  سکوی نقره  🥈  ┃\n┗━━━━━━━━━━━━━━┛",
        "line": "تبریک! شما رتبه ۲ شدید",
        "cheer": "فقط یک پله تا قهرمانی — فشار را ادامه بده 🔥💪",
    },
    3: {
        "medal": "🥉",
        "title": "رتبه ۳",
        "sticker": "🌟🎯✨\n🥉  سکوی سوم  🥉\n✨🎯🌟",
        "banner": "┏━━━━━━━━━━━━━━┓\n┃  🥉  سکوی برنز  🥉  ┃\n┗━━━━━━━━━━━━━━┛",
        "line": "تبریک! شما رتبه ۳ شدید",
        "cheer": "وارد جمع سه‌نفره برتر شدید — برو برای رتبه ۲ 💪🚀",
    },
}


def _now_tehran() -> datetime:
    return datetime.now(TZ)


def current_season_id(now: datetime | None = None) -> str:
    """شناسه هفته = تاریخ شنبهٔ شروع هفته (YYYY-MM-DD)."""
    now = now or _now_tehran()
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)
    else:
        now = now.astimezone(TZ)
    # Mon=0 ... Sat=5 Sun=6 → فاصله از شنبه
    days_since_sat = (now.weekday() - 5) % 7
    start = (now - timedelta(days=days_since_sat)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return start.strftime("%Y-%m-%d")


def previous_season_id(now: datetime | None = None) -> str:
    cur = current_season_id(now)
    start = datetime.strptime(cur, "%Y-%m-%d").replace(tzinfo=TZ)
    return (start - timedelta(days=7)).strftime("%Y-%m-%d")


def season_window(season_id: str | None = None) -> tuple[datetime, datetime]:
    """(شروع شنبه ۰۰:۰۰، پایان جمعه ۲۳:۵۹:۵۹)."""
    sid = season_id or current_season_id()
    start = datetime.strptime(sid, "%Y-%m-%d").replace(tzinfo=TZ)
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start, end


def format_season_deadline(now: datetime | None = None) -> str:
    """متن پایان هفته + باقی‌مانده برای نمایش در لیگ من."""
    import jdatetime

    now = now or _now_tehran()
    _start, end = season_window(current_season_id(now))
    left = end - now
    if left.total_seconds() < 0:
        left = timedelta(0)
    days = left.days
    hours = left.seconds // 3600
    mins = (left.seconds % 3600) // 60
    if days > 0:
        remain = f"{days} روز و {hours} ساعت"
    elif hours > 0:
        remain = f"{hours} ساعت و {mins} دقیقه"
    else:
        remain = f"{mins} دقیقه"

    j_end = jdatetime.datetime.fromgregorian(datetime=end.replace(tzinfo=None))
    day_name = _WEEKDAY_FA.get(end.weekday(), "")
    return (
        f"⏱ پایان لیگ این هفته: {day_name} {j_end.strftime('%Y/%m/%d')} ساعت ۲۳:۵۹\n"
        f"⏳ باقی‌مانده: {remain}"
    )


def is_league_allowed_user(user_id) -> bool:
    from bot.constants import CREATOR_USER_ID
    try:
        if int(user_id) == int(CREATOR_USER_ID):
            return True
    except (TypeError, ValueError):
        pass
    return str(user_id).strip() in LEAGUE_ALLOWED_IDS


async def can_set_league_theme(chat_id: int, user_id: int) -> bool:
    from bot.constants import CREATOR_USER_ID
    from bot.helpers import has_admin, is_owner

    try:
        if int(user_id) == int(CREATOR_USER_ID):
            return True
    except (TypeError, ValueError):
        pass
    if is_league_allowed_user(user_id):
        return True
    if has_admin(int(chat_id), int(user_id)):
        return True
    if await is_owner(int(chat_id), int(user_id)):
        return True
    return False


def current_tier_for_wager(wager: int) -> dict | None:
    best = None
    w = int(wager or 0)
    for t in LEAGUE_TIERS:
        if w >= int(t["threshold"]):
            best = t
        else:
            break
    return best


def next_tier_after(wager: int) -> dict | None:
    w = int(wager or 0)
    for t in LEAGUE_TIERS:
        if w < int(t["threshold"]):
            return t
    return None


def _progress_bar(pct: int, width: int = 10) -> str:
    pct = max(0, min(100, int(pct)))
    filled = int(round(pct * width / 100))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def format_tiers_help() -> str:
    lines = ["📋 پله‌های لیگ", "━━━━━━━━━━━━━━━━━━━━"]
    prev = 0
    for t in LEAGUE_TIERS:
        th = int(t["threshold"])
        step = th - prev
        lines.append(
            f"🏅 {t['name']}\n"
            f"   آستانه: <code>{th:,}</code> واحد (+{step:,})\n"
            f"   جایزه: <code>{int(t['prize']):,}</code> واحد"
        )
        prev = th
    lines.append("\nبا هر شرط، حجم لیگ شما بالا می‌رود.")
    lines.append("لیگ هر هفته (شنبه تا جمعه) ریست می‌شود.")
    return "\n".join(lines)


@sync_to_async
def is_league_enabled(chat_id: int) -> bool:
    from django.core.cache import cache
    from account.models import TelegramGroup

    cid = int(chat_id)
    key = _CACHE_KEY.format(cid)
    cached = cache.get(key)
    if cached is not None:
        return bool(int(cached))
    g = TelegramGroup.objects.filter(telegram_chat_id=cid).only("league_enabled").first()
    on = bool(getattr(g, "league_enabled", False)) if g else False
    cache.set(key, 1 if on else 0, 600)
    return on


@sync_to_async
def set_league_enabled(chat_id: int, enabled: bool) -> bool:
    from django.core.cache import cache
    from account.models import TelegramGroup

    cid = int(chat_id)
    g, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=cid, defaults={"name": str(cid)},
    )
    g.league_enabled = bool(enabled)
    g.save(update_fields=["league_enabled"])
    cache.set(_CACHE_KEY.format(cid), 1 if enabled else 0, 600)
    return bool(enabled)


_THEME_CACHE_KEY = "league_board_theme:{}"


@sync_to_async
def get_league_board_theme(chat_id: int) -> int:
    from django.core.cache import cache
    from account.models import TelegramGroup
    from bot.league_board_themes import clamp_theme

    cid = int(chat_id)
    key = _THEME_CACHE_KEY.format(cid)
    cached = cache.get(key)
    if cached is not None:
        return clamp_theme(cached)
    g = TelegramGroup.objects.filter(telegram_chat_id=cid).only("league_board_theme").first()
    theme = clamp_theme(getattr(g, "league_board_theme", 1) if g else 1)
    cache.set(key, theme, 600)
    return theme


@sync_to_async
def set_league_board_theme(chat_id: int, theme_id: int) -> int:
    from django.core.cache import cache
    from account.models import TelegramGroup
    from bot.league_board_themes import clamp_theme

    cid = int(chat_id)
    theme = clamp_theme(theme_id)
    g, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=cid, defaults={"name": str(cid)},
    )
    g.league_board_theme = theme
    g.save(update_fields=["league_board_theme"])
    cache.set(_THEME_CACHE_KEY.format(cid), theme, 600)
    return theme


def record_league_wager_silent(chat_id, user_id, bet_amount: int) -> None:
    from django.core.cache import cache
    from django.db import transaction
    from account.models import TelegramGroup, TelegramGroupMember, LeagueStanding, WalletTransaction

    amount = int(bet_amount or 0)
    if amount <= 0:
        return
    try:
        cid = int(chat_id)
        uid = int(user_id)
    except (TypeError, ValueError):
        return

    key = _CACHE_KEY.format(cid)
    cached = cache.get(key)
    if cached is not None:
        if not int(cached):
            return
    else:
        g = TelegramGroup.objects.filter(telegram_chat_id=cid).only("league_enabled").first()
        on = bool(getattr(g, "league_enabled", False)) if g else False
        cache.set(key, 1 if on else 0, 600)
        if not on:
            return

    def _owner_id() -> int | None:
        oid = (
            TelegramGroupMember.objects.filter(telegram_chat_id=cid, is_owner=True)
            .values_list("telegram_user_id", flat=True)
            .first()
        )
        try:
            return int(oid) if oid is not None else None
        except (TypeError, ValueError):
            return None

    unlocked: list[dict] = []
    rank_up: dict | None = None
    season = current_season_id()
    try:
        with transaction.atomic():
            standing, _ = LeagueStanding.objects.select_for_update().get_or_create(
                telegram_chat_id=cid, telegram_user_id=uid,
                defaults={"wager_total": 0, "claimed_level": 0, "season_id": season},
            )
            # هفته جدید → ریست پیشرفت قبلی
            if (standing.season_id or "") != season:
                standing.season_id = season
                standing.wager_total = 0
                standing.claimed_level = 0
            old_total = int(standing.wager_total or 0)
            standing.wager_total = old_total + amount
            new_total = int(standing.wager_total)
            claimed = int(standing.claimed_level or 0)
            owner_id = _owner_id()

            def _rank_for(wager: int) -> int:
                w = int(wager or 0)
                if w <= 0:
                    return 10**9
                return (
                    LeagueStanding.objects.filter(
                        telegram_chat_id=cid, season_id=season, wager_total__gt=w,
                    ).count()
                    + 1
                )

            old_rank = _rank_for(old_total) if old_total > 0 else 10**9
            new_rank = _rank_for(new_total)

            for t in LEAGUE_TIERS:
                lvl = int(t["level"])
                if lvl <= claimed:
                    continue
                if new_total < int(t["threshold"]):
                    break
                prize = int(t["prize"])
                tag = f"#idemp:lg:{season}:{lvl}:{uid}"
                if WalletTransaction.objects.filter(
                    telegram_chat_id=cid, telegram_user_id=uid,
                    description__contains=tag,
                ).exists():
                    claimed = lvl
                    continue
                grp, _ = TelegramGroup.objects.get_or_create(
                    telegram_chat_id=cid, defaults={"name": str(cid)},
                )
                m, _ = TelegramGroupMember.objects.select_for_update().get_or_create(
                    telegram_chat_id=cid, telegram_user_id=uid,
                    defaults={"group": grp},
                )
                m.point = int(m.point or 0) + prize
                m.save(update_fields=["point"])
                WalletTransaction.objects.create(
                    telegram_chat_id=cid,
                    telegram_user_id=uid,
                    admin_id=owner_id,
                    type="win",
                    amount=prize,
                    balance_after=m.point,
                    description=f"جایزه {t['name']} (لیگ پله {lvl}) {tag}",
                )
                claimed = lvl
                unlocked.append({
                    "chat_id": cid,
                    "user_id": uid,
                    "level": lvl,
                    "name": t["name"],
                    "prize": prize,
                    "wager_total": new_total,
                    "threshold": int(t["threshold"]),
                })

            standing.claimed_level = claimed
            standing.season_id = season
            standing.save(update_fields=["wager_total", "claimed_level", "season_id", "updated_at"])
            if unlocked:
                nxt = next_tier_after(new_total)
                for info in unlocked:
                    if nxt:
                        info["next_name"] = nxt["name"]
                        info["next_threshold"] = int(nxt["threshold"])
                        info["next_prize"] = int(nxt["prize"])
                        info["remaining"] = max(0, int(nxt["threshold"]) - new_total)
                    else:
                        info["next_name"] = None
                        info["next_threshold"] = None
                        info["next_prize"] = None
                        info["remaining"] = 0

            if new_rank <= 3 and new_rank < old_rank:
                cur = current_tier_for_wager(new_total)
                rank_up = {
                    "chat_id": cid,
                    "user_id": uid,
                    "rank": int(new_rank),
                    "prev_rank": int(old_rank) if old_rank < 10**9 else None,
                    "wager_total": new_total,
                    "tier_name": (cur or {}).get("name") or "—",
                }
    except Exception:
        logger.exception("record_league_wager_silent failed chat=%s user=%s", cid, uid)
        return

    for info in unlocked:
        _PENDING_UNLOCKS.append(dict(info))
    if rank_up:
        _PENDING_RANKS.append(dict(rank_up))


def undo_league_wager_silent(chat_id, user_id, bet_amount: int) -> None:
    """کاهش حجم لیگ وقتی بازی تساوی/برگشت شد — جایزه‌های قبلی دست نخورند."""
    from django.db import transaction
    from account.models import LeagueStanding

    amount = int(bet_amount or 0)
    if amount <= 0:
        return
    try:
        cid = int(chat_id)
        uid = int(user_id)
    except (TypeError, ValueError):
        return
    season = current_season_id()
    try:
        with transaction.atomic():
            standing = (
                LeagueStanding.objects.select_for_update()
                .filter(telegram_chat_id=cid, telegram_user_id=uid)
                .first()
            )
            if not standing:
                return
            if (standing.season_id or "") != season:
                return
            standing.wager_total = max(0, int(standing.wager_total or 0) - amount)
            standing.save(update_fields=["wager_total", "updated_at"])
    except Exception:
        logger.exception("undo_league_wager_silent failed chat=%s user=%s", cid, uid)


def pop_pending_unlocks(chat_id=None) -> list[dict]:
    global _PENDING_UNLOCKS
    if chat_id is None:
        out = list(_PENDING_UNLOCKS)
        _PENDING_UNLOCKS.clear()
        return out
    cid = int(chat_id)
    keep, out = [], []
    for item in _PENDING_UNLOCKS:
        try:
            if int(item.get("chat_id")) == cid:
                out.append(item)
            else:
                keep.append(item)
        except (TypeError, ValueError):
            keep.append(item)
    _PENDING_UNLOCKS = keep
    return out


def pop_pending_ranks(chat_id=None) -> list[dict]:
    global _PENDING_RANKS
    if chat_id is None:
        out = list(_PENDING_RANKS)
        _PENDING_RANKS.clear()
        return out
    cid = int(chat_id)
    keep, out = [], []
    for item in _PENDING_RANKS:
        try:
            if int(item.get("chat_id")) == cid:
                out.append(item)
            else:
                keep.append(item)
        except (TypeError, ValueError):
            keep.append(item)
    _PENDING_RANKS = keep
    return out


def format_league_ascent_message(
    *,
    mention: str,
    unlocks: list[dict],
    for_pv: bool = False,
) -> str:
    if not unlocks:
        return ""
    unlocks = sorted(unlocks, key=lambda x: int(x.get("level") or 0))
    top = unlocks[-1]
    wager = int(top.get("wager_total") or 0)
    total_prize = sum(int(u.get("prize") or 0) for u in unlocks)

    if for_pv:
        head = "🚀✨ صعود کردید! ✨🚀"
        who = "شما"
    else:
        head = "🚀✨ صعود در لیگ! ✨🚀"
        who = mention or "بازیکن"

    lines = [
        "🏅💎🏅💎🏅",
        head,
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 {who}",
        "",
    ]

    if len(unlocks) == 1:
        lines.append(f"🎊 تبریک! صعود به «{top.get('name')}»")
    else:
        names = " ← ".join(u.get("name") or "" for u in unlocks)
        lines.append(f"🎊 تبریک! صعود چندپله‌ای:\n   {names}")

    lines.extend([
        f"🎁 جایزه واریزی: <b>{total_prize:,}</b> واحد",
        f"📊 مجموع شرط: <b>{wager:,}</b> واحد",
        "",
    ])

    nxt_name = top.get("next_name")
    if nxt_name:
        remaining = int(top.get("remaining") or 0)
        next_th = int(top.get("next_threshold") or 0)
        next_prize = int(top.get("next_prize") or 0)
        done = max(0, next_th - remaining)
        pct = int(done * 100 / next_th) if next_th else 0
        lines.extend([
            f"🎯 تا لیگ بعد («{nxt_name}»):",
            f"   {_progress_bar(pct)} {pct}٪",
            f"   باقی: <b>{remaining:,}</b> · جایزه بعدی: {next_prize:,}",
            "",
            "ادامه بده — پله بعدی منتظرته 💪🔥",
        ])
    else:
        lines.extend([
            "👑 به بالاترین پله لیگ رسیدید!",
            "افسانه‌ای مطلق هستید 🔥✨",
        ])

    lines.append("")
    lines.append("✅ جایزه همین الان به موجودی اضافه شد.")
    return "\n".join(lines)


def format_league_rank_message(
    *,
    mention: str,
    info: dict,
    for_pv: bool = False,
) -> str:
    rank = int(info.get("rank") or 0)
    meta = _RANK_META.get(rank) or _RANK_META[3]
    who = "شما" if for_pv else (mention or "بازیکن")
    wager = int(info.get("wager_total") or 0)
    tier = info.get("tier_name") or "—"
    prev = info.get("prev_rank")

    lines = [
        meta["banner"],
        "",
        f"🎉 تبریک {who}!",
        f"{meta['medal']} {meta['line']}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🏷 جایگاه: <b>{meta['title']}</b>",
    ]
    if prev and int(prev) > rank:
        lines.append(f"📈 صعود: رتبه {int(prev)} → <b>{rank}</b>")
    lines.extend([
        f"📊 مجموع شرط: <b>{wager:,}</b> واحد",
        f"🎖 پله لیگ: {tier}",
        "",
        meta["cheer"],
    ])
    return "\n".join(lines)


def _group_unlocks_by_user(items: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for info in items:
        try:
            uid = int(info.get("user_id"))
        except (TypeError, ValueError):
            continue
        grouped.setdefault(uid, []).append(info)
    return grouped


async def flush_league_unlocks(bot, chat_id) -> int:
    from bot.helpers import send_private

    items = pop_pending_unlocks(chat_id)
    ranks = pop_pending_ranks(chat_id)
    if not items and not ranks:
        return 0
    sent = 0
    grouped = _group_unlocks_by_user(items)

    for uid, unlocks in grouped.items():
        try:
            from bot.helpers import user_mention_id
            mention = await user_mention_id(uid, bot, int(chat_id))
        except Exception:
            mention = f"<a href='tg://user?id={uid}'>{uid}</a>"

        group_text = format_league_ascent_message(
            mention=mention, unlocks=unlocks, for_pv=False,
        )
        pv_text = format_league_ascent_message(
            mention=mention, unlocks=unlocks, for_pv=True,
        )
        sticker = "🚀🎊✨\n🏆  صعود لیگ  🏆\n✨🎊🚀"
        try:
            await bot.send_message(int(chat_id), sticker)
            await bot.send_message(int(chat_id), group_text, parse_mode="HTML")
            sent += 1
        except Exception:
            logger.exception("league unlock group announce failed")
        try:
            await send_private(bot, uid, sticker)
            await send_private(bot, uid, pv_text)
        except Exception:
            try:
                await bot.send_message(uid, sticker)
                await bot.send_message(uid, pv_text, parse_mode="HTML")
            except Exception:
                logger.exception("league unlock pv announce failed user=%s", uid)

    best_by_user: dict[int, dict] = {}
    for info in ranks:
        try:
            uid = int(info.get("user_id"))
        except (TypeError, ValueError):
            continue
        prev = best_by_user.get(uid)
        if prev is None or int(info.get("rank") or 99) < int(prev.get("rank") or 99):
            best_by_user[uid] = info

    for uid, info in best_by_user.items():
        try:
            from bot.helpers import user_mention_id
            mention = await user_mention_id(uid, bot, int(chat_id))
        except Exception:
            mention = f"<a href='tg://user?id={uid}'>{uid}</a>"
        rank = int(info.get("rank") or 3)
        meta = _RANK_META.get(rank) or _RANK_META[3]
        sticker = meta["sticker"]
        group_text = format_league_rank_message(mention=mention, info=info, for_pv=False)
        pv_text = format_league_rank_message(mention=mention, info=info, for_pv=True)
        try:
            await bot.send_message(int(chat_id), sticker)
            await bot.send_message(int(chat_id), group_text, parse_mode="HTML")
            sent += 1
        except Exception:
            logger.exception("league rank group announce failed")
        try:
            await send_private(bot, uid, sticker)
            await send_private(bot, uid, pv_text)
        except Exception:
            try:
                await bot.send_message(uid, sticker)
                await bot.send_message(uid, pv_text, parse_mode="HTML")
            except Exception:
                logger.exception("league rank pv announce failed user=%s", uid)
    return sent


@sync_to_async
def get_my_league(chat_id: int, user_id: int) -> dict:
    from account.models import LeagueStanding

    cid, uid = int(chat_id), int(user_id)
    season = current_season_id()
    row = LeagueStanding.objects.filter(
        telegram_chat_id=cid, telegram_user_id=uid,
    ).first()
    if row and (row.season_id or "") not in ("", season):
        # هفته قبل — برای نمایش جاری صفر حساب کن
        wager, claimed = 0, 0
        row = None
    else:
        wager = int(row.wager_total or 0) if row else 0
        claimed = int(row.claimed_level or 0) if row else 0
    cur = current_tier_for_wager(wager)
    nxt = next_tier_after(wager)
    rank = None
    if wager > 0:
        rank = (
            LeagueStanding.objects.filter(
                telegram_chat_id=cid, season_id=season, wager_total__gt=wager,
            ).count() + 1
        )
    elif row and (row.season_id or "") in ("", season):
        rank = (
            LeagueStanding.objects.filter(
                telegram_chat_id=cid, season_id=season, wager_total__gt=0,
            ).count() + 1
        )
    return {
        "wager_total": wager,
        "claimed_level": claimed,
        "current": cur,
        "next": nxt,
        "rank": rank,
        "season_id": season,
        "deadline_text": format_season_deadline(),
    }


@sync_to_async
def count_league_leaders(chat_id: int, *, season_id: str | None = None) -> int:
    from account.models import LeagueStanding

    cid = int(chat_id)
    season = season_id or current_season_id()
    n = LeagueStanding.objects.filter(
        telegram_chat_id=cid, season_id=season, wager_total__gt=0,
    ).count()
    if n == 0 and not season_id:
        n = LeagueStanding.objects.filter(
            telegram_chat_id=cid, season_id="", wager_total__gt=0,
        ).count()
    return int(n or 0)


@sync_to_async
def get_league_leaders(
    chat_id: int,
    limit: int = 10,
    *,
    offset: int = 0,
    season_id: str | None = None,
) -> list[dict]:
    from account.models import LeagueStanding

    cid = int(chat_id)
    season = season_id or current_season_id()
    lim = max(1, int(limit))
    off = max(0, int(offset))
    rows = list(
        LeagueStanding.objects.filter(
            telegram_chat_id=cid, season_id=season, wager_total__gt=0,
        ).order_by("-wager_total", "updated_at")[off : off + lim]
    )
    # سازگاری با رکوردهای بدون season_id در همین هفته
    if not rows and not season_id and off == 0:
        rows = list(
            LeagueStanding.objects.filter(
                telegram_chat_id=cid, season_id="", wager_total__gt=0,
            ).order_by("-wager_total", "updated_at")[off : off + lim]
        )
    out = []
    for i, r in enumerate(rows, 1):
        cur = current_tier_for_wager(int(r.wager_total or 0))
        out.append({
            "rank": off + i,
            "user_id": int(r.telegram_user_id),
            "wager_total": int(r.wager_total or 0),
            "claimed_level": int(r.claimed_level or 0),
            "tier_name": (cur or {}).get("name") or "—",
        })
    return out


BOARD_PAGE_SIZE = 10
_BOARD_MAX_CHARS = 1400

LEAGUE_ME_CMDS = frozenset({"لیگ من", "لیگمن"})
LEAGUE_BOARD_CMDS = frozenset({
    "لیگ", "لیگ برترها", "جدول لیگ", "برترین لیگ",
    "رتبه بندی", "رتبه‌بندی", "رتبه بندی لیگ", "رتبه‌بندی لیگ",
    "لیگ رتبه", "لیگ رتبه‌بندی",
})
LEAGUE_HELP_CMDS = frozenset({"لیگ راهنما", "راهنما لیگ"})


def _normalize_league_text(text: str) -> str:
    raw = (text or "").replace("\u200c", " ").replace("\u200b", "").strip()
    return " ".join(raw.split())


def parse_league_board_page(text: str) -> int | None:
    raw = _normalize_league_text(text)
    if not raw:
        return None
    if raw in LEAGUE_ME_CMDS or raw in LEAGUE_HELP_CMDS:
        return None
    if raw in ("لیگ روشن", "لیگ خاموش", "لیگ وضعیت"):
        return None
    if raw.startswith("تم لیگ"):
        return None
    if raw in ("لیگ نمونه", "نمونه لیگ") or raw.startswith("لیگ نمونه ") or raw.startswith("نمونه لیگ "):
        return None

    prefixes = (
        "رتبه‌بندی لیگ", "رتبه بندی لیگ", "لیگ رتبه‌بندی", "لیگ رتبه بندی",
        "رتبه‌بندی", "رتبه بندی", "لیگ رتبه", "لیگ برترها", "جدول لیگ", "برترین لیگ",
    )
    for p in prefixes:
        if raw == p:
            return 1
        if raw.startswith(p + " "):
            rest = raw[len(p):].strip()
            if rest.isdigit():
                return max(1, int(rest))
            return None
    if raw == "لیگ":
        return 1
    if raw.startswith("لیگ "):
        rest = raw[4:].strip()
        if rest.isdigit():
            return max(1, int(rest))
    return None


def format_my_league(data: dict) -> str:
    wager = int(data.get("wager_total") or 0)
    claimed = int(data.get("claimed_level") or 0)
    cur = data.get("current")
    nxt = data.get("next")
    rank = data.get("rank")
    deadline = data.get("deadline_text") or format_season_deadline()

    lines = [
        "🏅 لیگ من",
        "━━━━━━━━━━━━━━━━━━━━",
        deadline,
        "",
        f"📊 مجموع شرط: <b>{wager:,}</b> واحد",
    ]
    if rank:
        lines.append(f"🏷 رتبه: <b>{rank}</b>")
    if cur:
        lines.append(f"✅ پله فعلی: <b>{cur['name']}</b>")
    else:
        lines.append("✅ پله فعلی: هنوز شروع نشده")
    if claimed:
        lines.append(f"🎁 آخرین جایزه: پله {claimed}")

    if nxt:
        th = int(nxt["threshold"])
        pct = min(100, int(wager * 100 / th)) if th else 0
        need = max(0, th - wager)
        lines.append("")
        lines.append(f"🎯 بعدی: <b>{nxt['name']}</b> · جایزه {int(nxt['prize']):,}")
        lines.append(f"{_progress_bar(pct)} <b>{pct}٪</b>")
        lines.append(f"باقی‌مانده: <b>{need:,}</b> / آستانه {th:,}")
    else:
        lines.append("")
        lines.append("👑 به بالاترین پله لیگ رسیده‌اید!")
        lines.append(f"{_progress_bar(100)} <b>100٪</b>")

    return "\n".join(lines)


def _tier_badge(tier_name: str) -> str:
    name = (tier_name or "").strip()
    if "افسانه" in name:
        return "👑"
    if "الماس" in name:
        return "💎"
    if "طلایی" in name:
        return "🌟"
    if "نقره" in name:
        return "🥈"
    if "برنز" in name:
        return "🥉"
    return "🏅"


def _short_display_name(name: str, *, max_len: int = 20) -> str:
    plain = (name or "").strip() or "کاربر"
    if len(plain) > max_len:
        return plain[: max_len - 1] + "…"
    return plain


def _format_board_header(title: str | None, *, html: bool) -> list[str]:
    head = title or "🏆 جدول برترین‌های لیگ"
    sep = "┈" * 18 if html else "─" * 18
    return [head, sep]


def _prize_paid_note(paid: bool | None) -> str:
    if paid is True:
        return " ✅ واریز شد"
    if paid is False:
        return " ⚠️ واریز ناموفق"
    return ""


def _leader_tier_progress(wager: int) -> tuple[int, str]:
    w = int(wager or 0)
    nxt = next_tier_after(w)
    if not nxt:
        return 100, "👑 بالاترین پله لیگ"
    th = int(nxt["threshold"])
    pct = min(100, int(w * 100 / th)) if th else 0
    need = max(0, th - w)
    return pct, f"🎯 تا {nxt['name']}: {need:,} واحد"


def _build_leader_row(
    row: dict,
    display: str,
    *,
    week_prize: int = 0,
    prize_paid: bool | None = None,
) -> "LeaderRow":
    from bot.league_board_themes import LeaderRow

    wager = int(row["wager_total"])
    prize_txt = ""
    if int(row["rank"]) <= 3 and int(week_prize or 0) > 0:
        prize_txt = f"🎁 {int(week_prize):,}"
    pct, note = _leader_tier_progress(wager)
    tier_name = row.get("tier_name") or "—"
    return LeaderRow(
        rank=int(row["rank"]),
        name=_short_display_name(display),
        wager=wager,
        tier=tier_name if tier_name != "—" else "هنوز شروع نشده",
        badge=_tier_badge(row.get("tier_name") or ""),
        prize_label=prize_txt,
        prize_paid_note=_prize_paid_note(prize_paid) if prize_txt else "",
        progress_pct=pct,
        progress_note=note,
    )


def _format_leader_entry(
    row: dict,
    display: str,
    *,
    week_prize: int = 0,
    html: bool = False,
    prize_paid: bool | None = None,
) -> list[str]:
    from bot.stat_prizes import prize_label

    rank = int(row["rank"])
    wager = int(row["wager_total"])
    tier = row.get("tier_name") or "—"
    badge = _tier_badge(tier)
    name = _short_display_name(display)

    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank)
    prize_txt = ""
    if rank <= 3 and int(week_prize or 0) > 0:
        pay_note = ""
        if prize_paid is True:
            pay_note = " ✅ واریز شد"
        elif prize_paid is False:
            pay_note = " ⚠️ واریز ناموفق"
        prize_txt = f"\n   🎁 {prize_label(int(week_prize))}{pay_note}"

    if rank == 1:
        title = "👑 قهرمان هفته"
    elif rank == 2:
        title = "🥈 نفر دوم"
    elif rank == 3:
        title = "🥉 نفر سوم"
    else:
        wager_s = f"{wager:,}" if not html else f"<b>{wager:,}</b>"
        return [f" {rank:2d} │ {name}  ·  {wager_s}  ·  {badge} {tier}"]

    wager_s = f"{wager:,}" if not html else f"<b>{wager:,}</b>"
    lines = [
        f"{medal} {title}",
        f"   👤 {name}",
        f"   📊 {wager_s} واحد",
        f"   {badge} {tier}{prize_txt}",
        "",
    ]
    return lines


async def format_league_board(
    bot,
    chat_id: int,
    leaders: list[dict],
    *,
    title: str | None = None,
    page: int = 1,
    pages: int = 1,
    total: int | None = None,
    compact: bool = True,
    viewer_row: dict | None = None,
) -> str:
    from bot.league_board_themes import BoardContext, render_league_board
    from bot.stat_prizes import get_group_prizes, format_week_prizes_line

    async def _display_name(uid: int) -> str:
        try:
            from bot.helpers import user_mention_id
            import re as _re
            mention = await user_mention_id(uid, bot, int(chat_id))
            m = _re.search(r">([^<]+)<", mention or "")
            return _html.escape((m.group(1) if m else str(uid))[:20])
        except Exception:
            return _html.escape(str(uid))

    theme_id = await get_league_board_theme(chat_id)
    week_prize: dict[int, int] = {}
    try:
        cfg = await get_group_prizes(int(chat_id))
        week_prize = {
            1: int(cfg.get("prize_week_1") or 0),
            2: int(cfg.get("prize_week_2") or 0),
            3: int(cfg.get("prize_week_3") or 0),
        }
    except Exception:
        cfg = {}

    leader_rows = []
    for row in leaders:
        rank = int(row["rank"])
        prize_amt = int(row.get("prize") or week_prize.get(rank, 0) or 0)
        paid = row.get("prize_paid")
        display = await _display_name(int(row["user_id"]))
        leader_rows.append(_build_leader_row(
            row, display,
            week_prize=prize_amt,
            prize_paid=paid if prize_amt > 0 else None,
        ))

    viewer = None
    if viewer_row is not None:
        vuid = int(viewer_row["user_id"])
        in_top = any(int(r["user_id"]) == vuid for r in leaders)
        if not in_top:
            vdisplay = await _display_name(vuid)
            viewer = _build_leader_row(viewer_row, vdisplay)

    ctx = BoardContext(
        title=title or "🏆 جدول برترین‌های لیگ",
        deadline=format_season_deadline(),
        prizes_line="",
        leaders=leader_rows,
        viewer=viewer,
        page=int(page or 1),
        pages=int(pages or 1),
        total=int(total if total is not None else len(leaders)),
    )
    try:
        wp_line = format_week_prizes_line(cfg, html=True)
        if wp_line:
            ctx.prizes_line = wp_line
    except Exception:
        pass
    if not leader_rows:
        head = [ctx.title, "┈" * 18, ctx.deadline]
        if ctx.prizes_line:
            head.extend(["", ctx.prizes_line])
        head.extend(["", ctx.empty_text[0], ctx.empty_text[1]])
        return "\n".join(head)
    from bot.league_board_themes import BOARD_MAX_CHARS
    return render_league_board(theme_id, ctx, max_chars=BOARD_MAX_CHARS)


async def build_league_sample_board(chat_id: int, *, theme_id: int | None = None) -> str:
    from bot.league_board_themes import (
        BoardContext, LEAGUE_THEME_NAMES, make_sample_leaders,
        render_league_board, BOARD_MAX_CHARS,
    )
    from bot.stat_prizes import get_group_prizes, format_week_prizes_line

    leaders = make_sample_leaders(count=10)
    name_map = {
        "sample_1": "علی رضایی", "sample_2": "محمد کریمی", "sample_3": "سارا احمدی",
        "sample_4": "رضا موسوی", "sample_5": "امیر حسینی", "sample_6": "نازنین جعفری",
        "sample_7": "پویا نوری", "sample_8": "مهدی صادقی", "sample_9": "فاطمه رحمانی",
        "sample_10": "کامران باقری",
    }
    tid = int(theme_id) if theme_id else await get_league_board_theme(chat_id)
    if tid == 0:
        tid = await get_league_board_theme(chat_id)
    tid = max(1, min(10, tid))
    tname = LEAGUE_THEME_NAMES.get(tid, str(tid))
    week_prize: dict[int, int] = {}
    cfg = {}
    try:
        cfg = await get_group_prizes(int(chat_id))
        week_prize = {
            1: int(cfg.get("prize_week_1") or 0),
            2: int(cfg.get("prize_week_2") or 0),
            3: int(cfg.get("prize_week_3") or 0),
        }
    except Exception:
        pass
    leader_rows = []
    for row in leaders:
        rank = int(row["rank"])
        prize_amt = week_prize.get(rank, 0)
        leader_rows.append(_build_leader_row(
            row, name_map.get(str(row["user_id"]), str(row["user_id"])),
            week_prize=prize_amt,
        ))
    ctx = BoardContext(
        title=f"🧪 پیش‌نمایش لیگ · تم {tid} ({tname})",
        deadline=format_season_deadline(),
        prizes_line="",
        leaders=leader_rows,
        total=10,
    )
    wp_line = format_week_prizes_line(cfg, html=True)
    if wp_line:
        ctx.prizes_line = wp_line
    return render_league_board(tid, ctx, max_chars=BOARD_MAX_CHARS)


def league_board_kb(group_id: int, page: int, pages: int):
    from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup

    pages = max(1, int(pages or 1))
    page = max(1, min(int(page or 1), pages))
    if pages <= 1:
        return None
    gid = int(group_id)
    nav = []
    if page > 1:
        nav.append(IKB(text="◀️ قبلی", callback_data=f"lgb:{gid}:{page - 1}"))
    nav.append(IKB(text=f"📄 {page}/{pages}", callback_data=f"lgb:{gid}:{page}"))
    if page < pages:
        nav.append(IKB(text="بعدی ▶️", callback_data=f"lgb:{gid}:{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[nav])


async def build_league_board_page(
    bot, group_id: int, page: int = 1, *, header: str = "", viewer_id=None,
):
    total = await count_league_leaders(group_id)
    pages = max(1, (total + BOARD_PAGE_SIZE - 1) // BOARD_PAGE_SIZE) if total else 1
    page = max(1, min(int(page or 1), pages))
    leaders = await get_league_leaders(
        group_id, BOARD_PAGE_SIZE, offset=(page - 1) * BOARD_PAGE_SIZE,
    )

    viewer_row = None
    if viewer_id is not None:
        me = await get_my_league(group_id, int(viewer_id))
        if me.get("rank") and int(me.get("wager_total") or 0) > 0:
            viewer_row = {
                "user_id": int(viewer_id),
                "rank": int(me["rank"]),
                "wager_total": int(me["wager_total"]),
                "tier_name": (me.get("current") or {}).get("name") or "—",
            }

    title = "🏆 جدول برترین‌های لیگ" if page == 1 else f"🏆 جدول لیگ — صفحه {page}"
    text = await format_league_board(
        bot, group_id, leaders,
        title=title, page=page, pages=pages, total=total,
        compact=True, viewer_row=viewer_row if page == 1 else None,
    )
    if header:
        text = header + text
    kb = league_board_kb(group_id, page, pages) if pages > 1 else None
    return text, kb


async def format_week_end_board(bot, chat_id: int, leaders: list[dict]) -> str:
    from bot.league_board_themes import BoardContext, render_league_board
    from bot.stat_prizes import get_group_prizes, format_week_prizes_line

    async def _display_name(uid: int) -> str:
        try:
            from bot.helpers import user_mention_id
            import re as _re
            mention = await user_mention_id(uid, bot, int(chat_id))
            m = _re.search(r">([^<]+)<", mention or "")
            return _html.escape((m.group(1) if m else str(uid))[:20])
        except Exception:
            return _html.escape(str(uid))

    theme_id = await get_league_board_theme(chat_id)
    cfg = {}
    try:
        cfg = await get_group_prizes(int(chat_id))
    except Exception:
        pass
    week_prize = {
        1: int(cfg.get("prize_week_1") or 0),
        2: int(cfg.get("prize_week_2") or 0),
        3: int(cfg.get("prize_week_3") or 0),
    }

    leader_rows = []
    top_mention = None
    for row in leaders[:10]:
        rank = int(row["rank"])
        prize_amt = int(row.get("prize") or week_prize.get(rank, 0) or 0)
        paid = row.get("prize_paid")
        display = await _display_name(int(row["user_id"]))
        if rank == 1:
            top_mention = display
        leader_rows.append(_build_leader_row(
            row, display,
            week_prize=prize_amt,
            prize_paid=paid if prize_amt > 0 else None,
        ))

    footer = "هفته جدید مبارک — با شرط زدن دوباره صعود کن 💪"
    if top_mention:
        footer = f"👑 قهرمان هفته: {top_mention}\n\n" + footer
    top = leaders[0] if leaders else None
    if top and int(top.get("prize") or 0) > 0 and top.get("prize_paid"):
        footer = f"🎁 جایزه قهرمان: <b>{int(top['prize']):,}</b> واحد واریز شد.\n\n" + footer

    ctx = BoardContext(
        title="🏁 پایان لیگ هفتگی",
        deadline=format_season_deadline(),
        prizes_line="",
        leaders=leader_rows,
        total=len(leader_rows),
        footer_note=footer,
        empty_text=(
            "📭 این هفته کسی در لیگ شرکت نکرد.",
            "از الان هفتهٔ جدید شروع شده (همه از صفر).",
        ),
    )
    try:
        wp_line = format_week_prizes_line(cfg, html=True)
        if wp_line:
            ctx.prizes_line = wp_line
    except Exception:
        pass
    if not leader_rows:
        return "\n".join([
            ctx.title, "┈" * 18, ctx.empty_text[0], ctx.empty_text[1],
        ])
    from bot.league_board_themes import BOARD_MAX_CHARS
    return render_league_board(theme_id, ctx, max_chars=BOARD_MAX_CHARS)


@sync_to_async
def list_league_enabled_chat_ids() -> list[int]:
    from account.models import TelegramGroup
    return list(
        TelegramGroup.objects.filter(league_enabled=True)
        .values_list("telegram_chat_id", flat=True)
    )


@sync_to_async
def snapshot_and_reset_season(chat_id: int, season_id: str) -> list[dict]:
    """رتبه‌های فصل تمام‌شده را برمی‌گرداند و رکوردهای آن فصل را پاک می‌کند."""
    from account.models import LeagueStanding

    cid = int(chat_id)
    qs = LeagueStanding.objects.filter(
        telegram_chat_id=cid, season_id=season_id, wager_total__gt=0,
    )
    rows = list(qs.order_by("-wager_total", "updated_at")[:15])
    out = []
    for i, r in enumerate(rows, 1):
        cur = current_tier_for_wager(int(r.wager_total or 0))
        out.append({
            "rank": i,
            "user_id": int(r.telegram_user_id),
            "wager_total": int(r.wager_total or 0),
            "claimed_level": int(r.claimed_level or 0),
            "tier_name": (cur or {}).get("name") or "—",
        })
    LeagueStanding.objects.filter(telegram_chat_id=cid, season_id=season_id).delete()
    return out


async def weekly_league_reset_job(bot) -> None:
    """شنبه ۰۰:۰۰ — اعلام رتبه هفته قبل و ریست."""
    from django.core.cache import cache
    from bot.stat_prizes import pay_and_annotate_week_leaders

    prev = previous_season_id()
    lock_key = f"tg_league_week_reset_done:{prev}"
    if not cache.add(lock_key, "1", timeout=60 * 60 * 48):
        return

    chats = await list_league_enabled_chat_ids()
    for cid in chats:
        try:
            leaders = await snapshot_and_reset_season(cid, prev)
            leaders = await pay_and_annotate_week_leaders(cid, leaders, season_id=prev)
            text = await format_week_end_board(bot, cid, leaders)
            await bot.send_message(int(cid), text, parse_mode="HTML")
        except Exception:
            logger.exception("weekly league reset failed chat=%s", cid)


def parse_league_sample_command(text: str) -> int | None:
    import re

    raw = _normalize_league_text(text)
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    norm = raw.translate(trans)
    if norm in ("لیگ نمونه", "نمونه لیگ"):
        return 0
    m = re.match(r"^(?:لیگ\s*نمونه|نمونه\s*لیگ)\s*(\d{1,2})$", norm)
    if not m:
        return None
    n = int(m.group(1))
    if 0 <= n <= 10:
        return n
    return None


def parse_league_theme_command(text: str) -> int | str | None:
    """تم لیگ 1..10 | تم لیگ وضعیت"""
    import re

    raw = _normalize_league_text(text)
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    norm = raw.translate(trans)
    if norm == "تم لیگ وضعیت":
        return "status"
    m = re.match(r"^تم\s*لیگ\s*(\d{1,2})$", norm)
    if not m:
        return None
    n = int(m.group(1))
    if 1 <= n <= 10:
        return n
    return None


async def handle_league_theme_command(message, bot) -> bool:
    from bot.league_board_themes import LEAGUE_THEME_NAMES, format_theme_catalog

    text = message.text or ""
    raw = _normalize_league_text(text)
    if not raw.startswith("تم لیگ"):
        return False

    parsed = parse_league_theme_command(raw)
    if parsed is None:
        await message.answer(
            "❌ فرمت نامعتبر.\n\n"
            "• <code>تم لیگ 1</code> تا <code>تم لیگ 10</code>\n"
            "• <code>تم لیگ وضعیت</code>",
            parse_mode="HTML",
        )
        return True

    if not await can_set_league_theme(message.chat.id, message.from_user.id):
        await message.answer(
            "⛔️ فقط مالک سیستم، سازنده، مالک یا ادمین گروه می‌تواند تم لیگ را عوض کند.",
            parse_mode="HTML",
        )
        return True

    chat_id = message.chat.id

    if parsed == "status":
        cur = await get_league_board_theme(chat_id)
        await message.answer(
            "🎨 تم جدول لیگ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"فعلی: تم {cur} — {LEAGUE_THEME_NAMES[cur]}\n\n"
            + format_theme_catalog(),
            parse_mode="HTML",
        )
        return True

    theme = int(parsed)
    try:
        await set_league_board_theme(chat_id, theme)
    except Exception:
        logger.exception("set_league_board_theme failed chat=%s theme=%s", chat_id, theme)
        await message.answer(
            "❌ خطا در ذخیره تم.\n"
            "اگر تازه آپدیت کردید: <code>python manage.py migrate account</code>",
            parse_mode="HTML",
        )
        return True
    await message.answer(
        f"✅ تم جدول لیگ روی {theme} ({LEAGUE_THEME_NAMES[theme]}) تنظیم شد.\n\n"
        "برای دیدن نتیجه: <code>لیگ</code> یا <code>رتبه‌بندی</code>",
        parse_mode="HTML",
    )
    return True


async def handle_league_sample_command(message, bot) -> bool:
    parsed = parse_league_sample_command(message.text or "")
    if parsed is None:
        return False
    if not await can_set_league_theme(message.chat.id, message.from_user.id):
        await message.answer(
            "⛔️ فقط مالک سیستم، سازنده، مالک یا ادمین گروه می‌تواند پیش‌نمایش لیگ ببیند.",
            parse_mode="HTML",
        )
        return True
    tid = parsed if parsed else await get_league_board_theme(message.chat.id)
    text = await build_league_sample_board(message.chat.id, theme_id=tid)
    await message.answer(text, parse_mode="HTML")
    return True


@sync_to_async
def list_user_league_groups(user_id: int) -> list[tuple[int, str]]:
    """گروه‌هایی که کاربر عضو/حساب دارد و لیگ روشن است."""
    from account.models import TelegramGroup, TelegramGroupMember, LeagueStanding, WalletTransaction

    uid = int(user_id)
    chat_ids: set[int] = set()
    chat_ids.update(
        int(x)
        for x in TelegramGroupMember.objects.filter(telegram_user_id=uid)
        .exclude(role="banned")
        .values_list("telegram_chat_id", flat=True)[:80]
    )
    chat_ids.update(
        int(x)
        for x in WalletTransaction.objects.filter(telegram_user_id=uid)
        .values_list("telegram_chat_id", flat=True)
        .distinct()[:80]
    )
    chat_ids.update(
        int(x)
        for x in LeagueStanding.objects.filter(telegram_user_id=uid)
        .values_list("telegram_chat_id", flat=True)[:40]
    )
    if not chat_ids:
        return []
    rows = list(
        TelegramGroup.objects.filter(telegram_chat_id__in=chat_ids, league_enabled=True)
        .values_list("telegram_chat_id", "name")[:20]
    )
    return [(int(cid), (name or str(cid)).strip() or str(cid)) for cid, name in rows]


async def _deliver_league_pv(
    bot, user_id: int, group_id: int, action: str, *, group_name: str = "", message=None, page: int = 1,
) -> None:
    from bot.helpers import send_private

    header = f"📍 گروه: {group_name}\n\n" if group_name else ""
    kb = None
    if action == "me":
        data = await get_my_league(group_id, user_id)
        text = header + format_my_league(data)
    else:
        text, kb = await build_league_board_page(
            bot, group_id, page, header=header, viewer_id=user_id,
        )
    if message is not None:
        try:
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass
    await send_private(bot, user_id, text, reply_markup=kb)


def _league_groups_kb(groups: list[tuple[int, str]], action: str):
    from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup

    rows = []
    for gid, gname in groups:
        label = (gname or str(gid))[:40]
        rows.append([IKB(text=f"📍 {label}", callback_data=f"lg:{action}:{gid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def handle_league_pv_command(bot, user_id: int, text: str, *, message=None) -> bool:
    """لیگ من / لیگ / رتبه‌بندی / راهنما در پیوی."""
    from bot.helpers import send_private

    raw = _normalize_league_text(text)
    if raw in LEAGUE_HELP_CMDS:
        body = format_season_deadline() + "\n\n" + format_tiers_help()
        if message is not None:
            await message.answer(body, parse_mode="HTML")
        else:
            await send_private(bot, user_id, body)
        return True

    page = parse_league_board_page(raw)
    if raw in LEAGUE_ME_CMDS:
        action, page = "me", 1
    elif page is not None:
        action = "board"
    else:
        return False

    groups = await list_user_league_groups(user_id)
    if not groups:
        body = (
            "⛔️ گروهی با لیگ روشن پیدا نشد.\n\n"
            "باید عضو گپی باشید که لیگ در آن روشن باشد "
            "و حداقل یک حساب/تراکنش در آن داشته باشید."
        )
        if message is not None:
            await message.answer(body)
        else:
            await send_private(bot, user_id, body)
        return True

    if len(groups) == 1:
        gid, gname = groups[0]
        await _deliver_league_pv(
            bot, user_id, gid, action, group_name=gname, message=message, page=page,
        )
        return True

    title = (
        "🏅 لیگ من — گروه را انتخاب کنید:"
        if action == "me"
        else "🏆 رتبه‌بندی لیگ — گروه را انتخاب کنید:"
    )
    kb_action = "me" if action == "me" else f"board:{page}"
    kb = _league_groups_kb(groups, kb_action)
    if message is not None:
        await message.answer(title, reply_markup=kb)
    else:
        await send_private(bot, user_id, title, reply_markup=kb)
    return True


async def handle_league_board_callback(call, bot) -> bool:
    """lgb:{gid}:{page}"""
    data = (call.data or "").strip()
    if not data.startswith("lgb:"):
        return False
    parts = data.split(":")
    if len(parts) != 3:
        await call.answer()
        return True
    try:
        gid = int(parts[1])
        page = max(1, int(parts[2]))
    except (TypeError, ValueError):
        await call.answer("❌ نامعتبر", show_alert=True)
        return True
    if not await is_league_enabled(gid):
        await call.answer("⛔️ لیگ خاموش است.", show_alert=True)
        return True
    header = ""
    chat_type = getattr(getattr(call, "message", None), "chat", None)
    chat_id = getattr(chat_type, "id", None) if chat_type else None
    if chat_id is not None and int(chat_id) != int(gid):
        for cid, name in await list_user_league_groups(call.from_user.id):
            if int(cid) == gid:
                header = f"📍 گروه: {name}\n\n"
                break
    text, kb = await build_league_board_page(
        bot, gid, page, header=header, viewer_id=call.from_user.id,
    )
    await call.answer()
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            from bot.helpers import send_private
            await send_private(bot, call.from_user.id, text, reply_markup=kb)
    return True


async def handle_league_pv_callback(call, bot) -> bool:
    """callback: lg:me:{gid} | lg:board:{gid} | lg:board:{page}:{gid} | lgb:..."""
    data = (call.data or "").strip()
    if data.startswith("lgb:"):
        return await handle_league_board_callback(call, bot)
    if not data.startswith("lg:"):
        return False
    parts = data.split(":")
    page = 1
    if len(parts) == 3:
        _, action, gid_raw = parts
    elif len(parts) == 4 and parts[1] == "board":
        _, action, page_raw, gid_raw = parts
        try:
            page = max(1, int(page_raw))
        except (TypeError, ValueError):
            page = 1
    else:
        await call.answer()
        return True
    if action not in ("me", "board"):
        await call.answer()
        return True
    try:
        gid = int(gid_raw)
    except (TypeError, ValueError):
        await call.answer("❌ گروه نامعتبر", show_alert=True)
        return True

    uid = call.from_user.id
    groups = await list_user_league_groups(uid)
    gname = ""
    for cid, name in groups:
        if int(cid) == gid:
            gname = name
            break
    else:
        await call.answer("❌ این گروه در دسترس نیست یا لیگ خاموش است.", show_alert=True)
        return True

    if not await is_league_enabled(gid):
        await call.answer("⛔️ لیگ در این گپ خاموش است.", show_alert=True)
        return True

    await call.answer()
    await _deliver_league_pv(
        bot, uid, gid, action, group_name=gname, message=call.message, page=page,
    )
    return True
