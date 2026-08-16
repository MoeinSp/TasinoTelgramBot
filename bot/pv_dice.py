"""مسابقه تاس دونفره در پیوی — دعوت، تایمر، اینلاین."""
from __future__ import annotations

import asyncio
import html as _html
import logging
import re
import secrets
import time
import uuid
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup
from asgiref.sync import sync_to_async

from bot.dice_game import (
    BET_MODE_FIXED,
    BET_MODE_EXTRA,
    calc_bet_costs,
    clear_last_dice,
    format_turn_limit_error,
    isolate_match_dice,
    roll_dice,
    _generate_dice_numbers,
    _multinomial_fair,
)
from bot.dice_themes import get_theme, build_single_dice_message, build_multi_dice_message
from bot.helpers import send_private, get_group_theme
from bot.utils import normalize_numbers
from bot import cache as bot_cache
from bot import pv_social as social

logger = logging.getLogger(__name__)

INVITE_TTL = 60            # مهلت قبول/رد — ۱ دقیقه
MOVE_TTL = 180            # مهلت هر حرکت
MOVE_WARN_AT = 60         # اخطار یک دقیقه مانده
MIN_BET = 5


def _sid(user_id) -> int:
    return int(user_id)


def _map_get(d: dict | None, uid, default=0):
    if not d:
        return default
    if uid in d:
        return d[uid]
    try:
        iu = int(uid)
        if iu in d:
            return d[iu]
    except (TypeError, ValueError):
        pass
    su = str(uid)
    if su in d:
        return d[su]
    return default


def _map_set(d: dict, uid, value) -> None:
    """نوشتن با یک کلید نرمال و پاک کردن کلیدهای تکراری str/int."""
    try:
        key = int(uid)
    except (TypeError, ValueError):
        key = uid
    for k in list(d.keys()):
        try:
            if int(k) == int(key):
                d.pop(k, None)
        except (TypeError, ValueError):
            if k == key or str(k) == str(key):
                d.pop(k, None)
    d[key] = value


def _norm_player_maps(game: dict) -> None:
    """یکدست‌سازی کلیدهای totals/remaining/actions بعد از restore از کش."""
    players = list(game.get("players") or [])
    if not players:
        return
    for field in ("totals", "remaining", "dice_rolled"):
        src = game.get(field)
        if not isinstance(src, dict):
            continue
        game[field] = {int(p): int(_map_get(src, p, 0) or 0) for p in players}
    src_al = game.get("actions_left")
    if isinstance(src_al, dict):
        fixed = {}
        for p in players:
            if int(p) in src_al:
                fixed[int(p)] = src_al[int(p)]
            elif str(int(p)) in src_al:
                fixed[int(p)] = src_al[str(int(p))]
            elif p in src_al:
                fixed[int(p)] = src_al[p]
            else:
                fixed[int(p)] = None
        game["actions_left"] = fixed
    src_q = game.get("qual_rolls")
    if isinstance(src_q, dict) and src_q:
        game["qual_rolls"] = {
            int(p): int(v)
            for p, v in (
                (p, _map_get(src_q, p, None)) for p in players
            )
            if v is not None
        }
    if game.get("turn") is not None:
        try:
            game["turn"] = int(game["turn"])
        except (TypeError, ValueError):
            pass
    if game.get("round_setter") is not None:
        try:
            game["round_setter"] = int(game["round_setter"])
        except (TypeError, ValueError):
            pass


def _roll_progress(game: dict, uid) -> tuple[int, int, int]:
    """(rolled, total_rounds, remaining)"""
    rounds = int(game.get("total_rounds") or 0)
    rem = max(0, int(_map_get(game.get("remaining"), uid, 0) or 0))
    if rounds <= 0:
        return 0, 0, rem
    rolled = max(0, rounds - rem)
    return rolled, rounds, rem


def _all_players_rolls_done(game: dict) -> bool:
    for p in game.get("players") or []:
        _rolled, _rounds, rem = _roll_progress(game, p)
        if rem > 0:
            return False
    return True


def _qual_missing_players(game: dict) -> list:
    """بازیکنانی که هنوز تاس تعیین نزده‌اند — با کلید نرمال (جلوی باگ str/int)."""
    _norm_player_maps(game)
    rolls = game.get("qual_rolls") or {}
    missing = []
    for p in game.get("players") or []:
        if _map_get(rolls, p, None) is None:
            missing.append(int(p))
    return missing


def _any_real_game_roll(game: dict) -> bool:
    """آیا بعد از تعیین راند، حداقل یک تاس در بازی اصلی ریخته شده؟"""
    _norm_player_maps(game)
    for p in game.get("players") or []:
        if int(_map_get(game.get("dice_rolled"), p, 0) or 0) > 0:
            return True
    total = int(game.get("total_rounds") or 0)
    if total > 0:
        for p in game.get("players") or []:
            rem = int(_map_get(game.get("remaining"), p, total) or 0)
            if rem < total:
                return True
    return bool(game.get("first_roll_done"))


def _soft_timeout_applies(game: dict, soft: bool) -> bool:
    """در حالت باخت‌خاموش: قبل از اولین تاس واقعی، مهلت → لغو نه باخت."""
    if not soft:
        return False
    st = game.get("status")
    if st in ("qualifying", "awaiting_rounds"):
        return True
    if st == "playing" and not _any_real_game_roll(game):
        return True
    return False


def _other_player(players, uid):
    try:
        su = int(uid)
    except (TypeError, ValueError):
        return None
    for p in players or []:
        try:
            if int(p) != su:
                return p
        except (TypeError, ValueError):
            continue
    return None


def invite_ttl_label() -> str:
    """متن انسانی مهلت دعوت — همیشه با INVITE_TTL هم‌خوان."""
    if INVITE_TTL < 60:
        return f"{INVITE_TTL} ثانیه"
    mins = INVITE_TTL // 60
    secs = INVITE_TTL % 60
    if secs == 0:
        return "۱ دقیقه" if mins == 1 else f"{mins} دقیقه"
    return f"{mins} دقیقه و {secs} ثانیه"


_MODE_WORDS = {
    "فیکس": BET_MODE_FIXED, "fix": BET_MODE_FIXED, "fixed": BET_MODE_FIXED,
    "اضافه": BET_MODE_EXTRA, "شرط": BET_MODE_EXTRA, "extra": BET_MODE_EXTRA,
}

# invite_id → dict
INVITES: dict[str, dict] = {}
# game_id → dict
GAMES: dict[str, dict] = {}
# user_id → ("invite"|"game", id)
USER_BUSY: dict[int, tuple[str, str]] = {}
# user_id → game_id (منتظر عدد تاس دلخواه)
AWAITING_CUSTOM_DICE: dict[int, str] = {}

_sweeper_started = False
_restore_round_prompts_done = False
_PV_STATE_TTL = 60 * 60 * 48
_PV_CACHE_GAMES = "tg_pv_dice:v1:games"
_PV_CACHE_INVITES = "tg_pv_dice:v1:invites"
_PV_CACHE_BUSY = "tg_pv_dice:v1:busy"
_PV_CACHE_CUSTOM = "tg_pv_dice:v1:custom"
_pv_state_loaded = False
_active_watchdogs: set[str] = set()
_active_invite_timers: set[str] = set()
_accept_locks: dict[str, asyncio.Lock] = {}
_recent_invite_by_sig: dict[str, tuple[float, str]] = {}
_invite_sig_locks: dict[str, asyncio.Lock] = {}
_game_roll_locks: dict[str, asyncio.Lock] = {}
_RECENT_INVITE_WINDOW_SEC = 4.0


def _game_roll_lock(game_id: str) -> asyncio.Lock:
    gid = str(game_id or "").strip()
    lock = _game_roll_locks.get(gid)
    if lock is None:
        lock = asyncio.Lock()
        _game_roll_locks[gid] = lock
    return lock


def _clamp_dice_total(dice_count: int, total: int) -> int:
    """مجموع یک پرتاب باید بین N و 6N باشد."""
    n = max(1, int(dice_count or 1))
    t = int(total or 0)
    return max(n, min(6 * n, t))


def _avg_per_die(total: int, dice_count: int) -> float:
    """میانگین هر تاس (مجموع ÷ تعداد تاس واقعی)."""
    total = int(total or 0)
    count = int(dice_count or 0)
    if total <= 0 or count <= 0:
        return 0.0
    return total / count


def _invite_signature(
    *,
    group_id: int,
    challenger_id: int,
    target_id: int,
    bet_amount: int,
    has_bet: bool,
    bet_mode: str,
    fee_percent: int,
    group_msg_id: int | None = None,
) -> str:
    del group_msg_id  # فقط برای API سازگار؛ در امضا نیست (جلوگیری از دوباره‌کاری)
    return "|".join([
        str(int(group_id)),
        str(int(challenger_id)),
        str(int(target_id)),
        str(int(bet_amount)),
        "1" if has_bet else "0",
        str(bet_mode or ""),
        str(int(fee_percent)),
    ])


def _forget_invite_sig(invite_id: str, inv: dict | None = None) -> None:
    sig = (inv or {}).get("_sig") if inv else None
    if not sig:
        for k, (_ts, iid) in list(_recent_invite_by_sig.items()):
            if iid == invite_id:
                _recent_invite_by_sig.pop(k, None)
        return
    prev = _recent_invite_by_sig.get(sig)
    if prev and prev[1] == invite_id:
        _recent_invite_by_sig.pop(sig, None)


_persist_dirty = False
_persist_task = None
_PERSIST_DEBOUNCE_SEC = 0.8
_pv_chat_enabled_cache: dict[str, tuple[float, bool]] = {}
_PV_CHAT_CACHE_TTL = 45.0


def _persist_pv_state_sync() -> None:
    """ذخیره کامل وضعیت پیوی در Redis (دعوت، بازی، قفل کاربر، تاس دلخواه)."""
    try:
        from django.core.cache import cache

        busy_to_save = {
            k: v for k, v in USER_BUSY.items()
            if not (isinstance(v, (tuple, list)) and len(v) >= 1 and v[0] == "search")
        }
        cache.set(_PV_CACHE_GAMES, dict(GAMES), timeout=_PV_STATE_TTL)
        cache.set(_PV_CACHE_INVITES, dict(INVITES), timeout=_PV_STATE_TTL)
        cache.set(_PV_CACHE_BUSY, busy_to_save, timeout=_PV_STATE_TTL)
        cache.set(_PV_CACHE_CUSTOM, dict(AWAITING_CUSTOM_DICE), timeout=_PV_STATE_TTL)
        social.persist_social()
    except Exception:
        logger.exception("pv_dice persist state failed")


def _persist_pv_state() -> None:
    """از مسیر async: debounce تا event loop با Redis sync قفل نشود."""
    global _persist_dirty, _persist_task
    import asyncio

    _persist_dirty = True
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _persist_pv_state_sync()
        _persist_dirty = False
        return

    async def _flush_later():
        global _persist_dirty, _persist_task
        await asyncio.sleep(_PERSIST_DEBOUNCE_SEC)
        while _persist_dirty:
            _persist_dirty = False
            try:
                await asyncio.to_thread(_persist_pv_state_sync)
            except Exception:
                logger.exception("pv_dice persist async failed")
            if _persist_dirty:
                await asyncio.sleep(0.15)
        _persist_task = None

    if _persist_task is None or _persist_task.done():
        _persist_task = loop.create_task(_flush_later())


async def _persist_pv_state_now() -> None:
    """Persist فوری برای accept/finish/cancel."""
    global _persist_dirty, _persist_task
    import asyncio

    _persist_dirty = False
    task = _persist_task
    _persist_task = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    await asyncio.to_thread(_persist_pv_state_sync)


_ADMIN_CHAT_TTL = 60 * 30
_ADMIN_CHAT_SESSIONS: dict[str, dict] = {}


def _day_label(ts: float) -> str:
    try:
        import jdatetime
        return jdatetime.datetime.fromtimestamp(float(ts)).strftime("%Y/%m/%d")
    except Exception:
        return time.strftime("%Y/%m/%d", time.localtime(float(ts)))


def collect_admin_pv_games(group_id, user_id, *, limit: int = 30) -> list[dict]:
    uid = str(user_id).strip()
    gid = str(group_id).strip()
    items: list[dict] = []

    for game in GAMES.values():
        if str(game.get("group_id") or "").strip() != gid:
            continue
        if uid not in [str(p).strip() for p in (game.get("players") or [])]:
            continue
        if game.get("status") in ("finished", "cancelled"):
            continue
        social.ensure_game_social(game)
        names = game.get("names") or {}
        a, b = (game.get("players") or [None, None])[:2]
        log = list(game.get("chat_log") or [])
        ts = float(log[-1]["ts"]) if log else time.time()
        na = social._name_of(game, a) if hasattr(social, "_name_of") else names.get(a, a)
        nb = social._name_of(game, b) if hasattr(social, "_name_of") else names.get(b, b)
        items.append({
            "live": True,
            "game_id": game.get("id"),
            "ts": ts,
            "day": _day_label(ts),
            "title": f"🟢 {na} vs {nb}",
            "subtitle": f"جاری · {game.get('status')}",
            "chat_log": log,
        })

    key = social._archive_key(gid, uid)
    for g in (social.CHAT_ARCHIVE.get(key) or [])[:limit]:
        names = g.get("names") or {}
        a, b = (g.get("players") or [None, None])[:2]
        na = names.get(str(a).strip(), names.get(a, a))
        nb = names.get(str(b).strip(), names.get(b, b))
        ts = float(g.get("ended_at") or 0) or time.time()
        w = g.get("winner_id")
        if g.get("is_tie"):
            sub = "تساوی"
        elif w:
            sub = f"برنده: {names.get(str(w).strip(), names.get(w, w))}"
        else:
            sub = "پایان‌یافته"
        items.append({
            "live": False,
            "ts": ts,
            "day": _day_label(ts),
            "title": f"🎮 {na} vs {nb}",
            "subtitle": sub,
            "chat_log": list(g.get("chat_log") or []),
        })

    items.sort(key=lambda x: float(x.get("ts") or 0), reverse=True)
    return items[:limit]


def format_admin_game_chat(item: dict) -> str:
    if item.get("live") and item.get("game_id"):
        g = GAMES.get(item["game_id"])
        if g:
            social.ensure_game_social(g)
            item = dict(item)
            item["chat_log"] = list(g.get("chat_log") or [])
            item["subtitle"] = f"جاری · {g.get('status')}"
    lines = [
        _html.escape(str(item.get("title") or "🎮 بازی")),
        f"📅 {_html.escape(str(item.get('day') or '—'))}",
        f"ℹ️ {_html.escape(str(item.get('subtitle') or ''))}",
        "────────────────────",
    ]
    log = item.get("chat_log") or []
    if not log:
        lines.append("(بدون پیام چت)")
    else:
        for e in log:
            t = time.strftime("%H:%M", time.localtime(float(e.get("ts") or 0)))
            lines.append(
                f"[{t}] {_html.escape(str(e.get('name') or ''))}: "
                f"{_html.escape(str(e.get('text') or ''))}"
            )
    return "\n".join(lines)


def format_admin_pv_game_list(target_name: str, items: list[dict]) -> str:
    if not items:
        return (
            "📭 بازی پیوی ثبت‌شده‌ای برای این کاربر در این گروه نیست.\n"
            "بعد از بازی‌هایی که داخلشان پیام رد و بدل شده، اینجا دیده می‌شود."
        )
    lines = [
        "📂 گزارش چت پیوی",
        f"👤 کاربر: {_html.escape(str(target_name))}",
        "یک بازی را انتخاب کنید تا چت همان بازی نمایش داده شود.",
        "",
    ]
    current_day = None
    for i, it in enumerate(items, start=1):
        day = it.get("day") or "—"
        if day != current_day:
            current_day = day
            lines.append(f"📅 {_html.escape(str(day))}")
            lines.append("────────")
        n_msg = len(it.get("chat_log") or [])
        lines.append(
            f"{i}. {_html.escape(str(it.get('title')))} — "
            f"{_html.escape(str(it.get('subtitle')))} ({n_msg} پیام)"
        )
    return "\n".join(lines)


def _admin_chat_list_kb(session_id: str, items: list[dict]) -> InlineKeyboardMarkup | None:
    rows = []
    for i, it in enumerate(items):
        label = f"{it.get('day', '')} · {it.get('title', 'بازی')}"
        if len(label) > 40:
            label = label[:37] + "…"
        rows.append([IKB(text=label, callback_data=f"pvc:g:{session_id}:{i}")])
    return _kb(rows) if rows else None


def _admin_chat_back_kb(session_id: str) -> InlineKeyboardMarkup:
    return _kb([[IKB(text="↩️ بازگشت به لیست بازی‌ها", callback_data=f"pvc:l:{session_id}")]])


async def open_admin_pv_chat_browser(
    bot: Bot, *, group_id, admin_id, target_id, group_msg_id, target_name: str | None = None,
) -> bool:
    from bot.helpers import safe_send

    await ensure_sweeper(bot)
    items = collect_admin_pv_games(group_id, target_id)
    name = (target_name or "").strip() or str(target_id)
    text = format_admin_pv_game_list(name, items)
    if not items:
        await safe_send(bot, group_id, text, reply_to=group_msg_id)
        return False

    sid = secrets.token_hex(4)
    _ADMIN_CHAT_SESSIONS[sid] = {
        "admin_id": int(admin_id),
        "group_id": int(group_id),
        "target_id": int(target_id),
        "target_name": name,
        "games": items,
        "expires_at": time.time() + _ADMIN_CHAT_TTL,
    }
    kb = _admin_chat_list_kb(sid, items)
    ok = await send_private(bot, int(admin_id), text, reply_markup=kb)
    if ok:
        await safe_send(
            bot, group_id, "📲 گزارش در پیوی ربات ارسال شد.", reply_to=group_msg_id,
        )
        return True
    await safe_send(
        bot, group_id,
        "⚠️ ابتدا ربات را در پیوی /start کنید تا گزارش ارسال شود.",
        reply_to=group_msg_id,
    )
    return False


async def _handle_admin_chat_button(bot: Bot, uid: int, data: str) -> bool:
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != "pvc":
        return False
    action = parts[1]
    session_id = parts[2]
    sess = _ADMIN_CHAT_SESSIONS.get(session_id)
    if not sess or time.time() > float(sess.get("expires_at") or 0):
        _ADMIN_CHAT_SESSIONS.pop(session_id, None)
        await send_private(bot, uid, "⚠️ این گزارش منقضی شده؛ دوباره از گروه «چت پیوی» را بزنید.")
        return True
    if int(uid) != int(sess.get("admin_id")):
        await send_private(bot, uid, "❌ این گزارش فقط برای ادمین درخواست‌کننده است.")
        return True

    items = sess.get("games") or []
    if action == "l":
        text = format_admin_pv_game_list(sess.get("target_name") or sess.get("target_id"), items)
        await send_private(bot, uid, text, reply_markup=_admin_chat_list_kb(session_id, items))
        return True
    if action == "g" and len(parts) >= 4:
        try:
            idx = int(parts[3])
        except ValueError:
            await send_private(bot, uid, "بازی نامعتبر.")
            return True
        if idx < 0 or idx >= len(items):
            await send_private(bot, uid, "این بازی در لیست نیست.")
            return True
        body = format_admin_game_chat(items[idx])
        max_len = 3500
        chunk = body
        while chunk:
            part, chunk = chunk[:max_len], chunk[max_len:]
            kb = _admin_chat_back_kb(session_id) if not chunk else None
            await send_private(bot, uid, part, reply_markup=kb)
        return True
    return True


def format_admin_pv_chats(group_id, user_id) -> str:
    items = collect_admin_pv_games(group_id, user_id)
    return format_admin_pv_game_list(str(user_id), items)


