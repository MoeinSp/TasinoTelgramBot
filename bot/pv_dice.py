"""مسابقه تاس دونفره در پیوی — دعوت، تایمر، اینلاین."""
from __future__ import annotations

import asyncio
import re
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
    format_turn_limit_error,
    roll_dice,
    _generate_dice_numbers,
    _multinomial_fair,
)
from bot.dice_themes import get_theme, build_single_dice_message, build_multi_dice_message
from bot.helpers import send_private, get_group_theme
from bot import cache as bot_cache

INVITE_TTL = 120          # مهلت قبول/رد
MOVE_TTL = 180            # مهلت هر حرکت
MOVE_WARN_AT = 60         # اخطار یک دقیقه مانده
MIN_BET = 5

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
_PV_STATE_TTL = 60 * 60 * 48
_PV_CACHE_GAMES = "tg_pv_dice:v1:games"
_PV_CACHE_INVITES = "tg_pv_dice:v1:invites"
_PV_CACHE_BUSY = "tg_pv_dice:v1:busy"
_PV_CACHE_CUSTOM = "tg_pv_dice:v1:custom"
_pv_state_loaded = False
_active_watchdogs: set[str] = set()
_active_invite_timers: set[str] = set()
_accept_locks: dict[str, asyncio.Lock] = {}


def _persist_pv_state() -> None:
    """ذخیره کامل وضعیت پیوی در Redis (دعوت، بازی، قفل کاربر، تاس دلخواه)."""
    try:
        from django.core.cache import cache

        cache.set(_PV_CACHE_GAMES, dict(GAMES), timeout=_PV_STATE_TTL)
        cache.set(_PV_CACHE_INVITES, dict(INVITES), timeout=_PV_STATE_TTL)
        cache.set(_PV_CACHE_BUSY, dict(USER_BUSY), timeout=_PV_STATE_TTL)
        cache.set(_PV_CACHE_CUSTOM, dict(AWAITING_CUSTOM_DICE), timeout=_PV_STATE_TTL)
    except Exception as e:
        print(f"pv_dice persist state failed: {e}")


def _heal_restored_games() -> None:
    """اگر قبل از persist مرحله تعیین گیر کرده بود، وضعیت را درست کن."""
    changed = False
    for game in list(GAMES.values()):
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
            USER_BUSY.clear()
            USER_BUSY.update({int(k): v for k, v in busy.items()})
        if isinstance(custom, dict) and custom:
            AWAITING_CUSTOM_DICE.clear()
            AWAITING_CUSTOM_DICE.update({int(k): v for k, v in custom.items()})
        _heal_restored_games()
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


def _resume_timers_after_restore(bot: Bot) -> None:
    for gid, game in list(GAMES.items()):
        if game.get("status") not in ("finished", "cancelled"):
            _ensure_game_watchdog(bot, gid)
    for iid, inv in list(INVITES.items()):
        if inv.get("status") == "pending":
            _ensure_invite_timer(bot, iid)
    asyncio.create_task(_notify_restored_awaiting_rounds(bot))


async def _notify_restored_awaiting_rounds(bot: Bot) -> None:
    changed = False
    for gid, game in list(GAMES.items()):
        if game.get("status") != "awaiting_rounds":
            continue
        if game.get("_restored_notified"):
            continue
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


def parse_pv_start_command(text: str) -> dict | None:
    """شروع 2 100 پیوی | شروع 2 100 فیکس پیوی | شروع 2 100 اضافه پیوی"""
    raw = (text or "").strip()
    if not raw:
        return None
    # normalize persian digits lightly via caller
    parts = raw.split()
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
        return {"enabled": False, "reason": ""}
    return {
        "enabled": bool(getattr(g, "pv_start_enabled", False)),
        "reason": (getattr(g, "pv_start_off_reason", None) or "").strip(),
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
    }


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
        f"❌ حداقل مبلغ شرط پیوی در این گروه {minimum:,} واحد است.\n"
        f"💰 مبلغ وارد شده: {amount:,} واحد\n\n"
        f"فقط از {minimum:,} به بالا می‌توانید درخواست بدهید.\n"
        f"مثال: <code>شروع 2 {minimum} پیوی</code>"
    )


def user_busy(user_id: int) -> tuple[str, str] | None:
    return USER_BUSY.get(int(user_id))


def user_busy_label(user_id: int) -> str | None:
    """برچسب کوتاه وضعیت قفل کاربر — دعوت‌شونده تا قبول کامل آزاد است."""
    busy = user_busy(user_id)
    if not busy:
        return None
    kind, oid = busy
    if kind == "invite":
        inv = INVITES.get(oid)
        if not inv or inv.get("status") != "pending":
            return None
        # فقط فرستنده دعوت قفل است؛ گیرنده آزاد است
        if int(inv.get("challenger_id") or 0) != int(user_id):
            return None
        return "invite"
    game = GAMES.get(oid)
    if not game:
        return None
    st = game.get("status")
    if st == "qualifying":
        return "qualifying"
    if st == "awaiting_rounds":
        return "awaiting_rounds"
    if st == "playing":
        return "playing"
    return "game"


def pv_busy_short_title(code: str) -> str:
    return {
        "invite": "دعوت بازی پیوی (منتظر پاسخ حریف)",
        "qualifying": "مسابقه پیوی — تاس تعیین",
        "awaiting_rounds": "مسابقه پیوی — انتخاب تعداد راند",
        "playing": "مسابقه پیوی — در حال انجام",
        "game": "مسابقه پیوی فعال",
    }.get(code or "", "مسابقه پیوی فعال")


def format_pv_busy_message(code: str, *, for_other: bool = False, other_name: str = "") -> str:
    """متن واضح وقتی کاربر (یا حریف) مشغول پیوی است."""
    if code == "invite":
        if for_other:
            who = other_name or "این کاربر"
            return (
                f"⏳ {who} دعوت بازی پیوی فرستاده و منتظر پاسخ حریف است.\n"
                "بعد از قبول/رد یا لغو دعوت، دوباره تلاش کنید."
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
        body = "🎲 مسابقه پیوی — مرحله تاس تعیین"
        tip = "اول در پیوی ربات تاس تعیین را بزنید و بازی را تمام کنید."
    elif code == "awaiting_rounds":
        body = "🎲 مسابقه پیوی — انتخاب تعداد راند"
        tip = "اول در پیوی ربات تعداد راند را مشخص کنید (یا منتظر حریف بمانید)."
    elif code == "playing":
        body = "🎲 مسابقه پیوی — در حال انجام"
        tip = "اول بازی فعلی را در پیوی ربات تمام کنید."
    else:
        body = "🎲 مسابقه پیوی فعال"
        tip = "اول بازی فعلی را تمام کنید."

    if for_other:
        who = other_name or "این کاربر"
        return f"⏳ {who} الان مشغول است:\n{body}\nمنتظر پایان بازی بمانید."
    return (
        "⚠️ الان نمی‌توانید چالش جدید بفرستید.\n\n"
        f"وضعیت شما:\n{body}\n\n"
        f"💡 {tip}"
    )


def _bind_user(user_id: int, kind: str, oid: str) -> None:
    USER_BUSY[int(user_id)] = (kind, oid)
    _persist_pv_state()


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
        [IKB(text="ℹ️ جزئیات شرط", callback_data=f"pvd:inf:{invite_id}")],
    ])