def _heal_restored_games() -> None:
    """اگر قبل از persist مرحله تعیین گیر کرده بود، وضعیت را درست کن."""
    changed = False
    for game in list(GAMES.values()):
        _norm_player_maps(game)
        if game.get("status") != "qualifying":
            continue
        players = list(game.get("players") or [])
        rolls = game.get("qual_rolls") or {}
        if len(players) < 2:
            continue
        a, b = int(players[0]), int(players[1])
        # کلیدها بعد از redis ممکن است str باشند
        ra = rolls.get(a, rolls.get(str(a)))
        rb = rolls.get(b, rolls.get(str(b)))
        if ra is None or rb is None:
            continue
        if ra == rb:
            game["qual_rolls"] = {}
            game["move_deadline"] = time.time() + MOVE_TTL
            game["warned"] = False
            changed = True
            continue
        setter = a if ra > rb else b
        game["round_setter"] = setter
        game["status"] = "awaiting_rounds"
        game["move_deadline"] = time.time() + MOVE_TTL
        game["warned"] = False
        changed = True
    if changed:
        _persist_pv_state()


def _load_pv_state() -> None:
    global _pv_state_loaded
    if _pv_state_loaded:
        return
    _pv_state_loaded = True
    try:
        from django.core.cache import cache

        games = cache.get(_PV_CACHE_GAMES)
        invites = cache.get(_PV_CACHE_INVITES)
        busy = cache.get(_PV_CACHE_BUSY)
        custom = cache.get(_PV_CACHE_CUSTOM)
        if isinstance(games, dict) and games:
            GAMES.clear()
            GAMES.update(games)
        if isinstance(invites, dict) and invites:
            INVITES.clear()
            INVITES.update(invites)
        if isinstance(busy, dict) and busy:
            cleaned: dict[int, tuple[str, str]] = {}
            for k, v in busy.items():
                try:
                    uid = int(k)
                except (TypeError, ValueError):
                    continue
                if isinstance(v, list):
                    v = tuple(v)
                if not (isinstance(v, tuple) and len(v) >= 2):
                    continue
                # search آفرها persist نمی‌شوند — قفل یتیم را دور بریز
                if v[0] == "search":
                    continue
                cleaned[uid] = (str(v[0]), str(v[1]))
            USER_BUSY.clear()
            USER_BUSY.update(cleaned)
        if isinstance(custom, dict) and custom:
            AWAITING_CUSTOM_DICE.clear()
            AWAITING_CUSTOM_DICE.update({int(k): v for k, v in custom.items()})
        _heal_restored_games()
        _rebuild_busy_from_live_games()
        _heal_orphan_busy_locks()
        if GAMES or INVITES:
            print(f"pv_dice restored from redis games={len(GAMES)} invites={len(INVITES)}")
    except Exception as e:
        print(f"pv_dice load state failed: {e}")


def _ensure_game_watchdog(bot: Bot, game_id: str) -> None:
    gid = str(game_id or "").strip()
    if not gid or gid in _active_watchdogs:
        return
    game = GAMES.get(gid)
    if not game or game.get("status") in ("finished", "cancelled"):
        return
    _active_watchdogs.add(gid)
    asyncio.create_task(_move_watchdog(bot, gid))


def _ensure_invite_timer(bot: Bot, invite_id: str) -> None:
    iid = str(invite_id or "").strip()
    if not iid or iid in _active_invite_timers:
        return
    inv = INVITES.get(iid)
    if not inv or inv.get("status") != "pending":
        return
    _active_invite_timers.add(iid)
    asyncio.create_task(_invite_timeout(bot, iid))


def _resume_timers_after_restore(bot: Bot, *, send_round_prompts: bool = False) -> None:
    global _restore_round_prompts_done
    for gid, game in list(GAMES.items()):
        if game.get("status") not in ("finished", "cancelled"):
            _ensure_game_watchdog(bot, gid)
    for iid, inv in list(INVITES.items()):
        if inv.get("status") == "pending":
            _ensure_invite_timer(bot, iid)
    if send_round_prompts and not _restore_round_prompts_done:
        _restore_round_prompts_done = True
        asyncio.create_task(_notify_restored_awaiting_rounds(bot))


async def _notify_restored_awaiting_rounds(bot: Bot) -> None:
    changed = False
    for gid, game in list(GAMES.items()):
        if game.get("status") != "awaiting_rounds":
            continue
        if game.get("_rounds_prompted") or game.get("_restored_notified"):
            continue
        game["_rounds_prompted"] = True
        game["_restored_notified"] = True
        changed = True
        setter = int(game.get("round_setter") or 0)
        sname = game["names"].get(setter, str(setter))
        for p in game.get("players") or []:
            try:
                if int(p) == setter:
                    await send_private(
                        bot, p,
                        "🏅 نوبت شماست — تعداد راند مسابقه را بنویسید (مثلاً <code>20</code>).",
                        reply_markup=_rounds_prompt_kb(gid),
                    )
                else:
                    await send_private(
                        bot, p,
                        f"🏅 {sname} تعداد راند را انتخاب می‌کند…",
                    )
            except Exception:
                pass
    if changed:
        _persist_pv_state()


def _kb(rows: list[list[IKB]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _invite_money_block(inv: dict) -> str:
    if not inv.get("has_bet"):
        return ""
    block = (
        f"💳 ورودی هر نفر: {int(inv.get('entry') or 0):,} واحد ({inv.get('mode_label') or 'فیکس'})\n"
        f"🏆 جایزه برنده: {int(inv.get('winner_amount') or 0):,} واحد\n"
    )
    if int(inv.get("fee_amount") or 0) > 0:
        block += f"💸 حق واسطه: {int(inv['fee_amount']):,} واحد\n"
    return block


def _clean_person_label(name: str, fallback: str) -> str:
    """نام قابل‌نمایش برای پیام خطا — بدون HTML و بدون برچسب مبهم."""
    import re as _re
    n = _re.sub(r"<[^>]+>", "", name or "").strip()
    n = _html.unescape(n)
    n = " ".join(n.split())
    if not n or n in ("شما", "حریف", "کاربر", "یکی از کاربران", "—", "-"):
        return fallback
    if len(n) > 40:
        n = n[:38] + "…"
    return n


def format_pv_invite_delivery_fail(
    *,
    challenger_ok: bool,
    target_ok: bool,
    challenger_name: str = "",
    target_name: str = "",
    challenger_started: bool | None = None,
    target_started: bool | None = None,
) -> str:
    """متن کوتاه و دقیق: دقیقاً مشخص می‌کند کی پیوی ندارد / بلاک است."""
    ch = _clean_person_label(challenger_name, "چالش‌کننده")
    tg = _clean_person_label(target_name, "حریف")

    def _why(started: bool | None) -> str:
        if started is False:
            return "ربات را در پیوی استارت نکرده"
        if started is True:
            return "پیوی‌اش بسته است یا ربات را بلاک کرده"
        return "پیوی در دسترس نیست (استارت نکرده یا بلاک)"

    problems: list[tuple[str, str]] = []
    if not challenger_ok:
        problems.append((ch, _why(challenger_started)))
    if not target_ok:
        problems.append((tg, _why(target_started)))

    lines = [
        "⚠️ دعوت پیوی ارسال نشد",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if len(problems) == 2:
        lines.append("❌ مشکل از هر دو نفر:")
        for name, why in problems:
            lines.append(f"• {_html.escape(name)} — {why}")
    elif len(problems) == 1:
        name, why = problems[0]
        lines.append(f"❌ مشکل از {_html.escape(name)}")
        lines.append(f"📌 {why}")
    else:
        lines.append("❌ ارسال دعوت به پیوی ممکن نشد.")

    lines.extend([
        "",
        "آموزش:",
        "۱) پیوی همین ربات را باز کنید",
        "۲) /start بزنید (اگر بلاک بود، آنبلاک کنید)",
        "۳) دوباره در گروه دعوت را بفرستید",
    ])
    return "\n".join(lines)


def _cancelled_target_text(inv: dict) -> str:
    return (
        "❌ چالش تاس پیوی — لغو شد\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"از طرف: {_html.escape(str(inv.get('challenger_name') or '—'))}\n"
        f"{_invite_money_block(inv)}"
        "\nدعوت توسط چالش‌کننده لغو شد."
    )


def _cancelled_challenger_text(inv: dict) -> str:
    return (
        "❌ دعوت بازی پیوی لغو شد\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"حریف: {_html.escape(str(inv.get('target_name') or '—'))}\n"
        f"{_invite_money_block(inv)}"
    )


async def _edit_invite_message(bot: Bot, user_id: int, message_id, text: str) -> bool:
    if not message_id:
        return False
    try:
        await bot.edit_message_text(
            text,
            chat_id=int(user_id),
            message_id=int(message_id),
            reply_markup=None,
            parse_mode="HTML",
        )
        return True
    except Exception:
        return False


async def _send_invite_pm(bot: Bot, user_id: int, text: str, reply_markup=None):
    """ارسال دعوت و برگرداندن message_id یا False."""
    try:
        sent = await bot.send_message(
            int(user_id), text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return getattr(sent, "message_id", None) or True
    except Exception as e:
        print(f"send_invite_pm error ({user_id}): {e}")
        return False


def parse_pv_start_command(text: str) -> dict | None:
    """شروع 2 100 پیوی | شروع 2 100 فیکس پیوی | شروع 2 100 اضافه پیوی"""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        from bot.silent_cmd import parse_silent_suffix
        body, _lvl = parse_silent_suffix(raw)
        if body:
            raw = body
    except Exception:
        pass
    parts = raw.split()
    if parts:
        parts[-1] = parts[-1].rstrip(".….۔")
    if len(parts) < 3 or parts[-1] != "پیوی":
        return None
    if parts[0] != "شروع":
        return None
    parts = parts[:-1]  # drop پیوی
    explicit_mode = None
    if parts and parts[-1].lower() in _MODE_WORDS:
        explicit_mode = _MODE_WORDS[parts[-1].lower()]
        parts = parts[:-1]
    if len(parts) < 2:
        return None
    try:
        total_players = int(parts[1])
    except ValueError:
        return None
    if total_players != 2:
        return {"error": "pv_only_2"}
    bet_amount = 0
    has_bet = False
    if len(parts) >= 3:
        try:
            bet_amount = int(parts[2])
            has_bet = True
        except ValueError:
            return {"error": "bad_bet"}
        if bet_amount < MIN_BET:
            return {"error": "min_bet"}
    return {
        "total_players": 2,
        "bet_amount": bet_amount,
        "has_bet": has_bet,
        "explicit_mode": explicit_mode,
    }


@sync_to_async
def get_pv_start_settings(chat_id: int) -> dict:
    from account.models import TelegramGroup
    g = TelegramGroup.objects.filter(telegram_chat_id=int(chat_id)).first()
    if not g:
        return {"enabled": False, "reason": "", "soft_timeout": False}
    return {
        "enabled": bool(getattr(g, "pv_start_enabled", False)),
        "reason": (getattr(g, "pv_start_off_reason", None) or "").strip(),
        "soft_timeout": bool(getattr(g, "pv_soft_timeout", False)),
    }


@sync_to_async
def set_pv_start_settings(chat_id: int, *, enabled: bool | None = None, reason: str | None = None) -> dict:
    from account.models import TelegramGroup
    g, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=int(chat_id), defaults={"name": ""})
    fields = []
    if enabled is not None:
        g.pv_start_enabled = bool(enabled)
        fields.append("pv_start_enabled")
        if enabled:
            g.pv_start_off_reason = ""
            fields.append("pv_start_off_reason")
    if reason is not None and not (enabled is True):
        g.pv_start_off_reason = (reason or "").strip()[:300]
        if "pv_start_off_reason" not in fields:
            fields.append("pv_start_off_reason")
    if fields:
        g.save(update_fields=list(dict.fromkeys(fields)))
    return {
        "enabled": bool(g.pv_start_enabled),
        "reason": (g.pv_start_off_reason or "").strip(),
        "soft_timeout": bool(getattr(g, "pv_soft_timeout", False)),
    }


@sync_to_async
def get_pv_soft_timeout(chat_id: int) -> bool:
    from account.models import TelegramGroup

    g = TelegramGroup.objects.filter(telegram_chat_id=int(chat_id)).first()
    return bool(getattr(g, "pv_soft_timeout", False)) if g else False


@sync_to_async
def set_pv_soft_timeout(chat_id: int, enabled: bool) -> bool:
    from account.models import TelegramGroup

    g, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=int(chat_id), defaults={"name": ""},
    )
    g.pv_soft_timeout = bool(enabled)
    g.save(update_fields=["pv_soft_timeout"])
    return bool(g.pv_soft_timeout)


def _game_chat_on(game: dict) -> bool:
    return bool(game.get("chat_enabled", True))


def _apply_chat_enabled_to_live_games(group_id, enabled: bool) -> None:
    gid = int(group_id)
    on = bool(enabled)
    for g in GAMES.values():
        try:
            if int(g.get("group_id") or 0) == gid:
                g["chat_enabled"] = on
        except (TypeError, ValueError):
            continue


@sync_to_async
def _get_pv_chat_enabled_db(chat_id: int) -> bool:
    from account.models import TelegramGroup

    g = TelegramGroup.objects.filter(telegram_chat_id=int(chat_id)).first()
    if not g:
        return True
    return bool(getattr(g, "pv_chat_enabled", True))


@sync_to_async
def _set_pv_chat_enabled_db(chat_id: int, enabled: bool) -> bool:
    from account.models import TelegramGroup

    g, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=int(chat_id), defaults={"name": ""},
    )
    g.pv_chat_enabled = bool(enabled)
    g.save(update_fields=["pv_chat_enabled"])
    return bool(g.pv_chat_enabled)


async def get_pv_chat_enabled(chat_id: int) -> bool:
    key = str(int(chat_id))
    now = time.time()
    hit = _pv_chat_enabled_cache.get(key)
    if hit and now - hit[0] < _PV_CHAT_CACHE_TTL:
        return hit[1]
    val = await _get_pv_chat_enabled_db(chat_id)
    _pv_chat_enabled_cache[key] = (now, val)
    return val


async def set_pv_chat_enabled(chat_id: int, enabled: bool) -> bool:
    val = await _set_pv_chat_enabled_db(chat_id, enabled)
    key = str(int(chat_id))
    _pv_chat_enabled_cache[key] = (time.time(), val)
    _apply_chat_enabled_to_live_games(chat_id, val)
    return val


def format_pv_chat_status(enabled: bool) -> str:
    if enabled:
        return (
            "📡 وضعیت چت پیوی\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ روشن است\n\n"
            "بازیکنان می‌توانند داخل بازی پیوی متن/واکنش بفرستند."
        )
    return (
        "📡 وضعیت چت پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⛔️ خاموش است\n\n"
        "چت و واکنش داخل بازی پیوی برای این گروه غیرفعال است."
    )


@sync_to_async
def get_min_pv_bet(chat_id: int) -> int:
    from account.models import TelegramGroup

    g = TelegramGroup.objects.filter(telegram_chat_id=int(chat_id)).first()
    return int(getattr(g, "min_pv_bet", 0) or 0)


@sync_to_async
def set_min_pv_bet(chat_id: int, amount: int) -> int:
    from account.models import TelegramGroup

    g, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=int(chat_id), defaults={"name": ""},
    )
    g.min_pv_bet = max(0, int(amount))
    g.save(update_fields=["min_pv_bet"])
    return int(g.min_pv_bet)


@sync_to_async
def get_pv_results_chat_id(chat_id: int) -> int | None:
    from account.models import TelegramGroup

    g = TelegramGroup.objects.filter(telegram_chat_id=int(chat_id)).first()
    val = getattr(g, "pv_results_chat_id", None) if g else None
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


@sync_to_async
def set_pv_results_chat_id(chat_id: int, results_chat_id: int | None) -> int | None:
    from account.models import TelegramGroup

    g, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=int(chat_id), defaults={"name": ""},
    )
    g.pv_results_chat_id = int(results_chat_id) if results_chat_id is not None else None
    g.save(update_fields=["pv_results_chat_id"])
    return g.pv_results_chat_id


def parse_pv_results_chat_command(text: str) -> tuple[str, int | None] | None:
    """('show', None) | ('set', chat_id) | ('off', None) | None"""
    if not text:
        return None
    t = normalize_numbers(text).strip()
    if t in ("تنظیم گپ اعلام نتایج خاموش", "گپ اعلام نتایج خاموش"):
        return ("off", None)
    prefixes = ("تنظیم گپ اعلام نتایج", "گپ اعلام نتایج")
    matched = None
    for p in prefixes:
        if t == p or t.startswith(p + " "):
            matched = p
            break
    if matched is None:
        return None
    rest = t[len(matched):].strip()
    if not rest:
        return ("show", None)
    if rest in ("خاموش", "off", "0", "حذف"):
        return ("off", None)
    raw = rest.replace(",", "").replace("_", "").split()[0]
    if raw.lstrip("-").isdigit():
        return ("set", int(raw))
    return None


def effective_min_pv_bet(group_min: int) -> int:
    """حداقل مؤثر شرط پیوی — حداقل سراسری یا مقدار گروه (هرکدام بزرگ‌تر)."""
    gmin = int(group_min or 0)
    return max(MIN_BET, gmin) if gmin > 0 else MIN_BET


def parse_min_pv_command(text: str) -> tuple[str, int] | None:
    """('show', 0) | ('set', amount) | ('off', 0) | None"""
    if not text:
        return None
    t = text.strip()
    if t == "حداقل پیوی خاموش":
        return ("off", 0)
    if not t.startswith("حداقل پیوی"):
        return None
    suffix = t[len("حداقل پیوی"):].strip()
    if not suffix:
        return ("show", 0)
    raw = suffix.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if raw.isdigit() and int(raw) > 0:
        return ("set", int(raw))
    return None


def format_min_pv_denial(minimum: int, amount: int) -> str:
    return (
        f"❌ حداقل مبلغ بازی پیوی در این گروه {minimum:,} واحد است.\n"
        f"💰 مبلغ وارد شده: {amount:,} واحد\n\n"
        f"فقط از {minimum:,} به بالا می‌توانید درخواست بدهید.\n"
        f"مثال: <code>شروع 2 {minimum} پیوی</code>"
    )


def format_min_pv_free_denial(minimum: int) -> str:
    return (
        f"❌ در این گروه حداقل مبلغ بازی پیوی {minimum:,} واحد است.\n"
        "شروع بدون مبلغ (رایگان) مجاز نیست.\n\n"
        f"مثال: <code>شروع 2 {minimum} پیوی</code>"
    )


def find_group_active_pv_games(group_id: int, *, player_id: int | None = None) -> list[tuple[str, dict]]:
    gid = int(group_id)
    pid = int(player_id) if player_id is not None else None
    out: list[tuple[str, dict]] = []
    for game_id, game in list(GAMES.items()):
        if int(game.get("group_id") or 0) != gid:
            continue
        if game.get("status") in ("finished", "cancelled"):
            continue
        if pid is not None:
            players = {int(p) for p in (game.get("players") or [])}
            if pid not in players:
                continue
        out.append((game_id, game))
    return out


def find_group_pending_pv_invites(group_id: int, *, player_id: int | None = None) -> list[tuple[str, dict]]:
    gid = int(group_id)
    pid = int(player_id) if player_id is not None else None
    out: list[tuple[str, dict]] = []
    for invite_id, inv in list(INVITES.items()):
        if int(inv.get("group_id") or 0) != gid:
            continue
        if inv.get("status") != "pending":
            continue
        if pid is not None:
            involved = {int(inv["challenger_id"]), int(inv["target_id"])}
            if pid not in involved:
                continue
        out.append((invite_id, inv))
    return out


async def _admin_cancel_pending_invite(bot: Bot, invite_id: str, inv: dict, *, reason: str) -> None:
    INVITES.pop(invite_id, None)
    inv["status"] = "cancelled_admin"
    _unbind_user(inv["challenger_id"], "invite", invite_id)
    _unbind_user(inv["target_id"], "invite", invite_id)
    note = (
        "⛔ دعوت بازی پیوی توسط مدیر گروه لغو شد.\n"
        f"{reason}"
    )
    for uid in (inv["challenger_id"], inv["target_id"]):
        await send_private(bot, int(uid), note)
    try:
        group_id = int(inv["group_id"])
        ch = inv.get("challenger_name") or inv["challenger_id"]
        tg = inv.get("target_name") or inv["target_id"]
        await bot.send_message(
            group_id,
            f"⛔ دعوت پیوی {ch} → {tg} توسط مدیر لغو شد.",
        )
    except Exception:
        pass
    _persist_pv_state()