def _game_roll_kb(
    game_id: str,
    *,
    remaining: int = 0,
    actions_left: int | None = None,
    allow_custom: bool = False,
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
    rows.append([IKB(text="📊 وضعیت بازی", callback_data=f"pvd:st:{game_id}")])
    return _kb(rows)


def _rounds_prompt_kb(game_id: str) -> InlineKeyboardMarkup:
    return _kb([[IKB(text="📊 وضعیت بازی", callback_data=f"pvd:st:{game_id}")]])


def _roll_kb_for(game: dict) -> InlineKeyboardMarkup:
    gid = game["id"]
    st = game.get("status")
    if st == "qualifying":
        return _game_roll_kb(gid, allow_custom=False)
    if st == "awaiting_rounds":
        return _rounds_prompt_kb(gid)
    if st != "playing":
        return _game_roll_kb(gid, allow_custom=False)
    turn = game.get("turn")
    rem = int((game.get("remaining") or {}).get(turn, 0) or 0) if turn else 0
    al = None
    if turn is not None and game.get("actions_left") is not None:
        al = (game.get("actions_left") or {}).get(turn)
    return _game_roll_kb(gid, remaining=rem, actions_left=al, allow_custom=True)


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


def parse_dice_command(text: str) -> int | None:
    raw = (text or "").strip()
    if raw == "تاس":
        return 1
    m = re.fullmatch(r"تاس\s+(\d{1,10})", raw)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except ValueError:
        return None
    return n if n >= 1 else None


def _group_dice_option_off(group_id: int) -> bool:
    return int(group_id) not in bot_cache.DICE_OPTION


def _group_turn_limit(group_id: int) -> int:
    return int(bot_cache.DICE_TURN_LIMIT.get(int(group_id)) or 0)


def _can_pv_roll(game: dict, uid: int, dice_count: int) -> tuple[bool, int, str]:
    if game.get("turn") != uid:
        return False, 0, "⏳ نوبت بازیکن دیگر است!\nلطفاً صبر کنید تا نوبت شما برسد."
    remaining = int((game.get("remaining") or {}).get(uid, 0) or 0)
    if remaining <= 0:
        return False, 0, "❌ شما تمام راندهای خود را ریخته‌اید!"
    if dice_count > remaining:
        return False, remaining, f"❌ شما فقط {remaining} راند باقی دارید!"
    limit = int(game.get("dice_turn_limit") or 0)
    actions_left = (game.get("actions_left") or {}).get(uid)
    if limit > 0 and actions_left is not None:
        if actions_left <= 0:
            return False, remaining, (
                f"⚠️ محدودیت تعداد تاس این گپ: {limit} نوبت\n\n"
                f"نوبت‌های مجازت تمام شده است."
            )
        if actions_left == 1 and dice_count != remaining:
            return False, remaining, format_turn_limit_error(limit, remaining, dice_count)
    return True, remaining, f"🎯 {remaining} راند باقی مانده"


def _build_roll_message(group_id: int, dice_count: int) -> tuple[str, int]:
    """فرمت دقیقاً مثل تاس گروه + مجموع امتیاز این پرتاب."""
    theme = get_theme(get_group_theme(int(group_id)))
    dice_option_off = _group_dice_option_off(group_id)
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

    text = (message.text or "").strip()
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


async def create_invite(bot: Bot, *, group_id: int, challenger_id: int, target_id: int,
                        bet_amount: int, has_bet: bool, bet_mode: str, fee_percent: int,
                        group_msg_id: int | None, challenger_name: str, target_name: str) -> str:
    invite_id = uuid.uuid4().hex[:12]
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
    }
    _bind_user(challenger_id, "invite", invite_id)
    # دعوت‌شونده تا قبول کامل قفل نمی‌شود — می‌تواند دعوت دیگر بگیرد یا در گروه بازی کند

    money_block = ""
    if has_bet:
        money_block = (
            f"💳 ورودی هر نفر: {costs['entry']:,} واحد ({mode_label})\n"
            f"🏆 جایزه برنده: {costs['winner_total']:,} واحد\n"
        )
        if fee_percent > 0:
            money_block += f"💸 حق واسطه: {costs['total_fee']:,} واحد\n"

    group_text = (
        "📨 چالش پیوی ارسال شد\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 از: {challenger_name}\n"
        f"🎯 برای: {target_name}\n"
        f"{money_block}"
        f"⏳ مهلت پاسخ: {INVITE_TTL // 60} دقیقه\n\n"
        "ادامه در پیوی ربات پیگیری می‌شود."
    )
    try:
        await bot.send_message(group_id, group_text, reply_to_message_id=group_msg_id, parse_mode="HTML")
    except Exception:
        pass

    ch_text = (
        "📤 دعوت شما ارسال شد\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"حریف: {target_name}\n"
        f"{money_block}"
        f"⏳ مهلت پاسخ حریف: {INVITE_TTL // 60} دقیقه\n\n"
        "💡 تا قبل از قبول حریف می‌توانید همین‌جا با دکمه «❌ لغو دعوت» دعوت را لغو کنید."
    )
    await send_private(bot, challenger_id, ch_text, reply_markup=_invite_challenger_kb(invite_id))

    tg_text = (
        "⚔️ چالش تاس پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"از طرف: {challenger_name}\n"
        f"{money_block}"
        "⚠️ اگر قبول کنید و در مهلت مقرر تاس نزنید، بازنده می‌شوید.\n"
        f"⏳ مهلت پاسخ: {INVITE_TTL // 60} دقیقه\n\n"
        "بعد از قبول و شروع بازی، لغو ممکن نیست."
    )
    ok = await send_private(bot, target_id, tg_text, reply_markup=_invite_target_kb(invite_id))
    if not ok:
        await _expire_invite(bot, invite_id, reason="no_pv_target")
        return invite_id

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


async def _expire_invite(bot: Bot, invite_id: str, *, reason: str) -> None:
    inv = INVITES.pop(invite_id, None)
    if not inv or inv.get("status") != "pending":
        return
    inv["status"] = "expired"
    _unbind_user(inv["challenger_id"], "invite", invite_id)
    _unbind_user(inv["target_id"], "invite", invite_id)
    if reason == "timeout":
        msg = (
            "⌛ دعوت بازی پیوی منقضی شد\n"
            "حریف در مهلت ۲ دقیقه‌ای پاسخ نداد.\n"
            "می‌توانید دوباره چالش بفرستید."
        )
    elif reason == "no_pv_target":
        msg = "⚠️ ارسال دعوت به پیوی حریف ممکن نشد؛ احتمالاً ربات را استارت نکرده است."
    else:
        msg = "ℹ️ دعوت بازی پیوی بسته شد."
    for uid in (inv["challenger_id"], inv["target_id"]):
        try:
            await send_private(bot, uid, msg)
        except Exception:
            pass


async def handle_callback(call, bot: Bot) -> bool:
    data = call.data or ""
    if not data.startswith("pvd:"):
        return False
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    await call.answer()

    if action == "can" and len(parts) >= 3:
        return await _cancel_invite(bot, call.from_user.id, parts[2])
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
        "✏️ تعداد تاس دلخواه را بنویسید\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"باقی‌مانده راند شما: <b>{rem}</b>\n\n"
        "مثلاً: <code>15</code>\n"
        "یا مستقیم: <code>تاس 15</code>\n"
        "برای یک تاس: <code>تاس</code>",
    )
    return True


async def _cancel_invite(bot: Bot, user_id: int, invite_id: str) -> bool:
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
    await send_private(bot, inv["challenger_id"], "❌ دعوت بازی پیوی لغو شد.")
    await send_private(bot, inv["target_id"], "ℹ️ چالش‌کننده دعوت بازی را لغو کرد.")
    return True