async def admin_cancel_pv_in_group(
    bot: Bot,
    group_id: int,
    *,
    player_id: int | None = None,
) -> str:
    """لغو بازی/دعوت پیوی فعال در گروه (بازگشت ورودی در صورت کسر)."""
    games = find_group_active_pv_games(group_id, player_id=player_id)
    if len(games) > 1:
        return (
            "⚠️ چند مسابقه پیوی هم‌زمان فعال است.\n"
            "روی پیام یکی از بازیکنان ریپلای کنید و دوباره بنویسید:\n"
            "<code>لغو پیوی</code>"
        )
    if len(games) == 1:
        game_id, game = games[0]
        if game.get("paid") and game.get("entry"):
            pm_msg = "مسابقه توسط مدیر گروه لغو شد؛ ورودی به کیف پول برمی‌گردد."
        else:
            pm_msg = "مسابقه توسط مدیر گروه لغو شد."
        await _cancel_game_refund(bot, game_id, pm_msg)
        _persist_pv_state()
        return "✅ مسابقه پیوی لغو شد و به بازیکنان اطلاع داده شد."

    invites = find_group_pending_pv_invites(group_id, player_id=player_id)
    if len(invites) > 1:
        return (
            "⚠️ چند دعوت پیوی در انتظار است.\n"
            "روی پیام یکی از بازیکنان ریپلای کنید و بنویسید:\n"
            "<code>لغو پیوی</code>"
        )
    if len(invites) == 1:
        invite_id, inv = invites[0]
        await _admin_cancel_pending_invite(
            bot, invite_id, inv, reason="هنوز بازی شروع نشده بود.",
        )
        return "✅ دعوت پیوی لغو شد."

    # جستجوی حریف گیرکرده / در انتظار قبول
    try:
        from bot.pv_search import SEARCH_OFFERS, clear_pv_search

        search_hits: list[tuple[str, dict]] = []
        for oid, offer in list(SEARCH_OFFERS.items()):
            if offer.get("status") != "pending":
                continue
            if int(offer.get("group_id") or 0) != int(group_id):
                continue
            if player_id is not None and int(offer.get("challenger_id") or 0) != int(player_id):
                continue
            search_hits.append((str(oid), offer))
        if len(search_hits) > 1 and player_id is None:
            return (
                "⚠️ چند جستجوی حریف پیوی فعال است.\n"
                "روی پیام جستجوکننده ریپلای کنید و بنویسید:\n"
                "<code>لغو پیوی</code>"
            )
        if search_hits:
            for oid, offer in search_hits:
                ch = offer.get("challenger_id")
                if ch:
                    clear_pv_search(int(ch))
                    try:
                        await send_private(bot, int(ch), "⛔ جستجوی حریف توسط مدیر گروه لغو شد.")
                    except Exception:
                        pass
            return "✅ جستجوی حریف پیوی لغو شد."
        if player_id is not None:
            busy = user_busy(player_id)
            if busy and busy[0] == "search":
                clear_pv_search(int(player_id))
                try:
                    await send_private(bot, int(player_id), "⛔ جستجوی حریف توسط مدیر گروه لغو شد.")
                except Exception:
                    pass
                return "✅ جستجوی حریف پیوی لغو شد."
    except Exception:
        logger.exception("admin_cancel_pv search clear failed")

    if player_id is not None:
        return "📭 بازی یا دعوت پیوی فعالی برای این کاربر در این گروه نیست."
    return (
        "📭 بازی پیوی فعالی برای لغو نیست.\n"
        "اگر مسابقه در جریان است، روی پیام یکی از بازیکنان ریپلای کنید:\n"
        "<code>لغو پیوی</code>"
    )


def user_busy(user_id: int) -> tuple[str, str] | None:
    return USER_BUSY.get(int(user_id))


def find_user_live_pv_game(user_id: int) -> dict | None:
    uid = int(user_id)
    for game in GAMES.values():
        if not game or game.get("status") in ("finished", "cancelled", None):
            continue
        try:
            players = [int(p) for p in (game.get("players") or [])]
        except (TypeError, ValueError):
            continue
        if uid in players:
            return game
    return None


def find_user_pending_invite(user_id: int) -> dict | None:
    uid = int(user_id)
    now = time.time()
    for inv in INVITES.values():
        if not inv or inv.get("status") not in ("pending", "accepting"):
            continue
        if now > float(inv.get("expires_at") or 0) and inv.get("status") == "pending":
            continue
        try:
            if uid in (int(inv.get("challenger_id")), int(inv.get("target_id"))):
                return inv
        except (TypeError, ValueError):
            continue
    return None


def pv_user_is_occupied(user_id: int) -> str | None:
    game = find_user_live_pv_game(user_id)
    if game:
        try:
            _bind_user(user_id, "game", game["id"], force=True)
        except Exception:
            pass
        return user_busy_label(user_id) or "playing"
    label = user_busy_label(user_id)
    if label:
        return label
    if find_user_pending_invite(user_id):
        return "invite"
    try:
        from bot.dice_game import is_user_involved_in_any_group_game
        if is_user_involved_in_any_group_game(user_id):
            return "group"
    except Exception:
        pass
    return None


def get_active_pv_game(user_id: int) -> dict | None:
    """بازی پیوی فعال کاربر (qualifying / awaiting_rounds / playing) یا None."""
    busy = user_busy(user_id)
    if busy and busy[0] == "game":
        game = GAMES.get(busy[1])
        if game and game.get("status") not in ("finished", "cancelled"):
            return game
    game = find_user_live_pv_game(user_id)
    if game:
        _bind_user(user_id, "game", game["id"], force=True)
        return game
    return None


def is_in_active_pv_game(user_id: int) -> bool:
    return get_active_pv_game(user_id) is not None


_PV_LOCK_MENU_TEXTS = frozenset({
    "استارت", "شروع", "start", "Start", "START",
    "راهنما", "help", "Help", "HELP",
    "منو", "پنل", "menu", "Menu", "MENU",
    "خروج", "لغو", "انصراف", "cancel", "exit",
    "بازگشت", "خانه", "home",
})


def is_pv_locked_misc_text(text: str | None) -> bool:
    """دستور/منوی متفرقه که وسط بازی نباید اجرا یا به حریف فوروارد شود."""
    t = (text or "").strip()
    if not t:
        return False
    if t.startswith("/"):
        return True
    if t in _PV_LOCK_MENU_TEXTS:
        return True
    # /start@BotName
    low = t.lower()
    if low.startswith("/start") or low.startswith("start@"):
        return True
    return False


def _rebuild_busy_from_live_games() -> None:
    changed = False
    for game in list(GAMES.values()):
        if not game or game.get("status") in ("finished", "cancelled", None):
            continue
        gid = str(game.get("id") or "").strip()
        if not gid:
            continue
        for p in game.get("players") or []:
            try:
                key = int(p)
            except (TypeError, ValueError):
                continue
            cur = USER_BUSY.get(key)
            if cur and cur[0] == "game" and str(cur[1]) == gid:
                continue
            USER_BUSY[key] = ("game", gid)
            changed = True
    if changed:
        _persist_pv_state()


def _heal_orphan_busy_locks() -> None:
    """پاک‌سازی قفل‌های بدون دعوت/بازی/آفر معتبر."""
    now = time.time()
    try:
        from bot.pv_search import SEARCH_OFFERS
    except Exception:
        SEARCH_OFFERS = {}

    changed = False
    for uid, busy in list(USER_BUSY.items()):
        if not busy or not isinstance(busy, (tuple, list)) or len(busy) < 2:
            USER_BUSY.pop(uid, None)
            changed = True
            continue
        kind, oid = busy[0], busy[1]
        if kind == "search":
            offer = SEARCH_OFFERS.get(str(oid))
            if (
                not offer
                or offer.get("status") != "pending"
                or now > float(offer.get("expires_at") or 0)
            ):
                USER_BUSY.pop(uid, None)
                changed = True
            continue
        if kind == "invite":
            inv = INVITES.get(oid)
            if not inv or inv.get("status") not in ("pending", "accepting"):
                USER_BUSY.pop(uid, None)
                changed = True
                continue
            if inv.get("status") == "pending" and now > float(inv.get("expires_at") or 0):
                # مهلت گذشته — sweeper منقضی می‌کند؛ فعلاً قفل را نگه دار تا expire تمیز انجام شود
                continue
            continue
        if kind == "game":
            game = GAMES.get(oid)
            if not game or game.get("status") in ("finished", "cancelled", None):
                USER_BUSY.pop(uid, None)
                changed = True
    if changed:
        _persist_pv_state()


def user_busy_label(user_id: int) -> str | None:
    """برچسب کوتاه وضعیت قفل کاربر — دعوت‌شونده تا قبول آزاد است؛ حین accepting هر دو قفل‌اند."""
    busy = user_busy(user_id)
    if not busy:
        return None
    kind, oid = busy
    if kind == "search":
        try:
            from bot.pv_search import SEARCH_OFFERS
            offer = SEARCH_OFFERS.get(str(oid))
        except Exception:
            offer = None
        if (
            offer
            and offer.get("status") == "pending"
            and time.time() <= float(offer.get("expires_at") or 0)
        ):
            return "search"
        # قفل یتیم / منقضی — آزاد کن
        _unbind_user(int(user_id), "search", str(oid))
        return None
    if kind == "invite":
        inv = INVITES.get(oid)
        if not inv:
            _unbind_user(int(user_id), "invite", str(oid))
            return None
        st = inv.get("status")
        # pending: فقط فرستنده | accepting: هر دو طرف (bind شده)
        if st == "accepting":
            return "invite"
        if st != "pending":
            _unbind_user(int(user_id), "invite", str(oid))
            return None
        if time.time() > float(inv.get("expires_at") or 0):
            # مهلت تمام — قفل را باز کن؛ sweeper دعوت را می‌بندد
            _unbind_user(int(user_id), "invite", str(oid))
            return None
        if int(inv.get("challenger_id") or 0) != int(user_id):
            return None
        return "invite"
    game = GAMES.get(oid)
    if not game:
        _unbind_user(int(user_id), "game", str(oid))
        return None
    st = game.get("status")
    if st in ("finished", "cancelled"):
        _unbind_user(int(user_id), "game", str(oid))
        return None
    if st == "qualifying":
        return "qualifying"
    if st == "awaiting_rounds":
        return "awaiting_rounds"
    if st == "playing":
        return "playing"
    return "game"


def bind_search_offer(user_id: int, offer_id: str) -> None:
    _bind_user(int(user_id), "search", str(offer_id))


def unbind_search_offer(user_id: int, offer_id: str | None = None) -> None:
    _unbind_user(int(user_id), "search", str(offer_id) if offer_id else None)


def _busy_conflicts_with_invite(user_id: int, invite_id: str) -> str | None:
    """اگر کاربر با بازی/دعوت دیگری مشغول است، کد busy برمی‌گرداند."""
    busy = user_busy(user_id)
    if not busy:
        return None
    kind, oid = busy
    if kind == "invite" and str(oid) == str(invite_id):
        return None
    # فقط اگر label معتبر باشد قفل است (قفل یتیم/منقضی را kind خام حساب نکن)
    return user_busy_label(user_id)


def resolve_pv_busy_opponent_name(user_id: int) -> str:
    """نام حریف فعلی در دعوت/بازی پیوی که این کاربر را مشغول کرده."""
    busy = user_busy(user_id)
    if not busy:
        return ""
    kind, oid = busy
    uid = int(user_id)
    if kind == "invite":
        inv = INVITES.get(oid)
        if not inv:
            return ""
        if int(inv.get("challenger_id") or 0) == uid:
            return (inv.get("target_name") or "").strip() or str(inv.get("target_id") or "")
        return (inv.get("challenger_name") or "").strip() or str(inv.get("challenger_id") or "")
    game = GAMES.get(oid)
    if not game:
        return ""
    names = game.get("names") or {}
    for p in game.get("players") or []:
        try:
            pid = int(p)
        except (TypeError, ValueError):
            continue
        if pid == uid:
            continue
        return str(names.get(pid) or names.get(str(pid)) or names.get(p) or pid).strip()
    return ""


def pv_busy_short_title(code: str) -> str:
    return {
        "invite": "دعوت بازی پیوی (منتظر پاسخ حریف)",
        "search": "جستجوی حریف پیوی (منتظر قبول)",
        "qualifying": "مسابقه پیوی — تاس تعیین",
        "awaiting_rounds": "مسابقه پیوی — انتخاب تعداد راند",
        "playing": "مسابقه پیوی — در حال انجام",
        "game": "مسابقه پیوی فعال",
    }.get(code or "", "مسابقه پیوی فعال")


def format_pv_busy_message(
    code: str,
    *,
    for_other: bool = False,
    other_name: str = "",
    user_id: int | None = None,
) -> str:
    """متن واضح وقتی کاربر (یا حریف) مشغول پیوی است."""
    opp = resolve_pv_busy_opponent_name(user_id) if user_id is not None else ""
    with_opp = f" با {opp}" if opp else ""

    if code == "search":
        if for_other:
            who = other_name or "این کاربر"
            return (
                f"⏳ {who} در حال جستجوی حریف پیوی است و منتظر قبول درخواست است.\n"
                "بعد از پیدا شدن حریف یا لغو جستجو، دوباره تلاش کنید."
            )
        return (
            "⚠️ الان نمی‌توانید چالش جدید بفرستید.\n\n"
            "وضعیت شما:\n"
            "🔍 درخواست جستجوی حریف ارسال شده و منتظر قبول هستید.\n\n"
            "💡 برای آزاد شدن:\n"
            "در پیوی ربات جستجو را لغو کنید، یا صبر کنید تا کسی قبول کند / مهلت تمام شود."
        )

    if code == "invite":
        if for_other:
            who = other_name or "این کاربر"
            if opp:
                return (
                    f"⏳ {who} دعوت بازی پیوی برای {opp} فرستاده و منتظر پاسخ است.\n"
                    "بعد از قبول/رد یا لغو دعوت، دوباره تلاش کنید."
                )
            return (
                f"⏳ {who} دعوت بازی پیوی فرستاده و منتظر پاسخ حریف است.\n"
                "بعد از قبول/رد یا لغو دعوت، دوباره تلاش کنید."
            )
        if opp:
            return (
                "⚠️ الان نمی‌توانید چالش جدید بفرستید.\n\n"
                "وضعیت شما:\n"
                f"📤 دعوت بازی پیوی برای {opp} ارسال شده و منتظر پاسخ هستید.\n\n"
                "💡 برای آزاد شدن:\n"
                "به پیوی ربات بروید و روی همان دعوت دکمه «❌ لغو دعوت» را بزنید.\n"
                "یا صبر کنید تا حریف قبول/رد کند یا مهلت دعوت تمام شود."
            )
        return (
            "⚠️ الان نمی‌توانید چالش جدید بفرستید.\n\n"
            "وضعیت شما:\n"
            "📤 دعوت بازی پیوی ارسال شده و منتظر پاسخ حریف هستید.\n\n"
            "💡 برای آزاد شدن:\n"
            "به پیوی ربات بروید و روی همان دعوت دکمه «❌ لغو دعوت» را بزنید.\n"
            "یا صبر کنید تا حریف قبول/رد کند یا مهلت دعوت تمام شود."
        )
    if code == "qualifying":
        body = f"🎲 مسابقه پیوی{with_opp} — مرحله تاس تعیین"
        tip = "اول در پیوی ربات تاس تعیین را بزنید و بازی را تمام کنید."
    elif code == "awaiting_rounds":
        body = f"🎲 مسابقه پیوی{with_opp} — انتخاب تعداد راند"
        tip = "اول در پیوی ربات تعداد راند را مشخص کنید (یا منتظر حریف بمانید)."
    elif code == "playing":
        body = f"🎲 مسابقه پیوی{with_opp} — در حال انجام"
        tip = "اول بازی فعلی را در پیوی ربات تمام کنید."
    else:
        body = f"🎲 مسابقه پیوی{with_opp} فعال" if with_opp else "🎲 مسابقه پیوی فعال"
        tip = "اول بازی فعلی را تمام کنید."

    if for_other:
        who = other_name or "این کاربر"
        return f"⏳ {who} الان مشغول است:\n{body}\nمنتظر پایان بازی بمانید."
    return (
        "⚠️ الان نمی‌توانید چالش جدید بفرستید.\n\n"
        f"وضعیت شما:\n{body}\n\n"
        f"💡 {tip}"
    )


def _bind_user(user_id: int, kind: str, oid: str, *, force: bool = False) -> bool:
    key = int(user_id)
    oid = str(oid)
    cur = USER_BUSY.get(key)
    if cur and not force:
        ck, co = cur[0], str(cur[1])
        if ck == kind and co == oid:
            return True
        upgrades = {("search", "invite"), ("search", "game"), ("invite", "game")}
        if (ck, kind) not in upgrades:
            return False
    USER_BUSY[key] = (kind, oid)
    _persist_pv_state()
    return True


def _unbind_user(user_id: int, kind: str | None = None, oid: str | None = None) -> None:
    cur = USER_BUSY.get(int(user_id))
    if not cur:
        AWAITING_CUSTOM_DICE.pop(int(user_id), None)
        _persist_pv_state()
        return
    if kind and cur[0] != kind:
        return
    if oid and cur[1] != oid:
        return
    USER_BUSY.pop(int(user_id), None)
    AWAITING_CUSTOM_DICE.pop(int(user_id), None)
    _persist_pv_state()


def _invite_challenger_kb(invite_id: str) -> InlineKeyboardMarkup:
    return _kb([[IKB(text="❌ لغو دعوت", callback_data=f"pvd:can:{invite_id}")]])


def _invite_target_kb(invite_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [
            IKB(text="✅ قبول چالش", callback_data=f"pvd:acc:{invite_id}"),
            IKB(text="❌ رد", callback_data=f"pvd:rej:{invite_id}"),
        ],
        [IKB(text="ℹ️ جزئیات مبلغ بازی", callback_data=f"pvd:inf:{invite_id}")],
    ])


def _game_roll_kb(
    game_id: str,
    *,
    remaining: int = 0,
    actions_left: int | None = None,
    allow_custom: bool = False,
    for_uid: int | None = None,
    game: dict | None = None,
) -> InlineKeyboardMarkup:
    # نوبت آخر با محدودیت: فقط همه باقی‌مانده
    if actions_left == 1 and remaining > 1:
        rows = [[IKB(text=f"🎲 تاس {remaining}", callback_data=f"pvd:roll:{game_id}:{remaining}")]]
    else:
        rows = [[IKB(text="🎲 تاس", callback_data=f"pvd:roll:{game_id}:1")]]
        if remaining > 1:
            shortcuts = []
            for n in (2, 3, 5, 10):
                if 1 < n < remaining:
                    shortcuts.append(IKB(text=f"تاس {n}", callback_data=f"pvd:roll:{game_id}:{n}"))
            if shortcuts:
                rows.append(shortcuts[:3])
            rows.append([IKB(text=f"تاس {remaining} (همه)", callback_data=f"pvd:roll:{game_id}:{remaining}")])
    if allow_custom:
        rows.append([IKB(text="✏️ تاس دلخواه", callback_data=f"pvd:custom:{game_id}")])
    chat_on = bool(game is None or _game_chat_on(game))
    if chat_on:
        rows.append([
            IKB(text="📊 وضعیت", callback_data=f"pvd:st:{game_id}"),
            IKB(text="💬 چت", callback_data=f"pvd:chat:{game_id}"),
        ])
        rows.append([
            IKB(text=emoji, callback_data=f"pvd:rx:{game_id}:{i}")
            for i, (emoji, _title) in enumerate(social.QUICK_REACTS[:4])
        ])
        if (
            game is not None
            and for_uid is not None
            and not social.chat_block_used(game, for_uid)
        ):
            if social.is_chat_blocked_by(game, for_uid):
                blk_label = "🔊 رفع بلاک چت"
            else:
                blk_label = "🔇 بلاک چت"
            rows.append([IKB(text=blk_label, callback_data=f"pvd:blk:{game_id}")])
    else:
        rows.append([IKB(text="📊 وضعیت", callback_data=f"pvd:st:{game_id}")])
    return _kb(rows)