async def _reject_invite(bot: Bot, user_id: int, invite_id: str) -> bool:
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
                await _expire_invite(bot, invite_id, reason="timeout")
                return True

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

            for uid in (inv["challenger_id"], inv["target_id"]):
                label = user_busy_label(uid)
                busy = user_busy(uid)
                if busy and busy[0] == "game":
                    inv["status"] = "pending"
                    _persist_pv_state()
                    await send_private(
                        bot, user_id,
                        "⚠️ فعلاً نمی‌توان قبول کرد؛ یکی از طرفین مشغول است:\n"
                        f"{pv_busy_short_title(label or 'game')}",
                    )
                    return True

            try:
                from bot.dice_game import is_user_involved_in_group_game
                if (
                    is_user_involved_in_group_game(inv["group_id"], inv["challenger_id"])
                    or is_user_involved_in_group_game(inv["group_id"], inv["target_id"])
                ):
                    inv["status"] = "pending"
                    _persist_pv_state()
                    await send_private(
                        bot, user_id,
                        "⚠️ یکی از طرفین هنوز درگیر بازی گروهی همان گپ است "
                        "(عضو بازی یا استارت‌کننده لابی).\n"
                        "اول آن را تمام/لغو کنید، بعد دعوت را قبول کنید.",
                    )
                    return True
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
                for uid in players:
                    _, available, _ = await get_playable_balance(inv["group_id"], uid)
                    if available < entry:
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
                        return True

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
                    return True

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
            }
            GAMES[game_id] = game
            _persist_pv_state()
            _bind_user(players[0], "game", game_id)
            _bind_user(players[1], "game", game_id)
            if inv["has_bet"] and entry > 0:
                cache.set(paid_key, "done", timeout=60 * 60 * 24 * 14)

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
            for uid in players:
                await send_private(bot, uid, start_text, reply_markup=_roll_kb_for(game))

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
                targets: list = []
                if game["status"] == "qualifying":
                    targets = [p for p in game["players"] if p not in game["qual_rolls"]]
                elif game["status"] == "awaiting_rounds":
                    targets = [game.get("round_setter")]
                elif game["status"] == "playing":
                    turn = game.get("turn")
                    targets = [turn] if turn else list(game["players"])
                warn_ok = False
                for uid in targets:
                    if not uid:
                        continue
                    try:
                        await send_private(
                            bot, uid,
                            "⏰ یک دقیقه تا پایان نوبت شما مانده!\n"
                            "اگر حرکت نکنید بازنده می‌شوید.",
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
    game = GAMES.get(game_id)
    if not game or game.get("status") in ("finished", "cancelled"):
        return
    loser = None
    if game["status"] == "qualifying":
        missing = [p for p in game["players"] if p not in game["qual_rolls"]]
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
    if not loser:
        return
    winner = [p for p in game["players"] if p != loser][0]
    await _finish_game(bot, game_id, winner_id=winner, reason="timeout")


async def _do_roll(bot: Bot, user_id: int, game_id: str, dice_count: int = 1) -> bool:
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
        if uid in game["qual_rolls"]:
            await send_private(bot, uid, "تاس تعیین شما ثبت شد؛ منتظر تاس حریف بمانید.")
            return True
        msg, val = _build_roll_message(game["group_id"], 1)
        game["qual_rolls"][uid] = val
        game["move_deadline"] = time.time() + MOVE_TTL
        game["warned"] = False
        _persist_pv_state()
        name = game["names"].get(uid, str(uid))
        for p in game["players"]:
            await send_private(bot, p, f"🎲 تاس تعیین {name}:\n{msg}")
        if len(game["qual_rolls"]) < 2:
            await send_private(bot, uid, "ثبت شد. منتظر تاس حریف…", reply_markup=_roll_kb_for(game))
            return True
        a, b = game["players"]
        ra, rb = game["qual_rolls"][a], game["qual_rolls"][b]
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
        _persist_pv_state()
        sname = game["names"].get(setter, str(setter))
        for p in game["players"]:
            if p == setter:
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

    allowed, remaining, err = _can_pv_roll(game, uid, dice_count)
    if not allowed:
        await send_private(bot, uid, err)
        return True

    msg, total = _build_roll_message(game["group_id"], dice_count)
    game["totals"][uid] = int(game["totals"].get(uid, 0)) + int(total)
    game["remaining"][uid] = int(game["remaining"].get(uid, 0)) - dice_count
    if (game.get("actions_left") or {}).get(uid) is not None:
        game["actions_left"][uid] = max(0, int(game["actions_left"][uid]) - 1)
    _persist_pv_state()

    rem = int(game["remaining"][uid])
    total_score = int(game["totals"][uid])
    other = [p for p in game["players"] if p != uid][0]
    finished = rem <= 0 and int(game["remaining"][other]) <= 0
    msg = _append_progress(msg, rem=rem, total_score=total_score, finished=finished)
    name = game["names"].get(uid, str(uid))
    for p in game["players"]:
        await send_private(bot, p, f"👤 {name}\n{msg}")

    if finished:
        if game["totals"][uid] == game["totals"][other]:
            await _finish_tie(bot, game_id)
        else:
            winner = uid if game["totals"][uid] > game["totals"][other] else other
            await _finish_game(bot, game_id, winner_id=winner, reason="normal")
        return True

    # مثل گروه: نوبت فقط وقتی راندهای این بازیکن تمام شود عوض می‌شود
    if rem <= 0:
        game["turn"] = other if int(game["remaining"][other]) > 0 else None
        game["move_deadline"] = time.time() + MOVE_TTL
        game["warned"] = False
        _persist_pv_state()
        turn = game["turn"]
        if turn:
            await send_private(
                bot, turn,
                "🔁 نوبت شماست!\n"
                "🎲 بنویسید <code>تاس</code> یا <code>تاس N</code> یا دکمه بزنید.",
                reply_markup=_roll_kb_for(game),
            )
            other_waiting = [p for p in game["players"] if p != turn][0]
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
    game["dice_turn_limit"] = turn_limit
    game["actions_left"] = {}
    for p in game["players"]:
        game["actions_left"][p] = min(turn_limit, rounds) if turn_limit > 0 else None
    game["status"] = "playing"

    # مثل گروه: نفر اول = حریفِ انتخاب‌کننده راند
    setter = int(game["round_setter"])
    starter = [p for p in game["players"] if p != setter][0]
    game["turn"] = starter
    game["move_deadline"] = time.time() + MOVE_TTL
    game["warned"] = False
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
        if uid in (game.get("qual_rolls") or {}):
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
    busy = user_busy(uid)
    if not busy or busy[0] != "game":
        AWAITING_CUSTOM_DICE.pop(uid, None)
        return False
    game_id = busy[1]
    game = GAMES.get(game_id)
    if not game or game.get("status") in ("finished", "cancelled"):
        AWAITING_CUSTOM_DICE.pop(uid, None)
        return False

    text = (message.text or "").strip()

    # دستور تاس / تاس N — مثل گروه، بدون نیاز به دکمه
    dice_count = parse_dice_command(text)
    if dice_count is not None:
        AWAITING_CUSTOM_DICE.pop(uid, None)
        return await _do_roll(bot, uid, game_id, dice_count)

    # عدد خالص: راند یا تاس دلخواه
    if re.fullmatch(r"\d{1,10}", text):
        n = int(text)
        if game.get("status") == "awaiting_rounds":
            AWAITING_CUSTOM_DICE.pop(uid, None)
            return await _select_rounds(bot, uid, game_id, n)
        custom_gid = AWAITING_CUSTOM_DICE.get(uid)
        if custom_gid and custom_gid == game_id and game.get("status") == "playing":
            AWAITING_CUSTOM_DICE.pop(uid, None)
            return await _do_roll(bot, uid, game_id, n)
        if (
            game.get("status") == "playing"
            and game.get("turn") == uid
            and n >= 1
        ):
            return await _do_roll(bot, uid, game_id, n)

    # هر پیام دیگر وسط بازی: داخل بازی بمان، منوی عادی نیاید
    await _remind_in_game(bot, uid, game)
    return True


async def _send_status(bot: Bot, user_id: int, game_id: str) -> bool:
    game = GAMES.get(game_id)
    if not game:
        await send_private(bot, user_id, "بازی پیدا نشد.")
        return True
    lines = [
        "📊 وضعیت مسابقه پیوی",
        "━━━━━━━━━━━━━━━━━━━━",
        f"وضعیت: {game['status']}",
    ]
    for p in game["players"]:
        lines.append(
            f"• {game['names'].get(p, p)} — مجموع {game['totals'].get(p, 0)} "
            f"| باقی {game['remaining'].get(p, 0)}"
        )
    if game.get("has_bet"):
        lines.append(f"💳 ورودی: {game['entry']:,} | 🏆 جایزه: {game['winner_amount']:,}")
    left = max(0, int(float(game.get("move_deadline") or 0) - time.time()))
    lines.append(f"⏱ مهلت حرکت فعلی: {left // 60}:{left % 60:02d}")
    await send_private(bot, user_id, "\n".join(lines))
    return True


async def _cancel_game_refund(bot: Bot, game_id: str, message: str) -> None:
    import html as _html

    game = GAMES.pop(game_id, None)
    if not game:
        return
    game["status"] = "cancelled"
    for p in game["players"]:
        _unbind_user(p, "game", game_id)
    if game.get("paid") and game.get("entry"):
        from bot.finance import increase_wallet
        for p in game["players"]:
            try:
                await increase_wallet(game["group_id"], p, game["entry"], description="بازگشت ورودی بازی پیوی")
            except Exception:
                pass
    for p in game["players"]:
        await send_private(bot, p, message)
    # اعلام لغو در گروه هم (مثلاً هر دو در مرحله تعیین نزدند)
    try:
        group_id = int(game["group_id"])
        names = game.get("names") or {}
        players = list(game.get("players") or [])
        a = players[0] if players else None
        b = players[1] if len(players) > 1 else None
        na = _html.escape(str(names.get(a, a) if a is not None else "?"))
        nb = _html.escape(str(names.get(b, b) if b is not None else "?"))
        await bot.send_message(
            group_id,
            f"⛔ مسابقه پیوی {na} و {nb} لغو شد.\n{_html.escape(message)}",
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"pv dice cancel group announce failed: {e}")


def _pv_result_rows(game: dict) -> list[tuple]:
    """[(uid, total, roll_count), ...] مرتب‌شده نزولی."""
    rounds = int(game.get("total_rounds") or 0)
    rows = []
    for p in game["players"]:
        total = int((game.get("totals") or {}).get(p, 0) or 0)
        rem = int((game.get("remaining") or {}).get(p, 0) or 0)
        count = max(0, rounds - rem) if rounds else 0
        if count <= 0 and total > 0:
            count = rounds or 1
        rows.append((p, total, count or (rounds or 1)))
    rows.sort(key=lambda x: x[1], reverse=True)
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
    results = _pv_result_rows(game)
    lines: list[str] = []
    if winner_id and not is_tie:
        lines.append("🏁 مسابقه تاس در پیوی تمام شد")
        lines.append(f"🏆 برنده: {name_fn(winner_id)} 🥇")
        if reason == "timeout":
            loser = next(
                (p for p in game.get("players") or [] if int(p) != int(winner_id)),
                None,
            )
            if loser is not None:
                lines.append(
                    f"⏱ {name_fn(loser)} به‌خاطر نزدن تاس در مهلت مقرر باخت."
                )
            else:
                lines.append("⏱ به‌خاطر اتمام زمان نوبت.")
    else:
        lines.append("🏁 مسابقه تاس در پیوی به پایان رسید!")
        if is_tie:
            lines.append("⚠️ بازی با تساوی به پایان رسید")
            if game.get("paid"):
                lines.append("💰 ورودی‌ها برگردانده شد.")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("🏆 نتایج نهایی")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    for i, (uid, total, count) in enumerate(results, start=1):
        display = name_fn(uid)
        medal = "🥇" if i == 1 and not is_tie else ("⭐" if i == 1 else "📌")
        avg = total / count if count > 0 else 0.0
        lines.append(f"{medal} {i:02}. {display}")
        lines.append(f"   📊 مجموع: {total}")
        lines.append(f"   🎲 تاس: {count}")
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
    for p in players:
        await send_private(bot, p, pv_text)

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
    try:
        await bot.send_message(group_id, group_text, parse_mode="HTML")
    except Exception as e:
        print(f"pv dice group announce failed: {e}")

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

    if game.get("paid") and game.get("entry"):
        from bot.finance import increase_wallet
        for p in game["players"]:
            try:
                await increase_wallet(
                    game["group_id"], p, game["entry"],
                    description="بازگشت ورودی بازی پیوی (تساوی)",
                )
            except Exception:
                pass

    await _announce_pv_end(bot, game, is_tie=True, reason="tie")

    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _hist():
            from account.models import DiceGameHistory
            session = f"pv_{game_id}"
            rolls = game["total_rounds"] or 1
            for p in game["players"]:
                total = game["totals"].get(p, 0)
                DiceGameHistory.objects.create(
                    telegram_chat_id=game["group_id"],
                    telegram_user_id=int(p),
                    total=int(total),
                    average=(total / rolls) if rolls else 0,
                    count=int(rolls),
                    winner=False,
                    amount_won=0,
                    bet_amount=int(game.get("entry") or 0) if game.get("paid") else 0,
                    game_session=session,
                )
        await _hist()
    except Exception as e:
        print(f"pv dice tie history: {e}")


async def _finish_game(bot: Bot, game_id: str, *, winner_id: int, reason: str) -> None:
    game = GAMES.pop(game_id, None)
    if not game:
        return
    game["status"] = "finished"
    for p in game["players"]:
        _unbind_user(p, "game", game_id)

    winner_id = int(winner_id)

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
        except Exception as e:
            print(f"pv dice win credit failed: {e}")
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

    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def _hist():
            from account.models import DiceGameHistory
            session = f"pv_{game_id}"
            for p in game["players"]:
                is_w = p == winner_id
                amt = (game["winner_amount"] - game["entry"]) if (is_w and game.get("paid")) else (
                    -game["entry"] if game.get("paid") else 0
                )
                rolls = game["total_rounds"] or 1
                total = game["totals"].get(p, 0)
                DiceGameHistory.objects.create(
                    telegram_chat_id=game["group_id"],
                    telegram_user_id=int(p),
                    total=int(total),
                    average=(total / rolls) if rolls else 0,
                    count=int(rolls),
                    winner=bool(is_w),
                    amount_won=int(amt),
                    bet_amount=int(game.get("entry") or 0) if game.get("paid") else 0,
                    game_session=session,
                )
        await _hist()
    except Exception as e:
        print(f"pv dice history: {e}")


async def ensure_sweeper(bot: Bot) -> None:
    global _sweeper_started
    _load_pv_state()
    _resume_timers_after_restore(bot)
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
        _persist_pv_state()
        _resume_timers_after_restore(bot)
        now = time.time()
        for iid, inv in list(INVITES.items()):
            if inv.get("status") == "pending" and now > float(inv.get("expires_at") or 0):
                await _expire_invite(bot, iid, reason="timeout")