def _rounds_prompt_kb(game_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [IKB(text="↩️ بازگشت به بازی", callback_data=f"pvd:back:{game_id}")],
        [IKB(text="📊 وضعیت بازی", callback_data=f"pvd:st:{game_id}")],
    ])


def _roll_kb_for(game: dict, for_uid: int | None = None) -> InlineKeyboardMarkup:
    gid = game["id"]
    st = game.get("status")
    if st == "qualifying":
        return _game_roll_kb(gid, allow_custom=False, for_uid=for_uid, game=game)
    if st == "awaiting_rounds":
        return _rounds_prompt_kb(gid)
    if st != "playing":
        return _game_roll_kb(gid, allow_custom=False, for_uid=for_uid, game=game)
    turn = game.get("turn")
    rem = int((game.get("remaining") or {}).get(turn, 0) or 0) if turn else 0
    al = None
    if turn is not None and game.get("actions_left") is not None:
        al = (game.get("actions_left") or {}).get(turn)
    return _game_roll_kb(
        gid, remaining=rem, actions_left=al, allow_custom=True, for_uid=for_uid, game=game,
    )


def format_off_message(reason: str) -> str:
    reason = (reason or "").strip() or "بدون توضیح"
    return (
        "🌙 شروع پیوی فعلاً خاموش است\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 دلیل: {reason}\n\n"
        "وقتی مدیر دوباره روشن کند می‌توانید چالش پیوی بفرستید."
    )


def format_status_message(cfg: dict) -> str:
    if cfg.get("enabled"):
        return (
            "📡 وضعیت شروع پیوی\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ روشن است\n\n"
            "مثال (با ریپلای روی حریف):\n"
            "• <code>شروع 2 100 پیوی</code>\n"
            "• <code>شروع 2 100 فیکس پیوی</code>\n"
            "• <code>شروع 2 50 اضافه پیوی</code>"
        )
    reason = (cfg.get("reason") or "").strip() or "بدون توضیح"
    return (
        "📡 وضعیت شروع پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⛔️ خاموش است\n"
        f"📝 دلیل: {reason}"
    )


def format_pv_forfeit_status(soft: bool) -> str:
    if soft:
        return (
            "📡 وضعیت باخت پیوی\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🌙 خاموش است\n\n"
            "تأخیر در تاس تعیین / تعیین راند / قبل از اولین تاس بازی → لغو (نه باخت).\n"
            "از اولین تاس بعد از تعیین راند → باخت مهلت مثل قبل."
        )
    return (
        "📡 وضعیت باخت پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ روشن است\n\n"
        "تأخیر در هر مرحله → باخت مهلت."
    )


def _normalize_pv_text(text: str) -> str:
    raw = normalize_numbers((text or "").strip())
    return re.sub(r"\s+", " ", raw).strip()


def _parse_rounds_input(text: str) -> int | None:
    t = _normalize_pv_text(text)
    if not t:
        return None
    t = t.replace(",", "").replace("،", "").replace("_", "").replace("٫", "")
    m = re.fullmatch(r"(\d{1,10})", t)
    if m:
        n = int(m.group(1))
        return n if n >= 1 else None
    m = re.fullmatch(r"(\d{1,10})\s*(راند|تاس|دور|round|rounds)?", t, flags=re.I)
    if m:
        n = int(m.group(1))
        return n if n >= 1 else None
    return None


_DICE_FORMAT_HELP = (
    "❌ فرمت دستور تاس اشتباه است.\n\n"
    "📌 راهنمای فرمت صحیح:\n\n"
    "1️⃣ تاس + یک فاصله + عدد\n"
    "✅ تاس 30\n\n"
    "2️⃣ تاس + عدد\n"
    "✅ تاس30\n\n"
    "⚠️ فقط همین دو فرمت قابل قبول هستند.\n"
    "از گذاشتن فاصله‌های اضافی، رفتن به خط بعد و نوشتن صفر قبل از عدد خودداری کنید."
)


def parse_group_dice_count(text: str) -> tuple[int | None, str | None]:
    """همان قواعد تاس گروه: «تاس» یا «تاس N» / «تاسN»."""
    raw = (text or "").strip()
    if not raw:
        return None, None
    norm = normalize_numbers(raw)
    if norm == "تاس":
        return 1, None
    if not norm.startswith("تاس"):
        return None, None
    match = re.fullmatch(r"تاس\s*([0-9]+)\s*", norm)
    if not match:
        if not any(ch.isdigit() for ch in norm[3:]):
            return None, None
        return None, _DICE_FORMAT_HELP
    n = int(match.group(1))
    if n <= 0:
        return None, None
    if n > 1_000_000_000:
        n = 1_000_000_000
    return n, None


def _pv_text_is_roll_related(raw: str) -> bool:
    count, err = parse_group_dice_count(raw)
    return count is not None or err is not None


def _group_dice_option_off(group_id: int) -> bool:
    return int(group_id) not in bot_cache.DICE_OPTION


def _group_turn_limit(group_id: int) -> int:
    return int(bot_cache.DICE_TURN_LIMIT.get(int(group_id)) or 0)


def _can_pv_roll(game: dict, uid: int, dice_count: int) -> tuple[bool, int, str]:
    if int(game.get("turn") or 0) != int(uid):
        return False, 0, "⏳ نوبت بازیکن دیگر است!\nلطفاً صبر کنید تا نوبت شما برسد."
    remaining = int(_map_get(game.get("remaining"), uid, 0) or 0)
    if remaining <= 0:
        return False, 0, "❌ شما تمام راندهای خود را ریخته‌اید!"
    if dice_count > remaining:
        return False, remaining, f"❌ شما فقط {remaining} راند باقی دارید!"
    total_rounds = int(game.get("total_rounds") or 0)
    already = int(_map_get(game.get("dice_rolled"), uid, 0) or 0)
    if total_rounds > 0 and already + int(dice_count) > total_rounds:
        left = max(0, total_rounds - already)
        return False, left, (
            f"❌ سقف راند این بازی {total_rounds} تاس است.\n"
            f"شما {already} تاس ریخته‌اید؛ حداکثر {left} تاس دیگر مجاز است."
        )
    limit = int(game.get("dice_turn_limit") or 0)
    actions_left = _map_get(game.get("actions_left"), uid, None)
    if limit > 0 and actions_left is not None:
        try:
            actions_left = int(actions_left)
        except (TypeError, ValueError):
            actions_left = None
    if limit > 0 and actions_left is not None:
        if actions_left <= 0:
            return False, remaining, (
                f"⚠️ محدودیت تعداد تاس این گپ: {limit} نوبت\n\n"
                f"نوبت‌های مجازت تمام شده است."
            )
        if actions_left == 1 and dice_count != remaining:
            return False, remaining, format_turn_limit_error(limit, remaining, dice_count)
    return True, remaining, f"🎯 {remaining} راند باقی مانده"


def _build_roll_message(
    group_id: int, dice_count: int, *, skip_consecutive: bool = False, user_id=None,
) -> tuple[str, int]:
    """فرمت دقیقاً مثل تاس گروه + مجموع امتیاز این پرتاب."""
    theme = get_theme(get_group_theme(int(group_id)))
    if user_id is not None:
        isolate_match_dice(group_id, user_id)
    dice_option_off = _group_dice_option_off(group_id) and not skip_consecutive
    if dice_count == 1:
        r = roll_dice(int(group_id), dice_option_off)
        return build_single_dice_message(r, theme), r
    if dice_count <= 30:
        results, total = _generate_dice_numbers(dice_count, int(group_id), dice_option_off)
        return build_multi_dice_message(results, total, dice_count, theme), total
    freq = _multinomial_fair(dice_count)
    total = sum(face * freq[face] for face in range(1, 7))
    inv_count = 100.0 / dice_count
    chart = []
    for num in range(1, 7):
        f = freq[num]
        percent = f * inv_count
        bars = "█" * max(1, int(percent / 5))
        chart.append(f"{num}️⃣  | {bars} {f} بار (~{percent:.1f}٪)")
    msg = "\n".join((
        "📊 نتایج تاس‌ها",
        f"📌 تعداد تاس‌ها: {dice_count:,}",
        f"🔢 مجموع اعداد: {total:,}",
        "────────────────────",
        "📊 تحلیل آماری:",
        *chart,
        "────────────────────",
        "💡 هرچه تعداد تاس بیشتر باشد، نتیجه‌ها یکنواخت‌تر می‌شوند.",
    ))
    return msg, total


def _append_progress(msg: str, *, rem: int, total_score: int, finished: bool) -> str:
    if finished or rem <= 0:
        return (
            f"{msg}\n\n━━━━━━━━━━━━━━━━\n"
            f"✅ راندهای شما تمام شد!\n"
            f"📊 امتیاز نهایی شما: {total_score}\n"
            f"⏳ منتظر پایان بازی بازیکنان دیگر..."
        )
    return (
        f"{msg}\n\n━━━━━━━━━━━━━━━━\n"
        f"🎯 {rem} راند دیگر باقی مانده\n"
        f"📊 امتیاز فعلی: {total_score}"
    )


async def handle_pv_setting_command(message, bot: Bot) -> bool:
    """شروع پیوی | شروع پیوی روشن | شروع پیوی خاموش [دلیل] | شروع پیوی وضعیت

    روشن/خاموش فقط برای سازنده؛ بقیه هیچ پاسخی نمی‌گیرند.
    """
    from bot.cache_manager import is_admin, is_owner
    from bot.constants import CREATOR_USER_ID

    text = " ".join((message.text or "").replace("\u200c", " ").split())
    if not text.startswith("شروع پیوی"):
        return False
    chat_id = message.chat.id
    user_id = message.from_user.id
    rest = text[len("شروع پیوی"):].strip()

    if rest in ("", "وضعیت", "status"):
        cfg = await get_pv_start_settings(chat_id)
        await message.reply(format_status_message(cfg), parse_mode="HTML")
        return True

    is_on = rest in ("روشن", "on", "فعال")
    is_off = rest.startswith("خاموش") or rest.startswith("off") or rest.startswith("غیرفعال")
    if is_on or is_off:
        # فقط سازنده — بدون هیچ پیام خطایی برای دیگران
        if int(user_id) != int(CREATOR_USER_ID):
            return True
        if is_on:
            await set_pv_start_settings(chat_id, enabled=True)
            await message.reply(
                "✅ شروع پیوی روشن شد.\n"
                "اعضا می‌توانند با ریپلای روی حریف بنویسند:\n"
                "<code>شروع 2 100 پیوی</code>",
                parse_mode="HTML",
            )
            return True
        reason = rest
        for prefix in ("خاموش", "off", "غیرفعال"):
            if reason.startswith(prefix):
                reason = reason[len(prefix):].strip()
                break
        if not reason:
            reason = "شروع چالش گروهی"
        await set_pv_start_settings(chat_id, enabled=False, reason=reason)
        await message.reply(
            "⛔️ شروع پیوی خاموش شد.\n"
            f"📝 دلیل نمایش‌داده‌شده به اعضا: <b>{reason}</b>",
            parse_mode="HTML",
        )
        return True

    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        await message.reply("❌ فقط مدیران می‌توانند شروع پیوی را تغییر دهند.")
        return True

    await message.reply(
        "📖 راهنمای شروع پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• <code>شروع پیوی وضعیت</code>\n"
        "• <code>شروع پیوی روشن</code> (فقط سازنده)\n"
        "• <code>شروع پیوی خاموش [دلیل]</code> (فقط سازنده)\n\n"
        "چالش توسط اعضا:\n"
        "<code>شروع 2 100 پیوی</code> (با ریپلای)",
        parse_mode="HTML",
    )
    return True


async def handle_pv_forfeit_setting_command(message, bot: Bot) -> bool:
    """باخت پیوی | باخت پیوی روشن | باخت پیوی خاموش | باخت پیوی وضعیت"""
    from bot.cache_manager import is_admin, is_owner

    text = " ".join((message.text or "").replace("\u200c", " ").split())
    if not text.startswith("باخت پیوی"):
        return False
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        await message.reply("❌ فقط مدیران می‌توانند باخت پیوی را تغییر دهند.")
        return True

    rest = text[len("باخت پیوی"):].strip()

    if rest in ("", "وضعیت", "status"):
        soft = await get_pv_soft_timeout(chat_id)
        await message.reply(format_pv_forfeit_status(soft), parse_mode="HTML")
        return True

    is_on = rest in ("روشن", "on", "فعال")
    is_off = rest in ("خاموش", "off", "غیرفعال")
    if is_on or is_off:
        soft = is_off
        await set_pv_soft_timeout(chat_id, soft)
        if soft:
            await message.reply(
                "🌙 باخت پیوی خاموش شد.\n"
                "اگر کسی در تاس تعیین / تعیین راند / قبل از اولین تاس بازی دیر کند،"
                " بازی لغو می‌شود (باخت نمی‌خورد).\n"
                "از اولین تاس بعد از تعیین راند، تأخیر مثل قبل باخت می‌زند.",
            )
        else:
            await message.reply(
                "✅ باخت پیوی روشن شد.\n"
                "تأخیر در هر مرحله (تاس تعیین، راند، بازی) مثل قبل باخت می‌زند.",
            )
        return True

    await message.reply(
        "📖 راهنمای باخت پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• <code>باخت پیوی وضعیت</code>\n"
        "• <code>باخت پیوی روشن</code> — باخت مهلت در همه مراحل\n"
        "• <code>باخت پیوی خاموش</code> — قبل از اولین تاس بازی اصلی، تأخیر فقط لغو است\n\n"
        "بعد از اولین تاس بازی (پس از تعیین راند) همیشه باخت مهلت اعمال می‌شود.",
        parse_mode="HTML",
    )
    return True


async def handle_pv_chat_setting_command(message, bot: Bot) -> bool:
    """چت پیوی روشن | چت پیوی خاموش | چت پیوی وضعیت

    توجه: خودِ «چت پیوی» (با ریپلای) گزارش چت ادمین است و اینجا نیست.
    """
    from bot.cache_manager import is_admin, is_owner

    text = (message.text or "").strip()
    m = re.match(r"^چت\s*پیوی\s*(.*)$", text)
    if not m:
        return False
    rest = (m.group(1) or "").strip()
    if not rest:
        return False

    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        await message.reply("❌ فقط مدیران می‌توانند چت پیوی را تغییر دهند.")
        return True

    if rest in ("وضعیت", "status"):
        on = await get_pv_chat_enabled(chat_id)
        await message.reply(format_pv_chat_status(on))
        return True

    is_on = rest in ("روشن", "on", "فعال")
    is_off = rest in ("خاموش", "off", "غیرفعال")
    if is_on or is_off:
        on = await set_pv_chat_enabled(chat_id, is_on)
        if on:
            await message.reply(
                "✅ چت پیوی روشن شد.\n"
                "بازیکنان می‌توانند داخل بازی متن و واکنش بفرستند.",
            )
        else:
            await message.reply(
                "🌙 چت پیوی خاموش شد.\n"
                "چت و واکنش داخل بازی برای این گروه غیرفعال است.",
            )
        return True

    await message.reply(
        "📖 راهنمای چت پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• <code>چت پیوی وضعیت</code>\n"
        "• <code>چت پیوی روشن</code>\n"
        "• <code>چت پیوی خاموش</code>\n\n"
        "برای مشاهدهٔ چت یک کاربر: روی پیامش ریپلای کنید و بنویسید <code>چت پیوی</code>.",
        parse_mode="HTML",
    )
    return True


async def create_invite(bot: Bot, *, group_id: int, challenger_id: int, target_id: int,
                        bet_amount: int, has_bet: bool, bet_mode: str, fee_percent: int,
                        group_msg_id: int | None, challenger_name: str, target_name: str,
                        via_search: bool = False, deliver: bool = True) -> str:
    # جلوگیری از ساخت/ارسال دوباره همان دعوت (هندلر دوبل یا race).
    sig = _invite_signature(
        group_id=int(group_id),
        challenger_id=int(challenger_id),
        target_id=int(target_id),
        bet_amount=int(bet_amount),
        has_bet=bool(has_bet),
        bet_mode=bet_mode,
        fee_percent=int(fee_percent),
    )
    lock = _invite_sig_locks.setdefault(sig, asyncio.Lock())
    async with lock:
        now = time.time()
        prev = _recent_invite_by_sig.get(sig)
        if prev and (now - float(prev[0])) <= _RECENT_INVITE_WINDOW_SEC:
            live = INVITES.get(prev[1])
            if live and live.get("status") == "pending":
                return prev[1]
            _recent_invite_by_sig.pop(sig, None)

        # جلوگیری از دو دعوت همزمان / دعوت وسط بازی گروهی
        if pv_user_is_occupied(challenger_id):
            return ""
        if pv_user_is_occupied(target_id):
            return ""
        try:
            from bot.dice_game import is_user_involved_in_any_group_game
            if (
                is_user_involved_in_any_group_game(challenger_id)
                or is_user_involved_in_any_group_game(target_id)
            ):
                return ""
        except Exception:
            pass

        invite_id = uuid.uuid4().hex[:12]
        _recent_invite_by_sig[sig] = (now, invite_id)
        if len(_recent_invite_by_sig) > 512:
            cutoff = now - (_RECENT_INVITE_WINDOW_SEC * 4)
            for k, (ts, _iid) in list(_recent_invite_by_sig.items()):
                if ts < cutoff:
                    _recent_invite_by_sig.pop(k, None)

        costs = calc_bet_costs(bet_amount, fee_percent, bet_mode, 2) if has_bet else {
            "entry": 0, "winner_total": 0, "total_fee": 0, "fee_per": 0, "gross_prize": 0,
        }
        mode_label = "فیکس" if bet_mode == BET_MODE_FIXED else "اضافه"
        INVITES[invite_id] = {
            "id": invite_id,
            "group_id": int(group_id),
            "challenger_id": int(challenger_id),
            "target_id": int(target_id),
            "bet_amount": int(bet_amount),
            "has_bet": bool(has_bet),
            "bet_mode": bet_mode,
            "fee_percent": int(fee_percent),
            "entry": int(costs.get("entry") or 0),
            "winner_amount": int(costs.get("winner_total") or 0),
            "fee_amount": int(costs.get("total_fee") or 0),
            "created_at": time.time(),
            "expires_at": time.time() + INVITE_TTL,
            "status": "pending",
            "challenger_name": challenger_name,
            "target_name": target_name,
            "mode_label": mode_label,
            "challenger_msg_id": None,
            "target_msg_id": None,
            "via_search": bool(via_search),
            "_sig": sig,
        }
        inv = INVITES[invite_id]
        _bind_user(challenger_id, "invite", invite_id)
        if not deliver:
            _bind_user(target_id, "invite", invite_id)
            _persist_pv_state()
            return invite_id

        money_block = _invite_money_block(inv)

        from bot.finance import has_started_bot
        ch_started = await has_started_bot(int(challenger_id))
        tg_started = await has_started_bot(int(target_id))

        if not ch_started or not tg_started:
            fail_text = format_pv_invite_delivery_fail(
                challenger_ok=ch_started,
                target_ok=tg_started,
                challenger_name=challenger_name,
                target_name=target_name,
                challenger_started=ch_started,
                target_started=tg_started,
            )
            await _expire_invite(bot, invite_id, reason="no_pv_delivery")
            if not via_search:
                try:
                    await bot.send_message(
                        group_id, fail_text,
                        reply_to_message_id=group_msg_id,
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            for uid, started in ((challenger_id, ch_started), (target_id, tg_started)):
                if started:
                    try:
                        await send_private(bot, uid, fail_text)
                    except Exception:
                        pass
            return invite_id

        tg_text = (
            "⚔️ چالش تاس پیوی\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"از طرف: {challenger_name}\n"
            f"{money_block}"
            "⚠️ اگر قبول کنید و در مهلت مقرر تاس نزنید، بازنده می‌شوید.\n"
            f"⏳ مهلت پاسخ: {invite_ttl_label()}\n\n"
            "بعد از قبول و شروع بازی، لغو ممکن نیست."
        )
        tg_mid = await _send_invite_pm(
            bot, target_id, tg_text, reply_markup=_invite_target_kb(invite_id),
        )
        tg_ok = bool(tg_mid)
        if tg_ok and tg_mid is not True:
            inv["target_msg_id"] = int(tg_mid)

        ch_text = (
            "📤 دعوت شما ارسال شد\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"حریف: {target_name}\n"
            f"{money_block}"
            f"⏳ مهلت پاسخ حریف: {invite_ttl_label()}\n\n"
            "💡 تا قبل از قبول حریف می‌توانید همین‌جا با دکمه «❌ لغو دعوت» دعوت را لغو کنید."
        )
        ch_mid = await _send_invite_pm(
            bot, challenger_id, ch_text, reply_markup=_invite_challenger_kb(invite_id),
        )
        ch_ok = bool(ch_mid)
        if ch_ok and ch_mid is not True:
            inv["challenger_msg_id"] = int(ch_mid)

        if not ch_ok or not tg_ok:
            fail_text = format_pv_invite_delivery_fail(
                challenger_ok=ch_ok,
                target_ok=tg_ok,
                challenger_name=challenger_name,
                target_name=target_name,
                challenger_started=True,
                target_started=True,
            )
            await _expire_invite(bot, invite_id, reason="no_pv_delivery")
            if not via_search:
                try:
                    await bot.send_message(
                        group_id, fail_text,
                        reply_to_message_id=group_msg_id,
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            for uid, ok in ((challenger_id, ch_ok), (target_id, tg_ok)):
                if ok:
                    try:
                        await send_private(bot, uid, fail_text)
                    except Exception:
                        pass
            if not ch_ok:
                try:
                    await send_private(bot, challenger_id, fail_text)
                except Exception:
                    pass
            return invite_id

        if not via_search:
            group_text = (
                "📨 چالش پیوی ارسال شد\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 از: {challenger_name}\n"
                f"🎯 برای: {target_name}\n"
                f"{money_block}"
                f"⏳ مهلت پاسخ: {invite_ttl_label()}\n\n"
                "ادامه در پیوی ربات پیگیری می‌شود."
            )
            try:
                await bot.send_message(
                    group_id, group_text, reply_to_message_id=group_msg_id, parse_mode="HTML",
                )
            except Exception:
                pass

        _ensure_invite_timer(bot, invite_id)
        return invite_id


async def _invite_timeout(bot: Bot, invite_id: str) -> None:
    try:
        inv = INVITES.get(invite_id)
        if not inv or inv.get("status") != "pending":
            return
        wait = max(0.5, float(inv.get("expires_at") or 0) - time.time() + 0.5)
        await asyncio.sleep(wait)
        inv = INVITES.get(invite_id)
        if not inv or inv.get("status") != "pending":
            return
        await _expire_invite(bot, invite_id, reason="timeout")
    finally:
        _active_invite_timers.discard(invite_id)


async def _expire_invite(bot: Bot, invite_id: str, *, reason: str, _holding_lock: bool = False) -> None:
    async def _body():
        inv = INVITES.get(invite_id)
        if not inv or inv.get("status") != "pending":
            return
        INVITES.pop(invite_id, None)
        _forget_invite_sig(invite_id, inv)
        inv["status"] = "expired"
        _unbind_user(inv["challenger_id"], "invite", invite_id)
        _unbind_user(inv["target_id"], "invite", invite_id)
        _persist_pv_state()
        if reason == "timeout":
            msg = (
                "⌛ دعوت بازی پیوی منقضی شد\n"
                f"حریف در مهلت {invite_ttl_label()} پاسخ نداد.\n"
                "می‌توانید دوباره چالش بفرستید."
            )
        elif reason in ("no_pv_target", "no_pv_delivery"):
            msg = "⚠️ ارسال دعوت پیوی ممکن نشد؛ در گروه راهنما نمایش داده شده است."
        else:
            msg = "ℹ️ دعوت بازی پیوی بسته شد."
        for uid in (inv["challenger_id"], inv["target_id"]):
            try:
                await send_private(bot, uid, msg)
            except Exception:
                pass

    if _holding_lock:
        await _body()
        return
    lock = _accept_locks.setdefault(invite_id, asyncio.Lock())
    async with lock:
        await _body()


async def _cancel_invite(bot: Bot, user_id: int, invite_id: str, *, message=None) -> bool:
    lock = _accept_locks.setdefault(invite_id, asyncio.Lock())
    async with lock:
        from django.core.cache import cache
        if cache.get(f"tg_pv_accept_claim:{invite_id}"):
            await send_private(bot, user_id, "⏳ این دعوت هم‌اکنون در حال قبول شدن است.")
            return True
        inv = INVITES.get(invite_id)
        if not inv or inv.get("status") != "pending":
            await send_private(bot, user_id, "این دعوت دیگر قابل لغو نیست.")
            return True
        if int(user_id) != int(inv["challenger_id"]):
            await send_private(bot, user_id, "فقط فرستنده دعوت می‌تواند لغو کند.")
            return True
        INVITES.pop(invite_id, None)
        inv["status"] = "cancelled"
        _unbind_user(inv["challenger_id"], "invite", invite_id)
        _unbind_user(inv["target_id"], "invite", invite_id)

        ch_text = _cancelled_challenger_text(inv)
        tg_text = _cancelled_target_text(inv)

        ch_edited = False
        if message is not None:
            try:
                await message.edit_text(
                    ch_text, reply_markup=None, parse_mode="HTML",
                )
                ch_edited = True
            except Exception:
                pass
        if not ch_edited:
            ch_edited = await _edit_invite_message(
                bot, inv["challenger_id"], inv.get("challenger_msg_id"), ch_text,
            )
        if not ch_edited:
            await send_private(bot, inv["challenger_id"], ch_text)

        tg_edited = await _edit_invite_message(
            bot, inv["target_id"], inv.get("target_msg_id"), tg_text,
        )
        if not tg_edited:
            await send_private(bot, inv["target_id"], tg_text)
        _persist_pv_state()
        return True


async def _reject_invite(bot: Bot, user_id: int, invite_id: str) -> bool:
    lock = _accept_locks.setdefault(invite_id, asyncio.Lock())
    async with lock:
        from django.core.cache import cache
        if cache.get(f"tg_pv_accept_claim:{invite_id}"):
            await send_private(bot, user_id, "⏳ این دعوت هم‌اکنون در حال قبول شدن است.")
            return True
        inv = INVITES.get(invite_id)
        if not inv or inv.get("status") != "pending":
            await send_private(bot, user_id, "این دعوت دیگر فعال نیست.")
            return True
        if int(user_id) != int(inv["target_id"]):
            return True
        INVITES.pop(invite_id, None)
        inv["status"] = "rejected"
        _unbind_user(inv["challenger_id"], "invite", invite_id)
        _unbind_user(inv["target_id"], "invite", invite_id)
        await send_private(bot, inv["target_id"], "رد کردید — چالش بسته شد.")
        await send_private(
            bot, inv["challenger_id"],
            f"❌ {inv['target_name']} چالش را رد کرد.",
        )
        _persist_pv_state()
        return True


_SPAMMY_PV_ACTIONS = frozenset({"st", "chat", "blk", "rx", "back", "rm", "dbl", "custom", "inf"})


async def handle_callback(call, bot: Bot) -> bool:
    data = call.data or ""
    if data.startswith("pvc:"):
        await call.answer()
        return await _handle_admin_chat_button(bot, call.from_user.id, data)
    if not data.startswith("pvd:"):
        return False
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action in _SPAMMY_PV_ACTIONS:
        from bot.pv_throttle import allow_action, allow_reply, action_bucket
        uid = int(call.from_user.id)
        if not allow_action(uid, action_bucket(data)):
            await call.answer()
            return True
        if not allow_reply(uid):
            await call.answer()
            return True

    await call.answer()

    if action == "can" and len(parts) >= 3:
        return await _cancel_invite(bot, call.from_user.id, parts[2], message=call.message)
    if action == "rej" and len(parts) >= 3:
        return await _reject_invite(bot, call.from_user.id, parts[2])
    if action == "acc" and len(parts) >= 3:
        return await _accept_invite(bot, call.from_user.id, parts[2])
    if action == "inf" and len(parts) >= 3:
        inv = INVITES.get(parts[2])
        if not inv:
            await call.message.answer("این دعوت دیگر فعال نیست.")
            return True
        await call.message.answer(
            f"💳 ورودی: {inv['entry']:,}\n"
            f"🏆 جایزه: {inv['winner_amount']:,}\n"
            f"🎛 حالت: {inv['mode_label']}\n"
            f"⏳ مهلت پاسخ تا پایان دعوت."
        )
        return True
    if action == "roll" and len(parts) >= 3:
        dice_count = 1
        if len(parts) >= 4:
            try:
                dice_count = int(parts[3])
            except ValueError:
                dice_count = 1
        AWAITING_CUSTOM_DICE.pop(int(call.from_user.id), None)
        return await _do_roll(bot, call.from_user.id, parts[2], dice_count)
    if action == "custom" and len(parts) >= 3:
        return await _ask_custom_dice(bot, call.from_user.id, parts[2])
    if action == "st" and len(parts) >= 3:
        return await _send_status(bot, call.from_user.id, parts[2])
    if action == "back" and len(parts) >= 3:
        uid = int(call.from_user.id)
        game = GAMES.get(parts[2]) or get_active_pv_game(uid)
        if not game:
            await send_private(bot, uid, "بازی فعال نیست.")
            return True
        await _remind_in_game(bot, uid, game)
        return True
    if action == "rx" and len(parts) >= 4:
        return await _handle_react(bot, call.from_user.id, parts[2], parts[3])
    if action == "chat" and len(parts) >= 3:
        return await _handle_chat_help(bot, call.from_user.id, parts[2])
    if action == "blk" and len(parts) >= 3:
        return await _handle_chat_block(bot, call.from_user.id, parts[2])
    if action == "rm" and len(parts) >= 3:
        return await _handle_rematch(bot, call.from_user.id, parts[2], double=False)
    if action == "dbl" and len(parts) >= 3:
        return await _handle_rematch(bot, call.from_user.id, parts[2], double=True)
    return True


async def _ask_custom_dice(bot: Bot, user_id: int, game_id: str) -> bool:
    game = GAMES.get(game_id)
    if not game or game.get("status") in ("finished", "cancelled"):
        await send_private(bot, user_id, "این بازی تمام شده است.")
        return True
    uid = int(user_id)
    if uid not in game["players"]:
        return True
    if game.get("status") == "qualifying":
        await send_private(
            bot, uid,
            "برای تاس تعیین فقط «تاس» بفرستید (بدون عدد).\n"
            "می‌توانید دکمه 🎲 تاس را بزنید یا بنویسید: <code>تاس</code>",
        )
        return True
    if game.get("status") != "playing":
        await send_private(bot, uid, "الان نوبت پرتاب تاس نیست.")
        return True
    if game.get("turn") != uid:
        await send_private(bot, uid, "⏳ نوبت شما نیست.")
        return True
    rem = int((game.get("remaining") or {}).get(uid, 0) or 0)
    AWAITING_CUSTOM_DICE[uid] = game_id
    await send_private(
        bot, uid,
        "✏️ تعداد تاس را مثل گروه بنویسید\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"باقی‌مانده راند شما: <b>{rem}</b>\n\n"
        "مثال: <code>تاس 15</code> یا <code>تاس15</code>\n"
        "برای یک تاس: <code>تاس</code>",
    )
    return True


async def _close_conflicting_invites(bot: Bot, *, keep_id: str, user_ids: list[int]) -> None:
    """دعوت‌های دیگر مرتبط با این کاربران را ببند (قبل از شروع بازی)."""
    uids = {int(u) for u in user_ids}
    for iid, inv in list(INVITES.items()):
        if iid == keep_id:
            continue
        if inv.get("status") not in ("pending", "accepting"):
            continue
        if int(inv["challenger_id"]) not in uids and int(inv["target_id"]) not in uids:
            continue
        INVITES.pop(iid, None)
        inv["status"] = "superseded"
        _unbind_user(inv["challenger_id"], "invite", iid)
        _unbind_user(inv["target_id"], "invite", iid)
        try:
            from django.core.cache import cache
            cache.delete(f"tg_pv_accept_claim:{iid}")
            cache.delete(_pair_lock_key(inv.get("group_id"), inv["challenger_id"], inv["target_id"]))
        except Exception:
            pass
        msg = (
            "ℹ️ این دعوت پیوی بسته شد؛\n"
            "یکی از طرفین دعوت/بازی دیگری را ادامه داد."
        )
        for uid in (inv["challenger_id"], inv["target_id"]):
            try:
                await send_private(bot, uid, msg)
            except Exception:
                pass


def _pair_lock_key(group_id, a, b) -> str:
    x, y = sorted([int(a), int(b)])
    return f"tg_pv_pair_accept:{int(group_id)}:{x}:{y}"


def _paid_key(invite_id: str) -> str:
    return f"tg_pv_invite_paid:{str(invite_id).strip()}"


async def _kill_invite(invite_id: str, inv: dict, *, status: str) -> None:
    INVITES.pop(invite_id, None)
    inv["status"] = status
    _forget_invite_sig(invite_id, inv)
    _unbind_user(inv["challenger_id"], "invite", invite_id)
    _unbind_user(inv["target_id"], "invite", invite_id)
    _persist_pv_state()


async def _accept_invite(bot: Bot, user_id: int, invite_id: str) -> bool:
    from django.core.cache import cache

    lock = _accept_locks.setdefault(invite_id, asyncio.Lock())
    async with lock:
        claim_key = f"tg_pv_accept_claim:{invite_id}"
        paid_key = _paid_key(invite_id)
        pair_key = None
        claimed = False
        pair_locked = False

        if not cache.add(claim_key, "1", timeout=180):
            await send_private(bot, user_id, "⏳ این دعوت هم‌اکنون در حال قبول شدن است.")
            return True
        claimed = True

        try:
            inv = INVITES.get(invite_id)
            if not inv or inv.get("status") != "pending":
                await send_private(bot, user_id, "این دعوت منقضی یا بسته شده است.")
                return True
            if int(user_id) != int(inv["target_id"]):
                return True
            if time.time() > float(inv["expires_at"]):
                await _expire_invite(bot, invite_id, reason="timeout", _holding_lock=True)
                return False

            pair_key = _pair_lock_key(inv["group_id"], inv["challenger_id"], inv["target_id"])
            if not cache.add(pair_key, invite_id, timeout=180):
                cur = str(cache.get(pair_key) or "")
                if cur != invite_id:
                    await send_private(
                        bot, user_id,
                        "⏳ برای این دو نفر همین حالا دعوت دیگری در حال قبول است.\n"
                        "صبر کنید تا تمام شود.",
                    )
                    return True
            pair_locked = True

            inv["status"] = "accepting"
            _persist_pv_state()

            # قبل از bind: اگر یکی در بازی/دعوت دیگر است رد کن (bind نباید USER_BUSY را overwrite کند)
            conflict = None
            for uid in (inv["challenger_id"], inv["target_id"]):
                conflict = _busy_conflicts_with_invite(uid, invite_id)
                if conflict:
                    break
            if conflict:
                inv["status"] = "pending"
                _persist_pv_state()
                await send_private(
                    bot, user_id,
                    "⚠️ فعلاً نمی‌توان قبول کرد؛ یکی از طرفین مشغول است:\n"
                    f"{pv_busy_short_title(conflict)}",
                )
                return False

            # قفل هر دو طرف بلافاصله — تا وسط accept گروه/پیوی دیگر شروع نشود
            _bind_user(inv["challenger_id"], "invite", invite_id, force=True)
            _bind_user(inv["target_id"], "invite", invite_id, force=True)

            try:
                from bot.dice_game import is_user_involved_in_any_group_game
                if (
                    is_user_involved_in_any_group_game(inv["challenger_id"])
                    or is_user_involved_in_any_group_game(inv["target_id"])
                ):
                    _unbind_user(inv["challenger_id"], "invite", invite_id)
                    _unbind_user(inv["target_id"], "invite", invite_id)
                    inv["status"] = "pending"
                    _persist_pv_state()
                    await send_private(
                        bot, user_id,
                        "⚠️ یکی از طرفین هنوز درگیر بازی گروهی است "
                        "(عضو بازی یا استارت‌کننده لابی).\n"
                        "اول آن را تمام/لغو کنید، بعد دعوت را قبول کنید.",
                    )
                    return False
            except Exception:
                pass

            await _close_conflicting_invites(
                bot,
                keep_id=invite_id,
                user_ids=[inv["challenger_id"], inv["target_id"]],
            )

            from bot.finance import (
                allocate_game_no,
                charge_pv_invite_bets,
                get_playable_balance,
                refund_pv_invite_bets,
            )

            entry = int(inv["entry"])
            players = [int(inv["challenger_id"]), int(inv["target_id"])]
            game_no = None
            if inv["has_bet"] and entry > 0:
                from bot.finance import spendable_for_games
                for uid in players:
                    _, available, pending = await get_playable_balance(inv["group_id"], uid)
                    if spendable_for_games(available, pending) < entry:
                        name = (
                            inv["challenger_name"]
                            if uid == int(inv["challenger_id"])
                            else inv["target_name"]
                        )
                        msg = (
                            f"⚠️ موجودی کافی نیست\n"
                            f"کاربر {name} موجودی قابل‌استفاده کمتر از {entry:,} دارد.\n"
                            "دعوت لغو شد."
                        )
                        await _kill_invite(invite_id, inv, status="failed_balance")
                        for p in players:
                            await send_private(bot, p, msg)
                        return False

                try:
                    game_no = await allocate_game_no(inv["group_id"])
                    charges = [
                        (int(inv["challenger_id"]), inv["target_name"]),
                        (int(inv["target_id"]), inv["challenger_name"]),
                    ]
                    result = await charge_pv_invite_bets(
                        inv["group_id"],
                        charges,
                        entry,
                        invite_id=invite_id,
                        game_no=game_no,
                        description="ورودی مسابقه پیوی",
                    )
                    if result == "already":
                        print(
                            f"pv accept: invite {invite_id} already charged — continue to create single game"
                        )
                except Exception as e:
                    try:
                        await refund_pv_invite_bets(
                            inv["group_id"], players, entry, invite_id=invite_id,
                        )
                    except Exception:
                        print(f"pv refund after charge fail: {e}")
                    cache.set(paid_key, "failed", timeout=60 * 60 * 24 * 14)
                    await _kill_invite(invite_id, inv, status="failed_charge")
                    await send_private(bot, user_id, f"⚠️ خطا در کسر موجودی: {e}\nدعوت بسته شد.")
                    return False

            # اول ثبت پرداخت موفق، بعد حذف دعوت — تا crash وسط orphan charge نسازد
            if inv["has_bet"] and entry > 0:
                cache.set(paid_key, "done", timeout=60 * 60 * 24 * 14)

            INVITES.pop(invite_id, None)
            inv["status"] = "accepted"
            game_id = uuid.uuid4().hex[:12]
            game = {
                "id": game_id,
                "game_no": game_no,
                "group_id": inv["group_id"],
                "players": players,
                "names": {
                    inv["challenger_id"]: inv["challenger_name"],
                    inv["target_id"]: inv["target_name"],
                },
                "has_bet": inv["has_bet"],
                "bet_amount": inv["bet_amount"],
                "bet_mode": inv["bet_mode"],
                "fee_percent": inv["fee_percent"],
                "entry": entry,
                "winner_amount": inv["winner_amount"],
                "fee_amount": inv["fee_amount"],
                "paid": bool(inv["has_bet"] and entry > 0),
                "invite_id": invite_id,
                "status": "qualifying",
                "qual_rolls": {},
                "totals": {p: 0 for p in players},
                "remaining": {p: 0 for p in players},
                "actions_left": {p: None for p in players},
                "dice_turn_limit": 0,
                "turn": None,
                "round_setter": None,
                "total_rounds": 0,
                "move_deadline": time.time() + MOVE_TTL,
                "warned": False,
                "mode_label": inv["mode_label"],
                "via_search": bool(inv.get("via_search")),
                # لیگ فقط بعد از نتیجه قطعی (برد/باخت) — نه لغو/استرداد
                "league_on_finish": bool(inv["has_bet"] and entry > 0),
                "chat_enabled": await get_pv_chat_enabled(inv["group_id"]),
            }
            social.ensure_game_social(game)
            GAMES[game_id] = game
            await _persist_pv_state_now()
            _bind_user(players[0], "game", game_id, force=True)
            _bind_user(players[1], "game", game_id, force=True)

            start_text = (
                "🎮 مسابقه پیوی شروع شد\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"حریفان: {inv['challenger_name']}  vs  {inv['target_name']}\n"
            )
            if inv["has_bet"]:
                start_text += f"💳 ورودی کسر شد: {entry:,} واحد\n"
            start_text += (
                "\nمرحله ۱: هر دو یک تاس تعیین بزنید.\n"
                "می‌توانید دکمه بزنید یا بنویسید: <code>تاس</code>\n"
                "کسی که تاس بالاتر آورد، تعداد راند را انتخاب می‌کند.\n"
                f"⏱ مهلت هر حرکت: {MOVE_TTL // 60} دقیقه — اگر نزنید بازنده‌اید."
            )
            if _game_chat_on(game):
                start_text += (
                    f"\n\n{social.CHAT_WARN}\n"
                    "💬 هر متنی برای حریف ارسال می‌شود. از دکمه‌های واکنش هم می‌توانید استفاده کنید."
                )
            for uid in players:
                await send_private(
                    bot, uid, start_text, reply_markup=_roll_kb_for(game, for_uid=uid),
                )

            try:
                from bot.challenges import flush_challenge_breaks
                await flush_challenge_breaks(bot, inv["group_id"])
            except Exception:
                logger.exception("league/challenge flush after pv accept failed")

            _ensure_game_watchdog(bot, game_id)
            return True
        finally:
            if claimed:
                try:
                    cache.delete(claim_key)
                except Exception:
                    pass
            if pair_locked and pair_key:
                try:
                    if str(cache.get(pair_key) or "") == invite_id:
                        cache.delete(pair_key)
                except Exception:
                    pass
            _accept_locks.pop(invite_id, None)


async def _move_watchdog(bot: Bot, game_id: str) -> None:
    try:
        while True:
            await asyncio.sleep(5)
            game = GAMES.get(game_id)
            if not game or game.get("status") in ("finished", "cancelled"):
                return
            now = time.time()
            deadline = float(game.get("move_deadline") or 0)
            left = deadline - now
            if left <= MOVE_WARN_AT and not game.get("warned") and left > 0:
                soft = False
                try:
                    soft = await get_pv_soft_timeout(game.get("group_id"))
                except Exception:
                    soft = False
                soft_now = _soft_timeout_applies(game, soft)
                targets: list = []
                if game["status"] == "qualifying":
                    targets = _qual_missing_players(game)
                elif game["status"] == "awaiting_rounds":
                    targets = [game.get("round_setter")]
                elif game["status"] == "playing":
                    turn = game.get("turn")
                    targets = [turn] if turn else list(game["players"])
                warn_text = (
                    "⏰ یک دقیقه تا پایان نوبت شما مانده!\n"
                    "اگر حرکت نکنید بازی لغو می‌شود."
                    if soft_now
                    else
                    "⏰ یک دقیقه تا پایان نوبت شما مانده!\n"
                    "اگر حرکت نکنید بازنده می‌شوید."
                )
                warn_ok = False
                for uid in targets:
                    if not uid:
                        continue
                    try:
                        await send_private(
                            bot, uid,
                            warn_text,
                            reply_markup=(
                                _rounds_prompt_kb(game_id)
                                if game["status"] == "awaiting_rounds"
                                else _roll_kb_for(game)
                            ),
                        )
                        warn_ok = True
                    except Exception:
                        pass
                # فقط بعد از ارسال موفق علامت بزن تا در خطای ارسال دوباره تلاش شود
                if warn_ok or not targets:
                    game["warned"] = True
                    _persist_pv_state()
            if left <= 0:
                await _timeout_forfeit(bot, game_id)
                game = GAMES.get(game_id)
                if not game or game.get("status") in ("finished", "cancelled"):
                    return
                # اگر forfeit زود برگشت (وضعیت نامعتبر)، گیر نکن — ادامه بده
                continue
    finally:
        _active_watchdogs.discard(game_id)


async def _timeout_forfeit(bot: Bot, game_id: str) -> None:
    async with _game_roll_lock(game_id):
        game = GAMES.get(game_id)
        if not game or game.get("status") in ("finished", "cancelled"):
            return
        await _timeout_forfeit_locked(bot, game_id, game)


async def _timeout_forfeit_locked(bot: Bot, game_id: str, game: dict) -> None:
    _norm_player_maps(game)
    soft = False
    try:
        soft = await get_pv_soft_timeout(game.get("group_id"))
    except Exception:
        soft = False
    if _soft_timeout_applies(game, soft):
        paid = bool(game.get("paid"))
        st = game.get("status")
        if st == "qualifying":
            reason = (
                "مهلت تاس تعیین تمام شد؛ بازی لغو"
                + (" و ورودی برمی‌گردد." if paid else " شد.")
            )
        elif st == "awaiting_rounds":
            reason = (
                "مهلت تعیین راند تمام شد؛ بازی لغو"
                + (" و ورودی برمی‌گردد." if paid else " شد.")
            )
        else:
            reason = (
                "مهلت تمام شد قبل از شروع پرتاب تاس بازی؛ بازی لغو"
                + (" و ورودی برمی‌گردد." if paid else " شد.")
            )
        await _cancel_game_refund(bot, game_id, reason)
        return
    loser = None
    if game["status"] == "qualifying":
        missing = _qual_missing_players(game)
        if len(missing) == 1:
            loser = missing[0]
        elif len(missing) == 2:
            # both timed out — cancel refund
            await _cancel_game_refund(bot, game_id, "هر دو بازیکن در مهلت تاس نزدند؛ بازی لغو و ورودی برمی‌گردد." if game.get("paid") else "هر دو بازیکن تاس نزدند؛ بازی لغو شد.")
            return
        else:
            return
    elif game["status"] == "awaiting_rounds":
        loser = game.get("round_setter")
    elif game["status"] == "playing":
        loser = game.get("turn")
        # اگر نوبت خالی بود ولی هنوز راند باقی است، کسی که راند ناتمام دارد بازنده است
        if not loser:
            unfinished = [
                p for p in game["players"]
                if _roll_progress(game, p)[2] > 0
            ]
            if len(unfinished) == 1:
                loser = unfinished[0]
            elif len(unfinished) == 2:
                # هر دو ناتمام — امن‌تر: لغو
                await _cancel_game_refund(
                    bot, game_id,
                    "مهلت تمام شد ولی نوبت مشخص نبود؛ بازی لغو شد."
                    + (" ورودی برمی‌گردد." if game.get("paid") else ""),
                )
                return
    if not loser:
        return
    winner = _other_player(game["players"], loser)
    if winner is None:
        return
    game["timeout_loser"] = int(loser)
    await _finish_game(bot, game_id, winner_id=winner, reason="timeout")


async def _do_roll(bot: Bot, user_id: int, game_id: str, dice_count: int = 1) -> bool:
    """قفل حافظه + Redis تا دابل‌کلیک/چندورکر بیش از سقف راند نریزد."""
    from django.core.cache import cache

    uid = int(user_id)
    redis_key = f"pv_dice_roll_lock:{game_id}:{uid}"
    got = False
    try:
        got = bool(cache.add(redis_key, "1", timeout=12))
    except Exception:
        got = True
    if not got:
        await send_private(bot, uid, "⏳ تاس قبلی در حال ثبت است؛ یک لحظه صبر کنید.")
        return True
    try:
        async with _game_roll_lock(game_id):
            return await _do_roll_unlocked(bot, user_id, game_id, dice_count)
    finally:
        if got:
            try:
                cache.delete(redis_key)
            except Exception:
                pass


async def _do_roll_unlocked(bot: Bot, user_id: int, game_id: str, dice_count: int = 1) -> bool:
    game = GAMES.get(game_id)
    if not game or game.get("status") in ("finished", "cancelled"):
        await send_private(bot, user_id, "این بازی تمام شده است.")
        return True
    uid = int(user_id)
    if uid not in game["players"]:
        return True
    if dice_count < 1:
        await send_private(bot, uid, "❌ تعداد تاس نامعتبر است.")
        return True

    if game["status"] == "qualifying":
        if dice_count != 1:
            await send_private(bot, uid, "⚠️ برای تاس تعیین فقط «تاس» بزنید (بدون عدد).")
            return True
        if _map_get(game.get("qual_rolls"), uid, None) is not None:
            await send_private(bot, uid, "تاس تعیین شما ثبت شد؛ منتظر تاس حریف بمانید.")
            return True
        msg, val = _build_roll_message(game["group_id"], 1)
        val = _clamp_dice_total(1, val)
        _map_set(game.setdefault("qual_rolls", {}), uid, val)
        _norm_player_maps(game)
        game["move_deadline"] = time.time() + MOVE_TTL
        game["warned"] = False
        _persist_pv_state()
        name = game["names"].get(uid, str(uid))
        for p in game["players"]:
            await send_private(bot, p, f"🎲 تاس تعیین {name}:\n{msg}")
        if len(game.get("qual_rolls") or {}) < 2:
            await send_private(bot, uid, "ثبت شد. منتظر تاس حریف…", reply_markup=_roll_kb_for(game))
            return True
        a, b = game["players"]
        ra = int(_map_get(game.get("qual_rolls"), a, 0) or 0)
        rb = int(_map_get(game.get("qual_rolls"), b, 0) or 0)
        if ra == rb:
            game["qual_rolls"] = {}
            game["move_deadline"] = time.time() + MOVE_TTL
            game["warned"] = False
            _persist_pv_state()
            for p in game["players"]:
                await send_private(
                    bot, p,
                    "⚖️ تساوی در تاس تعیین — دوباره هر دو بزنید.",
                    reply_markup=_roll_kb_for(game),
                )
            return True
        setter = a if ra > rb else b
        game["round_setter"] = setter
        game["status"] = "awaiting_rounds"
        game["move_deadline"] = time.time() + MOVE_TTL
        game["warned"] = False
        game["_rounds_prompted"] = True
        _persist_pv_state()
        sname = game["names"].get(setter, str(setter))
        for p in game["players"]:
            if int(p) == int(setter):
                await send_private(
                    bot, p,
                    "🏅 تاس شما بالاتر بود.\n"
                    "تعداد راند مسابقه را بنویسید (مثلاً <code>20</code>).\n"
                    "عدد باید بین ۱ تا یک میلیارد باشد.",
                    reply_markup=_rounds_prompt_kb(game_id),
                )
            else:
                await send_private(bot, p, f"🏅 {sname} تعداد راند را انتخاب می‌کند…")
        return True

    if game["status"] != "playing":
        await send_private(bot, uid, "الان نوبت پرتاب تاس بازی نیست.")
        return True

    _norm_player_maps(game)
    allowed, remaining, err = _can_pv_roll(game, uid, dice_count)
    if not allowed:
        await send_private(bot, uid, err)
        return True

    # رزرو اتمی اسلات تاس قبل از تولید نتیجه (جلوی دابل‌کلیک/دکمه کهنه)
    rem_before = int(_map_get(game.get("remaining"), uid, 0) or 0)
    already = int(_map_get(game.get("dice_rolled"), uid, 0) or 0)
    total_rounds = int(game.get("total_rounds") or 0)
    if dice_count > rem_before or (total_rounds > 0 and already + dice_count > total_rounds):
        await send_private(bot, uid, f"❌ شما فقط {rem_before} راند باقی دارید!")
        return True
    rem_after = rem_before - dice_count
    _map_set(game.setdefault("remaining", {}), uid, rem_after)
    _map_set(game.setdefault("dice_rolled", {}), uid, already + dice_count)
    game["first_roll_done"] = True
    cur_al = _map_get(game.get("actions_left"), uid, None)
    prev_al = cur_al
    if cur_al is not None:
        try:
            _map_set(game.setdefault("actions_left", {}), uid, max(0, int(cur_al) - 1))
        except (TypeError, ValueError):
            prev_al = None
    _persist_pv_state()

    try:
        msg, total = _build_roll_message(
            game["group_id"],
            dice_count,
            skip_consecutive=total_rounds <= 2,
            user_id=uid,
        )
        total = _clamp_dice_total(dice_count, total)
    except Exception:
        _map_set(game.setdefault("remaining", {}), uid, rem_before)
        _map_set(game.setdefault("dice_rolled", {}), uid, already)
        if already <= 0:
            game["first_roll_done"] = False
        if prev_al is not None:
            _map_set(game.setdefault("actions_left", {}), uid, prev_al)
        _persist_pv_state()
        await send_private(bot, uid, "⚠️ خطا در پرتاب تاس؛ دوباره تلاش کنید.")
        return True

    _map_set(
        game.setdefault("totals", {}),
        uid,
        int(_map_get(game.get("totals"), uid, 0)) + int(total),
    )
    game["first_roll_done"] = True
    social.ensure_game_social(game)
    _persist_pv_state()

    rem = int(_map_get(game.get("remaining"), uid, 0))
    total_score = int(_map_get(game.get("totals"), uid, 0))
    other = _other_player(game["players"], uid)
    if other is None:
        return True
    finished = rem <= 0 and _all_players_rolls_done(game)
    msg = _append_progress(msg, rem=rem, total_score=total_score, finished=finished)
    name = game["names"].get(uid, str(uid))
    for p in game["players"]:
        if int(p) == int(uid):
            await send_private(bot, p, msg)
        else:
            await send_private(bot, p, f"👤 {name}\n{msg}")

    if finished:
        my_total = int(_map_get(game.get("totals"), uid, 0))
        other_total = int(_map_get(game.get("totals"), other, 0))
        if my_total == other_total:
            await _finish_tie(bot, game_id)
        else:
            winner = uid if my_total > other_total else other
            await _finish_game(bot, game_id, winner_id=winner, reason="normal")
        return True

    # مثل گروه: نوبت فقط وقتی راندهای این بازیکن تمام شود عوض می‌شود
    if rem <= 0:
        game["turn"] = other if int(_map_get(game.get("remaining"), other, 0)) > 0 else None
        game["move_deadline"] = time.time() + MOVE_TTL
        game["warned"] = False
        if game["turn"] is not None:
            clear_last_dice(game["group_id"])
        _persist_pv_state()
        turn = game["turn"]
        if turn:
            left = max(0, int(float(game.get("move_deadline") or 0) - time.time()))
            await send_private(
                bot, turn,
                "🔁 نوبت شماست!\n"
                f"⏱ مهلت: {left // 60}:{left % 60:02d}\n"
                "🎲 بنویسید <code>تاس</code> یا <code>تاس N</code> یا دکمه بزنید.\n"
                "💬 برای پیام به حریف هر متنی بفرستید.",
                reply_markup=_roll_kb_for(game),
            )
            other_waiting = _other_player(game["players"], turn)
            if other_waiting is not None:
                await send_private(bot, other_waiting, "⏳ نوبت حریف…")
    else:
        game["move_deadline"] = time.time() + MOVE_TTL
        game["warned"] = False
        _persist_pv_state()
        await send_private(
            bot, uid,
            "▶️ ادامه بده — هنوز راند باقی مانده.",
            reply_markup=_roll_kb_for(game),
        )
    return True


async def _select_rounds(bot: Bot, user_id: int, game_id: str, rounds: int) -> bool:
    async with _game_roll_lock(game_id):
        game = GAMES.get(game_id)
        if not game or game.get("status") != "awaiting_rounds":
            return True
        if int(user_id) != int(game.get("round_setter") or 0):
            await send_private(bot, user_id, "فقط برنده تاس تعیین می‌تواند تعداد راند را انتخاب کند.")
            return True
        if not (1 <= rounds <= 1_000_000_000):
            await send_private(bot, user_id, "❌ تعداد راند باید بین ۱ تا یک میلیارد باشد!")
            return True

        turn_limit = _group_turn_limit(game["group_id"])
        game["total_rounds"] = rounds
        game["remaining"] = {p: rounds for p in game["players"]}
        game["totals"] = {p: 0 for p in game["players"]}
        game["dice_rolled"] = {p: 0 for p in game["players"]}
        game["dice_turn_limit"] = turn_limit
        game["actions_left"] = {}
        for p in game["players"]:
            game["actions_left"][p] = min(turn_limit, rounds) if turn_limit > 0 else None
        game["status"] = "playing"

        setter = int(game["round_setter"])
        starter = [p for p in game["players"] if p != setter][0]
        game["turn"] = starter
        game["move_deadline"] = time.time() + MOVE_TTL
        game["warned"] = False
        clear_last_dice(game["group_id"])
        _persist_pv_state()

    limit_line = ""
    if turn_limit > 0:
        limit_line = (
            f"\n📌 محدودیت نوبت تاس: حداکثر {turn_limit}\n"
            f"   می‌توانی زودتر تمام کنی؛ نوبت آخر باید همه باقی‌مانده را بریزی.\n"
        )
    for p in game["players"]:
        await send_private(
            bot, p,
            f"🎲 بازی با {rounds} راند شروع شد!\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 هر بازیکن باید {rounds} بار تاس بزند!"
            f"{limit_line}\n"
            f"🔁 نوبت اول: {game['names'].get(starter, starter)}\n"
            f"🎲 بنویسید <code>تاس</code> یا <code>تاس N</code> یا دکمه بزنید.",
            reply_markup=_roll_kb_for(game) if p == starter else None,
        )
    return True


async def _remind_in_game(bot: Bot, user_id: int, game: dict) -> None:
    """کاربر وسط بازی است — از منوی عادی خارج نشود."""
    uid = int(user_id)
    st = game.get("status")
    gid = game["id"]
    if st == "qualifying":
        if _map_get(game.get("qual_rolls"), uid, None) is not None:
            hint = "تاس تعیین شما ثبت شده — منتظر حریف بمانید."
        else:
            hint = "مرحله تاس تعیین است.\nبنویسید: <code>تاس</code> یا دکمه 🎲 تاس را بزنید."
        kb = _roll_kb_for(game)
    elif st == "awaiting_rounds":
        if uid == int(game.get("round_setter") or 0):
            hint = "تعداد راند را بنویسید (مثلاً <code>20</code>)."
        else:
            hint = "منتظر انتخاب تعداد راند توسط حریف بمانید."
        kb = _rounds_prompt_kb(gid)
    elif st == "playing":
        if game.get("turn") == uid:
            rem = int((game.get("remaining") or {}).get(uid, 0) or 0)
            hint = (
                f"نوبت شماست (باقی: {rem}).\n"
                "بنویسید: <code>تاس</code> یا <code>تاس N</code> یا دکمه بزنید."
            )
            kb = _roll_kb_for(game)
        else:
            hint = "نوبت حریف است — صبر کنید."
            kb = _kb([[IKB(text="📊 وضعیت بازی", callback_data=f"pvd:st:{gid}")]])
    else:
        hint = "بازی پیوی هنوز باز است."
        kb = _kb([[IKB(text="📊 وضعیت بازی", callback_data=f"pvd:st:{gid}")]])
    title = pv_busy_short_title(user_busy_label(uid) or "game")
    await send_private(
        bot, uid,
        f"⏳ شما در حال «{title}» هستید.\n"
        "تا پایان این مرحله از منوی عادی ربات خارج نمی‌شوید.\n\n"
        f"{hint}",
        reply_markup=kb,
    )


async def handle_pv_game_text(message, bot: Bot) -> bool:
    """عدد راند / تاس دلخواه / دستور تاس در پیوی هنگام بازی فعال."""
    uid = int(message.from_user.id)
    game = get_active_pv_game(uid)
    if not game:
        AWAITING_CUSTOM_DICE.pop(uid, None)
        return False
    game_id = game["id"]
    if game.get("status") in ("finished", "cancelled"):
        AWAITING_CUSTOM_DICE.pop(uid, None)
        return False

    text = (message.text or "").strip()
    norm = _normalize_pv_text(text)

    if game.get("status") == "awaiting_rounds":
        n = _parse_rounds_input(text)
        if n is not None:
            if int(game.get("round_setter") or 0) != uid:
                await send_private(bot, uid, "⏳ فقط برنده تاس تعیین می‌تواند تعداد راند را بنویسد.")
                return True
            AWAITING_CUSTOM_DICE.pop(uid, None)
            return await _select_rounds(bot, uid, game_id, n)
        if is_pv_locked_misc_text(text) or _pv_text_is_roll_related(text):
            await _remind_in_game(bot, uid, game)
            return True
        if text and int(game.get("round_setter") or 0) == uid:
            await send_private(
                bot, uid,
                "⚠️ تعداد راند را به‌صورت عدد بنویسید.\n"
                "مثال: <code>20</code> یا <code>۲۰</code>\n"
                "عدد باید بین ۱ تا یک میلیارد باشد.",
                reply_markup=_rounds_prompt_kb(game_id),
            )
            return True

    dice_count, dice_err = parse_group_dice_count(text)
    if dice_err:
        await send_private(bot, uid, dice_err)
        return True
    if dice_count is not None:
        AWAITING_CUSTOM_DICE.pop(uid, None)
        return await _do_roll(bot, uid, game_id, dice_count)

    if re.fullmatch(r"\d{1,10}", norm):
        if AWAITING_CUSTOM_DICE.get(uid) == game_id:
            await send_private(
                bot, uid,
                "برای تاس مثل گروه بنویسید، مثلاً <code>تاس 15</code> یا <code>تاس15</code>.",
            )
            return True
        if game.get("status") == "playing":
            await send_private(
                bot, uid,
                "برای پرتاب تاس فقط <code>تاس</code> یا <code>تاس N</code> (مثل گروه) بنویسید.",
            )
            return True
        if game.get("status") == "qualifying":
            await send_private(
                bot, uid,
                "مرحله تاس تعیین است.\nفقط بنویسید: <code>تاس</code> یا دکمه 🎲 را بزنید.",
            )
            return True

    if _pv_text_is_roll_related(text):
        await _remind_in_game(bot, uid, game)
        return True

    # دستورات متفرقه/منو: اجرا نشوند و به حریف هم فوروارد نشوند
    if is_pv_locked_misc_text(text):
        await _remind_in_game(bot, uid, game)
        return True

    if text and game.get("status") in ("qualifying", "awaiting_rounds", "playing"):
        return await _relay_game_chat(bot, uid, game, text)

    # هر پیام دیگر وسط بازی: داخل بازی بمان، منوی عادی نیاید
    await _remind_in_game(bot, uid, game)
    return True


async def _handle_react(bot: Bot, uid: int, game_id: str, idx: str) -> bool:
    game = GAMES.get(game_id)
    if not game or int(uid) not in [int(p) for p in game["players"]]:
        await send_private(bot, uid, "بازی فعال نیست.")
        return True
    if not _game_chat_on(game):
        await send_private(bot, uid, "🌙 چت پیوی برای این گروه خاموش است.")
        return True
    try:
        i = int(idx)
        emoji, title = social.QUICK_REACTS[i]
    except Exception:
        await send_private(bot, uid, "واکنش نامعتبر.")
        return True
    other = [p for p in game["players"] if int(p) != int(uid)][0]
    if social.is_chat_blocked_by(game, other):
        await send_private(bot, uid, "🔇 حریف چت را بلاک کرده؛ واکنش ارسال نمی‌شود.")
        return True
    left = social.chat_cooldown_left(game, uid)
    if left > 0:
        await send_private(bot, uid, f"⏳ برای جلوگیری از اسپم، {left} ثانیه صبر کنید.")
        return True
    label = f"{emoji} {title}"
    entry = social.append_chat(game, uid, label, kind="react")
    social.mark_chat_activity(game, uid)
    _persist_pv_state()
    await send_private(bot, other, social.format_chat_relay(entry))
    await send_private(bot, uid, f"✅ واکنش ارسال شد: {label}")
    return True


async def _handle_chat_help(bot: Bot, uid: int, game_id: str) -> bool:
    game = GAMES.get(game_id)
    if not game or int(uid) not in [int(p) for p in game["players"]]:
        await send_private(bot, uid, "بازی فعال نیست.")
        return True
    if not _game_chat_on(game):
        await send_private(bot, uid, "🌙 چت پیوی برای این گروه خاموش است.")
        return True
    msg = (
        "💬 چت داخل بازی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{social.CHAT_WARN}\n\n"
        "هر متنی (غیر از دستور تاس/عدد راند) برای حریف ارسال می‌شود.\n"
        "از دکمه‌های واکنش سریع هم می‌توانید استفاده کنید.\n"
        f"⏱ بین هر پیام/واکنش حداقل {social.CHAT_COOLDOWN_SEC} ثانیه فاصله لازم است.\n"
        "🔇 با «بلاک چت» فقط یک‌بار در هر بازی می‌توانید پیام‌های حریف را قطع/وصل کنید."
    )
    social.mark_chat_warned(game, uid)
    _persist_pv_state()
    await send_private(bot, uid, msg, reply_markup=_roll_kb_for(game, for_uid=uid))
    return True


async def _handle_chat_block(bot: Bot, uid: int, game_id: str) -> bool:
    game = GAMES.get(game_id)
    if not game or int(uid) not in [int(p) for p in game["players"]]:
        await send_private(bot, uid, "بازی فعال نیست.")
        return True
    if not _game_chat_on(game):
        await send_private(bot, uid, "🌙 چت پیوی برای این گروه خاموش است.")
        return True
    status, blocked = social.try_chat_block_once(game, uid)
    _persist_pv_state()
    if status == "already_used":
        await send_private(
            bot, uid,
            "⚠️ در هر بازی فقط یک‌بار می‌توانید بلاک/آنبلاک کنید.",
            reply_markup=_roll_kb_for(game, for_uid=uid),
        )
        return True
    other = [p for p in game["players"] if int(p) != int(uid)][0]
    if blocked:
        await send_private(
            bot, uid,
            "🔇 چت بلاک شد.\nاز این لحظه پیام و واکنش حریف به شما نمی‌رسد.\n"
            "⚠️ دیگر نمی‌توانید در این بازی بلاک را عوض کنید.",
            reply_markup=_roll_kb_for(game, for_uid=uid),
        )
        await send_private(bot, other, "🔇 حریف چت را بلاک کرد؛ پیام/واکنش شما به او نمی‌رسد.")
    else:
        await send_private(
            bot, uid,
            "🔊 بلاک چت برداشته شد. دوباره پیام حریف را دریافت می‌کنید.\n"
            "⚠️ دیگر نمی‌توانید در این بازی بلاک را عوض کنید.",
            reply_markup=_roll_kb_for(game, for_uid=uid),
        )
        await send_private(bot, other, "🔊 حریف بلاک چت را برداشت.")
    return True


async def _handle_rematch(bot: Bot, uid: int, token: str, *, double: bool) -> bool:
    data = social.REMATCH.get(token)
    if not data or time.time() > float(data.get("expires_at") or 0):
        social.REMATCH.pop(token, None)
        await send_private(bot, uid, "⏳ این درخواست بازی مجدد منقضی شده است.")
        return True
    players = [int(p) for p in (data.get("players") or [])]
    if int(uid) not in players:
        await send_private(bot, uid, "این ریمچ برای شما نیست.")
        return True
    other = [p for p in players if p != int(uid)][0]
    bet = int(data.get("bet_amount") or 0)
    use_double = bool(double or data.get("double"))
    if double and not data.get("double") and bet > 0:
        bet *= 2
    has_bet = bool((data.get("has_bet") or use_double) and bet > 0)
    names = data.get("names") or {}
    group_id = int(data["group_id"])

    def _nm(who) -> str:
        return str(names.get(str(who)) or names.get(who) or who)

    # همان چک‌های «شروع ۲ ۱۰۰ پیوی» قبل از ساخت دعوت
    my_busy = user_busy_label(uid)
    if my_busy:
        await send_private(bot, uid, format_pv_busy_message(my_busy, user_id=uid))
        return True
    their_busy = user_busy_label(other)
    if their_busy:
        await send_private(
            bot, uid,
            format_pv_busy_message(
                their_busy, for_other=True, other_name=_nm(other), user_id=other,
            ),
        )
        return True
    try:
        from bot.dice_game import is_user_involved_in_group_game
        if is_user_involved_in_group_game(group_id, uid):
            await send_private(bot, uid, "⚠️ شما در بازی گروهی این گپ هستید؛ اول آن را تمام کنید.")
            return True
        if is_user_involved_in_group_game(group_id, other):
            await send_private(bot, uid, "⏳ حریف در بازی گروهی است؛ منتظر پایان باشید.")
            return True
    except Exception:
        pass
    try:
        cfg = await get_pv_start_settings(group_id)
        if not cfg.get("enabled"):
            await send_private(bot, uid, format_off_message(cfg.get("reason") or ""))
            return True
    except Exception:
        pass
    if not has_bet:
        try:
            group_min = await get_min_pv_bet(group_id)
            if int(group_min or 0) > 0:
                eff = effective_min_pv_bet(group_min)
                await send_private(bot, uid, format_min_pv_free_denial(eff))
                return True
        except Exception:
            pass
    if has_bet:
        try:
            group_min = await get_min_pv_bet(group_id)
            eff = effective_min_pv_bet(group_min)
            if bet < eff:
                await send_private(bot, uid, format_min_pv_denial(eff, bet))
                return True
        except Exception:
            pass
        try:
            from bot.finance import get_playable_balance, format_insufficient_balance_message, spendable_for_games
            costs = calc_bet_costs(
                bet, int(data.get("fee_percent") or 0),
                data.get("bet_mode") or BET_MODE_FIXED, 2,
            )
            entry = int(costs.get("entry") or 0)
            for who in (int(uid), int(other)):
                _total, playable, pending = await get_playable_balance(group_id, who)
                if spendable_for_games(playable, pending) >= entry:
                    continue
                if who == int(uid):
                    await send_private(
                        bot, uid,
                        format_insufficient_balance_message(
                            entry_cost=entry,
                            total_balance=_total,
                            playable=playable,
                            pending=pending,
                        ),
                    )
                else:
                    await send_private(
                        bot, uid,
                        f"❌ موجودی حریف کافی نیست (قابل‌استفاده: {playable:,} / ورودی: {entry:,}).",
                    )
                return True
        except Exception as e:
            print(f"rematch balance check failed: {e}")

    try:
        invite_id = await create_invite(
            bot,
            group_id=group_id,
            challenger_id=int(uid),
            target_id=int(other),
            bet_amount=bet,
            has_bet=has_bet,
            bet_mode=data.get("bet_mode") or BET_MODE_FIXED,
            fee_percent=int(data.get("fee_percent") or 0),
            group_msg_id=None,
            challenger_name=_nm(uid),
            target_name=_nm(other),
            via_search=bool(data.get("via_search")),
        )
        if invite_id not in INVITES:
            await send_private(
                bot, uid,
                "⚠️ دعوت بازی مجدد ساخته نشد.\n"
                "هر دو نفر باید ربات را در پیوی /start کرده باشند و بلاک نباشد.",
            )
            return True
        social.REMATCH.pop(token, None)
        social.persist_social()
        label = "دبل مبلغ بازی" if use_double else "بازی مجدد"
        await send_private(
            bot, uid,
            f"✅ دعوت {label} ارسال شد.\n"
            f"⏳ مهلت پاسخ: {invite_ttl_label()}",
        )
    except Exception as e:
        print(f"rematch failed: {e}")
        await send_private(bot, uid, f"⚠️ ساخت دعوت مجدد ناموفق بود: {e}")
    return True


async def _relay_game_chat(bot: Bot, uid: int, game: dict, text: str) -> bool:
    from bot.pv_throttle import allow_action, allow_reply

    social.ensure_game_social(game)
    if not _game_chat_on(game):
        await _remind_in_game(bot, uid, game)
        return True
    if not allow_action(uid, "chat_text") or not allow_reply(uid):
        return True
    other = [p for p in game["players"] if int(p) != int(uid)][0]
    if social.is_chat_blocked_by(game, other):
        await send_private(bot, uid, "🔇 حریف چت را بلاک کرده؛ پیام ارسال نمی‌شود.")
        return True
    left = social.chat_cooldown_left(game, uid)
    if left > 0:
        await send_private(bot, uid, f"⏳ برای جلوگیری از اسپم، {left} ثانیه صبر کنید.")
        return True
    if social.needs_chat_warning(game, uid):
        await send_private(bot, uid, social.CHAT_WARN)
        social.mark_chat_warned(game, uid)
    entry = social.append_chat(game, uid, text, kind="text")
    social.mark_chat_activity(game, uid)
    _persist_pv_state()
    await send_private(bot, other, social.format_chat_relay(entry))
    await send_private(bot, uid, social.format_chat_relay(entry, to_self=True))
    return True


def _status_phase_fa(status: str) -> str:
    return {
        "qualifying": "تاس تعیین",
        "awaiting_rounds": "انتخاب تعداد راند",
        "playing": "در حال انجام",
        "finished": "پایان‌یافته",
        "cancelled": "لغو شده",
    }.get(status or "", status or "نامشخص")


def _fmt_move_deadline_left(game: dict) -> str:
    left = max(0, int(float(game.get("move_deadline") or 0) - time.time()))
    m, s = divmod(left, 60)
    if m and s:
        return f"{m} دقیقه و {s} ثانیه"
    if m:
        return f"{m} دقیقه"
    return f"{s} ثانیه"


def format_pv_game_status(game: dict, *, html: bool = False) -> str:
    """متن تمیز و فارسی وضعیت مسابقه پیوی."""
    def _b(t: str) -> str:
        return f"<b>{t}</b>" if html else t

    st = game.get("status") or ""
    names = game.get("names") or {}
    players = list(game.get("players") or [])
    lines = [
        "📊 وضعیت مسابقه پیوی",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📌 مرحله: {_b(_status_phase_fa(st))}",
    ]

    if st == "qualifying":
        lines.append("")
        lines.append("🎲 تاس تعیین")
        qual = game.get("qual_rolls") or {}
        for p in players:
            nm = names.get(p, p)
            rolled = qual.get(p)
            if rolled is None:
                try:
                    rolled = qual.get(int(p))
                except Exception:
                    rolled = None
            if rolled is None:
                rolled = qual.get(str(p))
            if rolled is not None:
                lines.append(f"• {nm} — زده ✅  ({rolled})")
            else:
                lines.append(f"• {nm} — منتظر ⏳")

    elif st == "awaiting_rounds":
        setter = game.get("round_setter")
        setter_name = names.get(setter, setter) if setter else "—"
        lines.append("")
        lines.append(f"👤 انتخاب‌کننده راند: {_b(str(setter_name))}")
        lines.append("⏳ منتظر وارد کردن تعداد راند…")

    elif st == "playing":
        turn = game.get("turn")
        turn_name = names.get(turn, turn) if turn else "—"
        rounds = int(game.get("total_rounds") or 0)
        lines.append("")
        lines.append(f"🔁 نوبت: {_b(str(turn_name))}")
        if rounds:
            lines.append(f"🎯 تعداد راند: {rounds}")
        lines.append("")
        lines.append("👥 بازیکنان")
        for p in players:
            nm = names.get(p, p)
            total = int((game.get("totals") or {}).get(p, 0) or 0)
            rem = int((game.get("remaining") or {}).get(p, 0) or 0)
            mark = "◀" if turn is not None and p == turn else "•"
            lines.append(f"{mark} {_b(str(nm))}")
            lines.append(f"   مجموع: {total:,}   |   باقی‌مانده: {rem}")

    else:
        lines.append("")
        for p in players:
            nm = names.get(p, p)
            total = int((game.get("totals") or {}).get(p, 0) or 0)
            lines.append(f"• {nm} — مجموع {total:,}")

    if game.get("has_bet"):
        entry = int(game.get("entry") or 0)
        prize = int(game.get("winner_amount") or 0)
        lines.append("")
        lines.append("💳 مبلغ بازی")
        lines.append(f"ورودی هر نفر: {entry:,}")
        lines.append(f"🏆 جایزه برنده: {prize:,}")

    if st in ("qualifying", "awaiting_rounds", "playing"):
        lines.append("")
        lines.append(f"⏱ مهلت این حرکت: {_fmt_move_deadline_left(game)}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


async def _send_status(bot: Bot, user_id: int, game_id: str) -> bool:
    game = GAMES.get(game_id)
    if not game:
        await send_private(bot, user_id, "بازی پیدا نشد.")
        return True
    await send_private(bot, user_id, format_pv_game_status(game, html=True))
    return True


async def _cancel_game_refund(bot: Bot, game_id: str, message: str) -> None:
    import html as _html

    game = GAMES.pop(game_id, None)
    if not game:
        return
    game["status"] = "cancelled"
    for p in game["players"]:
        _unbind_user(p, "game", game_id)

    paid = bool(game.get("paid") and game.get("entry"))
    entry = int(game.get("entry") or 0) if paid else 0
    game_no = game.get("game_no")
    invite_id = game.get("invite_id")
    logger.info(
        "pv cancel refund game=%s game_no=%s group=%s players=%s entry=%s paid=%s msg=%s",
        game_id, game_no, game.get("group_id"), game.get("players"), entry, paid, (message or "")[:120],
    )

    if paid and entry > 0:
        from bot.finance import increase_wallet, with_game_id
        names = game.get("names") or {}
        for p in game["players"]:
            other = _other_player(game["players"], p)
            opp_name = ""
            if other is not None:
                try:
                    opp_name = names.get(int(other), "") or names.get(other, "")
                except (TypeError, ValueError):
                    opp_name = names.get(other, "")
            desc = with_game_id(
                "بازگشت ورودی بازی پیوی (لغو)",
                game_no,
                opponent_name=str(opp_name or ""),
                invite_id=invite_id,
            )
            try:
                await increase_wallet(game["group_id"], p, entry, description=desc)
            except Exception:
                logger.exception(
                    "pv cancel refund failed game=%s game_no=%s user=%s entry=%s",
                    game_id, game_no, p, entry,
                )
        if not game.get("league_on_finish"):
            try:
                @sync_to_async
                def _undo_league():
                    from bot.league import undo_league_wager_silent
                    for p in game["players"]:
                        undo_league_wager_silent(game["group_id"], p, entry)

                await _undo_league()
            except Exception:
                logger.exception("pv cancel league undo failed game=%s", game_id)
    for p in game["players"]:
        await send_private(bot, p, message)
    try:
        group_id = int(game["group_id"])
        names = game.get("names") or {}
        players = list(game.get("players") or [])
        a = players[0] if players else None
        b = players[1] if len(players) > 1 else None
        na = _html.escape(str(names.get(a, a) if a is not None else "?"))
        nb = _html.escape(str(names.get(b, b) if b is not None else "?"))
        group_msg = f"⛔ مسابقه پیوی {na} و {nb} لغو شد.\n{_html.escape(message)}"
        if game_no is not None:
            group_msg += f"\n🆔 آیدی بازی: {game_no}"
        await bot.send_message(group_id, group_msg, parse_mode="HTML")
    except Exception as e:
        logger.exception("pv dice cancel group announce failed: %s", e)
    await _persist_pv_state_now()


def _pv_result_rows(game: dict, *, winner_id=None) -> list[tuple]:
    """[(uid, total, rolled, rounds), ...] — برنده واقعی اول، بعد مجموع."""
    rows = []
    for p in game["players"]:
        total = int(_map_get(game.get("totals"), p, 0) or 0)
        rolled, rounds, _rem = _roll_progress(game, p)
        tracked = int(_map_get(game.get("dice_rolled"), p, 0) or 0)
        if tracked > 0:
            rolled = tracked
        rows.append((p, total, rolled, rounds))

    def _key(row):
        uid, total, _c, _r = row
        win_rank = 0
        if winner_id is not None:
            try:
                win_rank = 0 if int(uid) == int(winner_id) else 1
            except (TypeError, ValueError):
                win_rank = 1
        return (win_rank, -int(total))

    rows.sort(key=_key)
    return rows


def _build_pv_end_text(
    game: dict,
    *,
    winner_id,
    is_tie: bool,
    reason: str,
    name_fn,
) -> str:
    """فرمت دقیقاً مثل اعلام نتیجه گروه."""
    results = _pv_result_rows(game, winner_id=None if is_tie else winner_id)
    lines: list[str] = []
    if winner_id and not is_tie:
        lines.append("🏁 مسابقه تاس در پیوی تمام شد")
        lines.append(f"🏆 برنده: {name_fn(winner_id)} 🥇")
        if reason == "timeout":
            loser = game.get("timeout_loser")
            if loser is None:
                loser = _other_player(game.get("players") or [], winner_id)
            if loser is not None:
                rolled, rounds, rem = _roll_progress(game, loser)
                lines.append(
                    f"⏱ {name_fn(loser)} در مهلت مقرر تاس نریخت و باخت."
                )
                if rounds > 0 and rem > 0:
                    lines.append(
                        f"📌 تاس‌های ناتمام بازنده: {rolled} از {rounds}"
                        f" ({rem} راند باقی مانده بود)"
                    )
            else:
                lines.append("⏱ به‌خاطر اتمام زمان نوبت.")
    else:
        lines.append("🏁 مسابقه تاس در پیوی به پایان رسید!")
        if is_tie:
            lines.append("⚠️ بازی با تساوی به پایان رسید")
            if game.get("paid"):
                lines.append("💰 ورودی‌ها برگردانده شد.")
                lines.append("💸 حق واسطه گرفته نشد.")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("🏆 نتایج نهایی")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    for i, (uid, total, rolled, rounds) in enumerate(results, start=1):
        display = name_fn(uid)
        is_winner = False
        if winner_id and not is_tie:
            try:
                is_winner = int(uid) == int(winner_id)
            except (TypeError, ValueError):
                is_winner = False
        if is_tie:
            medal = "⭐"
        elif is_winner:
            medal = "🥇"
        else:
            medal = "📌"
        count = rolled if rolled > 0 else (1 if total > 0 else 0)
        avg = _avg_per_die(total, count)
        dice_line = f"   🎲 تاس: {rolled}"
        if rounds > 0:
            dice_line = f"   🎲 تاس: {rolled} از {rounds}"
            if rolled < rounds:
                dice_line += " ⚠️ ناتمام"
        lines.append(f"{medal} {i:02}. {display}")
        lines.append(f"   📊 مجموع: {total}")
        lines.append(dice_line)
        lines.append(f"   📈 میانگین: {avg:.1f}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")

    if game.get("paid") and not is_tie and winner_id:
        entry = int(game.get("entry") or 0)
        winner_amount = int(game.get("winner_amount") or 0)
        fee_amount = int(game.get("fee_amount") or 0)
        fee_percent = int(game.get("fee_percent") or 0)
        mode_label = game.get("mode_label") or ""
        bet_mode = game.get("bet_mode") or BET_MODE_FIXED
        lines.append("")
        lines.append("💰 جایزه نقدی")
        lines.append("────────────────────")
        lines.append(f"💳 هزینه ورودی هر نفر: {entry:,} واحد")
        if fee_percent > 0:
            if bet_mode == BET_MODE_FIXED or mode_label == "فیکس":
                lines.append(f"💸 حق واسطه ({fee_percent}% از مجموع برد): {fee_amount:,} واحد")
            else:
                lines.append(f"💸 حق واسطه ({fee_percent}% اضافه): {fee_amount:,} واحد")
        lines.append(f"🏆 مبلغ برد: {winner_amount:,} واحد")
        lines.append("")
        lines.append("📊 تغییرات موجودی:")
        for uid in game["players"]:
            display = name_fn(uid)
            if int(uid) == int(winner_id):
                lines.append(f"   ✅ {display}: +{winner_amount:,} واحد")
            else:
                lines.append(f"   ❌ {display}: -{entry:,} واحد")

    return "\n".join(lines)


def _pv_member_offer_kb(token: str) -> InlineKeyboardMarkup:
    return _kb([[IKB(text="افزایش موجودی", callback_data=f"incme:{token}")]])


_MEMBER_OFFER: dict[str, dict] = {}


def _store_member_offer(group_id: int, user_id: int) -> str:
    import uuid
    tok = uuid.uuid4().hex[:10]
    _MEMBER_OFFER[tok] = {"group_id": int(group_id), "user_id": int(user_id)}
    if len(_MEMBER_OFFER) > 400:
        for k in list(_MEMBER_OFFER)[:100]:
            _MEMBER_OFFER.pop(k, None)
    return tok


def resolve_member_offer(token: str) -> dict | None:
    return _MEMBER_OFFER.get(str(token or "").strip())


def format_post_game_balance_offer(
    *, playable: int, pending: int = 0, previous: int | None = None,
) -> str:
    lines = [
        "💳 موجودی پس از بازی",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if previous is not None:
        lines.append(f"📉 موجودی قبلی: {int(previous):,} واحد")
    lines.append(f"📊 موجودی قابل‌استفاده شما: {int(playable):,} واحد")
    if int(pending or 0) > 0:
        lines.append(f"⏳ در انتظار تسویه: {int(pending):,} واحد")
    lines.extend([
        "",
        "اگر می‌خواهید حسابتان را شارژ کنید، روی دکمه زیر بزنید و مبلغ را بفرستید.",
        "درخواست برای مدیران همین گروه ارسال می‌شود.",
    ])
    return "\n".join(lines)


async def _announce_pv_end(
    bot: Bot,
    game: dict,
    *,
    winner_id=None,
    is_tie: bool = False,
    reason: str = "normal",
) -> None:
    """نتیجه فقط برای ۲ بازیکن (پیوی) + گروه — نه برای ادمین/مالک خارج از بازی."""
    import html as _html
    from bot.dice_game import _bulk_mentions
    from bot.finance import get_playable_balance

    players = list(game.get("players") or [])
    group_id = int(game["group_id"])

    def pv_name(uid):
        raw = game.get("names", {}).get(uid) or game.get("names", {}).get(int(uid)) or str(uid)
        return _html.escape(str(raw))

    pv_text = _build_pv_end_text(
        game, winner_id=winner_id, is_tie=is_tie, reason=reason, name_fn=pv_name,
    )
    pv_text = social.enrich_end_text(pv_text, game, winner_id=winner_id, is_tie=is_tie)
    social.archive_game_chat(game, winner_id=winner_id, is_tie=is_tie)

    for p in players:
        rows = []
        tok = social.create_rematch_token(game, requester_id=p)
        rows.append([IKB(text="🔁 بازی مجدد", callback_data=f"pvd:rm:{tok}")])
        if game.get("has_bet") and int(game.get("bet_amount") or 0) > 0:
            dtok = social.create_double_token(game, requester_id=p)
            rows.append([IKB(text="💥 دبل مبلغ بازی (×۲)", callback_data=f"pvd:dbl:{dtok}")])
        await send_private(bot, p, pv_text, reply_markup=_kb(rows) if rows else None)

    try:
        mention_map = await asyncio.wait_for(
            _bulk_mentions(players, bot, group_id), timeout=8,
        )
    except Exception:
        mention_map = {}

    def group_name(uid):
        return mention_map.get(uid) or mention_map.get(int(uid)) or (
            f'<a href="tg://user?id={int(uid)}">{int(uid)}</a>'
        )

    group_text = _build_pv_end_text(
        game, winner_id=winner_id, is_tie=is_tie, reason=reason, name_fn=group_name,
    )

    via_search = bool(game.get("via_search"))
    try:
        results_chat = await get_pv_results_chat_id(group_id)
    except Exception:
        results_chat = None
    results_dest = int(results_chat) if results_chat else None

    # اگر گپ اعلام نتایج تنظیم شده و بازی از جستجوی پیوی است → فقط همان گپ
    # اگر بازی با ریپلای گروه است → گپ اصلی + (در صورت تنظیم) گپ اعلام نتایج
    announce_origin = not (via_search and results_dest is not None)
    if announce_origin:
        try:
            await bot.send_message(group_id, group_text, parse_mode="HTML")
        except Exception as e:
            print(f"pv dice group announce failed: {e}")

    if results_dest is not None:
        try:
            if results_dest != int(group_id) or not announce_origin:
                await bot.send_message(results_dest, group_text, parse_mode="HTML")
            id_lines = [
                "🆔 شناسه بازیکنان",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            for i, p in enumerate(players, 1):
                pname = pv_name(p)
                id_lines.append(f"👤 بازیکن {i}: {pname}")
                id_lines.append(f"🆔 <code>{int(p)}</code>")
            id_kb = InlineKeyboardMarkup(inline_keyboard=[
                [IKB(text=f"👤 مدیریت {int(p)}", callback_data=f"ua:open:{group_id}:{int(p)}")]
                for p in players
            ])
            await bot.send_message(
                results_dest, "\n".join(id_lines), parse_mode="HTML", reply_markup=id_kb,
            )
        except Exception as e:
            print(f"pv dice results-chat announce failed: {e}")

    entry = int(game.get("entry") or 0) if game.get("paid") else 0
    win_amt = int(game.get("winner_amount") or 0) if game.get("paid") else 0
    for p in players:
        try:
            _total, playable, pending = await get_playable_balance(group_id, int(p))
        except Exception:
            playable, pending = 0, 0
        previous = int(playable)
        if entry > 0:
            if is_tie:
                previous = int(playable)
            elif winner_id is not None and int(p) == int(winner_id):
                previous = int(playable) - win_amt + entry
            else:
                previous = int(playable) + entry
        tok = _store_member_offer(group_id, int(p))
        await send_private(
            bot, p,
            format_post_game_balance_offer(
                playable=playable, pending=pending, previous=previous,
            ),
            reply_markup=_pv_member_offer_kb(tok),
        )


async def _finish_tie(bot: Bot, game_id: str) -> None:
    game = GAMES.pop(game_id, None)
    if not game:
        return
    game["status"] = "finished"
    for p in game["players"]:
        _unbind_user(p, "game", game_id)

    game_no = game.get("game_no")
    invite_id = game.get("invite_id")
    logger.info(
        "pv finish tie game=%s game_no=%s group=%s players=%s paid=%s entry=%s",
        game_id, game_no, game.get("group_id"), game.get("players"),
        game.get("paid"), game.get("entry"),
    )

    if game.get("paid") and game.get("entry"):
        from bot.finance import increase_wallet, with_game_id
        entry = int(game.get("entry") or 0)
        names = game.get("names") or {}
        for p in game["players"]:
            other = _other_player(game["players"], p)
            opp_name = ""
            if other is not None:
                try:
                    opp_name = names.get(int(other), "") or names.get(other, "")
                except (TypeError, ValueError):
                    opp_name = names.get(other, "")
            desc = with_game_id(
                "بازگشت ورودی بازی پیوی (تساوی)",
                game_no,
                opponent_name=str(opp_name or ""),
                invite_id=invite_id,
            )
            try:
                await increase_wallet(game["group_id"], p, entry, description=desc)
            except Exception:
                logger.exception(
                    "pv tie refund failed game=%s game_no=%s user=%s entry=%s",
                    game_id, game_no, p, entry,
                )
        try:
            @sync_to_async
            def _undo_league():
                from bot.league import undo_league_wager_silent
                for p in game["players"]:
                    undo_league_wager_silent(game["group_id"], p, entry)

            if not game.get("league_on_finish"):
                await _undo_league()
        except Exception:
            logger.exception("pv tie league undo failed game=%s", game_id)

    await _announce_pv_end(bot, game, is_tie=True, reason="tie")

    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _hist():
            from account.models import DiceGameHistory
            session = f"pv_{game_id}"
            for p in game["players"]:
                total = int(_map_get(game.get("totals"), p, 0) or 0)
                rolled, rounds, _rem = _roll_progress(game, p)
                tracked = int(_map_get(game.get("dice_rolled"), p, 0) or 0)
                count = tracked if tracked > 0 else (rolled if rolled > 0 else (rounds or 1))
                DiceGameHistory.objects.create(
                    telegram_chat_id=game["group_id"],
                    telegram_user_id=int(p),
                    total=int(total),
                    average=_avg_per_die(total, count),
                    count=int(count),
                    winner=False,
                    amount_won=0,
                    bet_amount=int(game.get("entry") or 0) if game.get("paid") else 0,
                    game_session=session,
                )
        await _hist()
    except Exception as e:
        print(f"pv dice tie history: {e}")
    await _persist_pv_state_now()


async def _finish_game(bot: Bot, game_id: str, *, winner_id: int, reason: str) -> None:
    game = GAMES.pop(game_id, None)
    if not game:
        return
    game["status"] = "finished"
    for p in game["players"]:
        _unbind_user(p, "game", game_id)

    winner_id = int(winner_id)
    _norm_player_maps(game)
    # اگر پایان «عادی» ولی راندها کامل نیست → در واقع تایم‌اوت/ناتمام بوده
    if reason == "normal" and not _all_players_rolls_done(game):
        reason = "timeout"
        unfinished = [p for p in game["players"] if _roll_progress(game, p)[2] > 0]
        if len(unfinished) == 1:
            game["timeout_loser"] = int(unfinished[0])
            winner_id = int(_other_player(game["players"], unfinished[0]) or winner_id)
        elif not game.get("timeout_loser"):
            other = _other_player(game["players"], winner_id)
            if other is not None:
                game["timeout_loser"] = int(other)

    logger.info(
        "pv finish game=%s game_no=%s winner=%s reason=%s paid=%s entry=%s win_amt=%s",
        game_id, game.get("game_no"), winner_id, reason,
        game.get("paid"), game.get("entry"), game.get("winner_amount"),
    )

    if game.get("paid") and game.get("winner_amount"):
        from bot.finance import record_game_win, record_fee_income, with_game_id
        from bot.admin_accounting import active_cashier
        from bot.cache_manager import is_owner
        game_no = game.get("game_no")
        try:
            await record_game_win(
                game["group_id"], winner_id, int(game["winner_amount"]),
                description="برد مسابقه پیوی",
                game_no=game_no,
                opponent_name=next(
                    (
                        game["names"].get(p, str(p))
                        for p in game["players"]
                        if int(p) != int(winner_id)
                    ),
                    None,
                ),
            )
            logger.info(
                "pv win credited game=%s game_no=%s winner=%s amount=%s",
                game_id, game_no, winner_id, game.get("winner_amount"),
            )
        except Exception as e:
            logger.exception("pv dice win credit failed: %s", e)
        fee_amount = int(game.get("fee_amount") or 0)
        if fee_amount > 0:
            collector_id = None
            try:
                cashier = await active_cashier(game["group_id"])
                if cashier:
                    cid = int(cashier)
                    if not is_owner(game["group_id"], cid):
                        collector_id = cid
            except Exception as e:
                print(f"pv dice resolve fee collector: {e}")
            if collector_id:
                try:
                    mode = (game.get("mode_label") or "").strip()
                    if not mode:
                        mode = "فیکس" if game.get("bet_mode") == BET_MODE_FIXED else "اضافه"
                    await record_fee_income(
                        chat_id=game["group_id"],
                        user_id=collector_id,
                        amount=fee_amount,
                        admin_id=collector_id,
                        description=with_game_id(f"حق واسطه بازی پیوی ({mode})", game_no),
                    )
                except Exception:
                    pass
        try:
            from bot.challenges import flush_challenge_breaks
            await flush_challenge_breaks(bot, game["group_id"])
        except Exception:
            pass

    await _announce_pv_end(bot, game, winner_id=winner_id, is_tie=False, reason=reason)

    # لیگ فقط با نتیجه قطعی — بعد از اعلام نتیجه بازی
    if game.get("paid") and int(game.get("entry") or 0) > 0 and game.get("league_on_finish"):
        try:
            @sync_to_async
            def _record_league():
                from bot.league import record_league_wager_silent
                entry = int(game.get("entry") or 0)
                for p in game["players"]:
                    record_league_wager_silent(game["group_id"], p, entry)

            await _record_league()
            from bot.league import flush_league_unlocks
            await flush_league_unlocks(bot, game["group_id"])
        except Exception:
            logger.exception("pv league record/flush after finish failed")

    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _hist():
            from account.models import DiceGameHistory
            session = f"pv_{game_id}"
            for p in game["players"]:
                is_w = int(p) == int(winner_id)
                amt = (game["winner_amount"] - game["entry"]) if (is_w and game.get("paid")) else (
                    -game["entry"] if game.get("paid") else 0
                )
                total = int(_map_get(game.get("totals"), p, 0) or 0)
                rolled, rounds, _rem = _roll_progress(game, p)
                tracked = int(_map_get(game.get("dice_rolled"), p, 0) or 0)
                count = tracked if tracked > 0 else (rolled if rolled > 0 else (rounds or 1))
                DiceGameHistory.objects.create(
                    telegram_chat_id=game["group_id"],
                    telegram_user_id=int(p),
                    total=int(total),
                    average=_avg_per_die(total, count),
                    count=int(count),
                    winner=bool(is_w),
                    amount_won=int(amt),
                    bet_amount=int(game.get("entry") or 0) if game.get("paid") else 0,
                    game_session=session,
                )
        await _hist()
    except Exception as e:
        print(f"pv dice history: {e}")
    await _persist_pv_state_now()


async def ensure_sweeper(bot: Bot) -> None:
    global _sweeper_started
    first_boot = not _sweeper_started
    _load_pv_state()
    social.load_social()
    _resume_timers_after_restore(bot, send_round_prompts=first_boot)
    if _sweeper_started:
        return
    _sweeper_started = True
    asyncio.create_task(_sweep_loop(bot))


async def _sweep_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(20)
        try:
            from django.core.cache import cache
            for iid, inv in list(INVITES.items()):
                if inv.get("status") == "accepting" and not cache.get(f"tg_pv_accept_claim:{iid}"):
                    if cache.get(_paid_key(iid)) == "done":
                        INVITES.pop(iid, None)
                        inv["status"] = "accepted_orphan"
                        _unbind_user(inv["challenger_id"], "invite", iid)
                        _unbind_user(inv["target_id"], "invite", iid)
                    else:
                        inv["status"] = "pending"
                    _persist_pv_state()
        except Exception:
            pass
        # انقضای جستجوی حریف + درمان قفل یتیم
        try:
            from bot.pv_search import SEARCH_OFFERS, _expire_offer, clear_pv_search
            now_s = time.time()
            for oid, offer in list(SEARCH_OFFERS.items()):
                if offer.get("status") != "pending":
                    continue
                if now_s <= float(offer.get("expires_at") or 0):
                    continue
                ch = offer.get("challenger_id")
                _expire_offer(oid, reason="timeout")
                if ch:
                    clear_pv_search(int(ch))
                    try:
                        await send_private(
                            bot, int(ch),
                            "⏰ مهلت جستجوی حریف تمام شد؛ کسی قبول نکرد.\n"
                            "دوباره «جستجو» کنید.",
                        )
                    except Exception:
                        pass
        except Exception:
            logger.exception("sweep search offers failed")
        try:
            _heal_orphan_busy_locks()
        except Exception:
            pass
        _persist_pv_state()
        _resume_timers_after_restore(bot, send_round_prompts=False)
        now = time.time()
        for iid, inv in list(INVITES.items()):
            if inv.get("status") == "pending" and now > float(inv.get("expires_at") or 0):
                await _expire_invite(bot, iid, reason="timeout")
