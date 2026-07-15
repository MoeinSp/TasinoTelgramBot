"""
سیستم بازی تاس — پورت کامل از rubpy/bot/dice.py و rubpy/bot/func.py
"""
import asyncio
import math
import random
import re
import secrets
import threading
from typing import Optional

import jdatetime

from bot.dice_themes import (
    THEMES,
    get_theme,
    build_single_dice_message,
    build_multi_dice_message,
)

# ─── حافظه بازی‌ها (in-memory) ───────────────────────────────────────────────

ACTIVE_GAMES: dict = {}
GAME_PROGRESS: dict = {}
LAST_DICE: dict = {}
WAITING_ROUNDS: dict = {}  # chat_id → winner_id (منتظر انتخاب راند)

GAME_TTL = 600        # ۱۰ دقیقه — ثبت‌نام
PLAYING_TTL = 900     # ۱۵ دقیقه — بعد از شروع بازی
WAITING_TTL = 120     # مهلت تعیین راند

_GAME_LOCKS: dict[int, threading.Lock] = {}


def _game_lock(chat_id) -> threading.Lock:
    key = int(chat_id)
    if key not in _GAME_LOCKS:
        _GAME_LOCKS[key] = threading.Lock()
    return _GAME_LOCKS[key]


# ─── توابع مدیریت بازی ───────────────────────────────────────────────────────

BET_MODE_FIXED = "fixed"    # شروع 2 50 — ورودی ثابت، حق واسطه از جایزه
BET_MODE_EXTRA = "extra"    # شروع 2 50 اضافه — ورودی = شرط + حق واسطه


def create_game(chat_id, total_players, bet_amount=0, fee_percent=0, has_bet=False,
                bet_mode: str = BET_MODE_FIXED, starter_admin_id: int | None = None):
    import time
    game = {
        "chat_id": chat_id,
        "total_players": total_players,
        "players": [],
        "players_dice": {},
        "status": "waiting",
        "has_bet": has_bet,
        "bet_amount": bet_amount,
        "fee_percent": fee_percent,
        "bet_mode": bet_mode,
        "starter_admin_id": starter_admin_id,
        "fixed_entry": bet_mode == BET_MODE_FIXED,
        "rounds": 0,
        "total_rounds": 0,
        "is_turn_based": False,
        "turn": None,
        "players_rolls": {},
        "expires_at": time.time() + GAME_TTL,
    }
    ACTIVE_GAMES[chat_id] = game
    return game


def calc_bet_costs(bet_amount: int, fee_percent: int, bet_mode: str = BET_MODE_FIXED,
                   player_count: int = 0) -> dict:
    """
    محاسبه ورودی، حق واسطه و جایزه.

    فیکس (شروع 2 50):
      ورودی = 50 | جمع = 100 | برد = 100 − حق‌واسطه = 90 (با ۱۰٪)

    اضافه (شروع 2 50 اضافه):
      ورودی = 50 + حق‌واسطه = 55 | برد = 2×50 = 100
    """
    stake = bet_amount
    fee_per = int(stake * fee_percent / 100) if fee_percent > 0 else 0
    is_fixed = bet_mode == BET_MODE_FIXED
    entry = stake if is_fixed else stake + fee_per
    result = {
        "entry": entry,
        "fee_per": fee_per,
        "stake": stake,
        "bet_mode": bet_mode,
    }
    if player_count > 0:
        gross_prize = stake * player_count
        total_fee = int(gross_prize * fee_percent / 100) if fee_percent > 0 else 0
        winner_total = gross_prize - total_fee if is_fixed else gross_prize
        result.update(
            gross_prize=gross_prize,
            total_fee=total_fee,
            winner_total=winner_total,
        )
    return result


def _game_bet_mode(game: dict) -> str:
    mode = game.get("bet_mode")
    if mode in (BET_MODE_FIXED, BET_MODE_EXTRA):
        return mode
    if game.get("fixed_entry") is False:
        return BET_MODE_EXTRA
    return BET_MODE_FIXED


def _game_has_money_bet(game: dict) -> bool:
    return bool(game.get("has_bet") and game.get("bet_amount", 0) > 0)


def get_game(chat_id) -> Optional[dict]:
    game = ACTIVE_GAMES.get(chat_id)
    if not game:
        return None
    total = int(game.get("total_players") or 0)
    players = list(game.get("players") or [])
    if total and len(players) > total:
        game = dict(game)
        game["players"] = players[:total]
        dice = game.get("players_dice") or {}
        game["players_dice"] = {p: dice[p] for p in game["players"] if p in dice}
        ACTIVE_GAMES[chat_id] = game
    return game


def delete_game(chat_id):
    ACTIVE_GAMES.pop(chat_id, None)
    GAME_PROGRESS.pop(chat_id, None)
    WAITING_ROUNDS.pop(chat_id, None)


def has_active_game(chat_id) -> bool:
    import time
    game = ACTIVE_GAMES.get(chat_id)
    if not game:
        if chat_id in GAME_PROGRESS or chat_id in WAITING_ROUNDS:
            finish_game_cleanup(chat_id)
        return False
    if game.get("status") == "finished":
        finish_game_cleanup(chat_id)
        return False
    expires_at = game.get("expires_at")
    if expires_at and time.time() > expires_at:
        finish_game_cleanup(chat_id)
        return False
    if game.get("status") == "waiting" and game.get("awaiting_rounds"):
        if chat_id not in WAITING_ROUNDS:
            finish_game_cleanup(chat_id)
            return False
    return True


def is_game_full(chat_id) -> bool:
    game = get_game(chat_id)
    if not game:
        return False
    return len(game["players"]) >= game["total_players"]


def get_remaining_players(chat_id) -> int:
    game = get_game(chat_id)
    if not game:
        return 0
    return game["total_players"] - len(game["players"])


def registration_complete(game: dict) -> bool:
    if not game:
        return False
    total = int(game.get("total_players") or 0)
    players = list(game.get("players") or [])[:total]
    if not total or len(players) < total:
        return False
    dice = game.get("players_dice") or {}
    return all(p in dice for p in players)


def is_user_in_game(chat_id, user_id) -> bool:
    game = get_game(chat_id)
    if not game:
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    return any(int(p) == uid for p in (game.get("players") or []))


def is_user_involved_in_group_game(chat_id, user_id) -> bool:
    """بازیکن ثبت‌شده یا ادمینی که لابی را استارت کرده."""
    game = get_game(chat_id)
    if not game:
        return False
    st = game.get("status")
    if st in ("finished", "cancelled"):
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    if any(int(p) == uid for p in (game.get("players") or [])):
        return True
    starter = game.get("starter_admin_id")
    if starter is None:
        return False
    try:
        return int(starter) == uid
    except (TypeError, ValueError):
        return False


def _pv_blocks_group_play(user_id) -> str | None:
    try:
        from bot.pv_dice import user_busy_label, format_pv_busy_message
    except Exception:
        return None
    code = user_busy_label(user_id)
    if not code:
        return None
    return format_pv_busy_message(code)


def add_player_to_game(chat_id, user_id):
    with _game_lock(chat_id):
        game = get_game(chat_id)
        if not game:
            return False, "بازی فعالی وجود ندارد"
        total = int(game.get("total_players") or 0)
        players = list(game.get("players") or [])
        if len(players) >= total:
            return False, "تعداد بازیکن‌ها پر شده است"
        if user_id in players:
            return False, "این کاربر قبلاً ثبت نام کرده است"
        players.append(user_id)
        game["players"] = players[:total]
        ACTIVE_GAMES[chat_id] = game
    return True, "بازیکن اضافه شد"


def remove_player_from_game(chat_id, user_id):
    """حذف بازیکن از ثبت‌نام (مثلاً موجودی ناکافی بعد از پیوستن)."""
    with _game_lock(chat_id):
        game = ACTIVE_GAMES.get(chat_id)
        if not game:
            return False
        game = dict(game)
        game["players"] = [p for p in (game.get("players") or []) if p != user_id]
        dice = dict(game.get("players_dice") or {})
        dice.pop(user_id, None)
        game["players_dice"] = dice
        ACTIVE_GAMES[chat_id] = game
        return True


def finish_game_cleanup(chat_id):
    delete_game(chat_id)
    LAST_DICE.pop(chat_id, None)
    from django.core.cache import cache as django_cache
    django_cache.delete(f"dice_finalizing_{chat_id}")
    django_cache.delete(f"dice_waiting_finalize_{chat_id}")


# ─── منطق تاس ────────────────────────────────────────────────────────────────

def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def _binomial_approx(n, p):
    if n <= 0 or p <= 0.0:
        return 0
    if p >= 1.0:
        return n
    mean = n * p
    var = n * p * (1.0 - p)
    std = math.sqrt(var)
    if std < 1e-9:
        return _clamp(int(round(mean)), 0, n)
    x = random.gauss(mean, std)
    return _clamp(int(math.floor(x + 0.5)), 0, n)


def roll_dice(chat_id, dice_option_off: bool) -> int:
    """تولید یک تاس با در نظر گرفتن تاس متوالی"""
    r = secrets.randbelow(6) + 1
    if dice_option_off:
        last = LAST_DICE.get(chat_id)
        if last is not None and r == last:
            r = 1 if r == 6 else r + 1
    LAST_DICE[chat_id] = r
    return r


# ─── مدیریت راند و امتیاز ────────────────────────────────────────────────────

def format_turn_limit_error(limit: int, remaining: int, dice_count: int) -> str:
    """فقط نوبت آخر: باید دقیقاً همه تاس‌های باقی‌مانده ریخته شود."""
    return (
        f"⚠️ محدودیت تعداد تاس این گپ: {limit} نوبت\n\n"
        f"باید همه تاس‌هایت را در دقیقاً {limit} نوبت بریزی.\n\n"
        f"الان: آخرین نوبت · {remaining} تاس باقی\n"
        f"باید همه {remaining} تاس را در این نوبت بریزی.\n\n"
        f"تو خواستی {dice_count} تاس بریزی.\n"
        f"👉 بگو: تاس {remaining}"
    )


def can_player_roll(chat_id, user_id, dice_count=1):
    game = get_game(chat_id)
    if not game or game.get("status") != "playing":
        return True, 0, ""

    if game.get("is_turn_based") and game.get("turn"):
        if game["turn"] != user_id:
            return False, 0, "⏳ نوبت بازیکن دیگر است!\nلطفاً صبر کنید تا نوبت شما برسد."

    progress = GAME_PROGRESS.get(chat_id, {})
    if user_id not in progress:
        return False, 0, "❌ شما در این بازی عضو نیستید!"

    remaining = progress[user_id]["remaining"]
    if remaining <= 0:
        return False, 0, "❌ شما تمام راندهای خود را ریخته‌اید!"
    if dice_count > remaining:
        return False, remaining, f"❌ شما فقط {remaining} راند باقی دارید!"

    # محدودیت نوبت: در نوبت‌های غیرآخر آزاد است (حتی همه یکجا).
    # فقط نوبت آخر باید دقیقاً برابر تاس‌های باقی‌مانده باشد.
    limit = int(game.get("dice_turn_limit") or 0)
    actions_left = progress[user_id].get("actions_left")
    if limit > 0 and actions_left is not None:
        if actions_left <= 0:
            return False, remaining, (
                f"⚠️ محدودیت تعداد تاس این گپ: {limit} نوبت\n\n"
                f"نوبت‌های مجازت تمام شده است."
            )
        if actions_left == 1 and dice_count != remaining:
            return False, remaining, format_turn_limit_error(
                limit, remaining, dice_count
            )

    return True, remaining, f"🎯 {remaining} راند باقی مانده"


def save_roll_result(chat_id, user_id, dice_count, total):
    game = get_game(chat_id)
    if not game or game.get("status") != "playing":
        return False, 0, 0

    progress = GAME_PROGRESS.get(chat_id, {})
    if user_id not in progress:
        return False, 0, 0

    remaining_before = progress[user_id]["remaining"]
    if dice_count > remaining_before:
        return False, 0, remaining_before

    progress[user_id]["total"] += total
    progress[user_id]["remaining"] -= dice_count
    if progress[user_id].get("actions_left") is not None:
        progress[user_id]["actions_left"] = max(0, progress[user_id]["actions_left"] - 1)
    remaining = progress[user_id]["remaining"]
    current_total = progress[user_id]["total"]

    if game.get("is_turn_based") and game.get("turn") == user_id and remaining == 0:
        players_list = game.get("players", [])
        if len(players_list) == 2:
            for player in players_list:
                if player != user_id:
                    other_rem = progress.get(player, {}).get("remaining", 0)
                    game["turn"] = player if other_rem > 0 else None
                    break

    all_remaining = [p["remaining"] for p in progress.values()]
    finished = all(r <= 0 for r in all_remaining)
    import time
    game["expires_at"] = time.time() + PLAYING_TTL

    return finished, current_total, remaining


# ─── should_continue برای ثبت‌نام ────────────────────────────────────────────

def join_status_note(remaining):
    if remaining > 0:
        return f"\n\n✅ كاربر به بازی پیوست!\n📌 {remaining} نفر دیگر نیاز است."
    # پیام «ثبت‌نام کامل» جداگانه بعد از نمایش تاس می‌آید
    return ""


async def should_continue(chat_id, user_id, bot, message_id, text):
    """
    (0, None) = نده (کاربر در بازی است یا بازی پر)
    (1, None) = تاس عادی بریز
    (2, note) = تازه ثبت نام شد / باید تاس تعیین ذخیره شود
    """
    if not has_active_game(chat_id):
        return 1, None

    if is_user_in_game(chat_id, user_id):
        game = get_game(chat_id)
        waiting_for_rounds = chat_id in WAITING_ROUNDS or (
            game and game.get("status") == "waiting" and game.get("awaiting_rounds")
        )
        if waiting_for_rounds:
            await bot.send_message(
                chat_id=chat_id,
                text="⏳ منتظر بمان... باید اول راند تعیین شه!",
                reply_to_message_id=message_id
            )
            return 0, None
        if game and game.get("status") == "waiting":
            dice = game.get("players_dice") or {}
            # جوین شده ولی تاس تعیین ثبت نشده (خطا بین جوین و register) → اجازهٔ ادامه
            if user_id not in dice:
                if text != "تاس":
                    await bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ لطفا برای تعیین فقط از دستور تاس استفاده کنید بدون عدد !",
                        reply_to_message_id=message_id,
                    )
                    return 0, None
                return 2, None
            await bot.send_message(
                chat_id=chat_id,
                text="✅ شما در بازی ثبت‌نام کرده‌اید. منتظر بقیه بازیکنان...",
                reply_to_message_id=message_id
            )
            return 0, None
        return 1, None

    if is_game_full(chat_id):
        from bot.helpers import quiet_extra_on
        if not quiet_extra_on(chat_id):
            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ توی این بازی نیستی تاس نریز!!\n",
                reply_to_message_id=message_id
            )
        return 0, None

    if text != "تاس":
        await bot.send_message(
            chat_id=chat_id,
            text="⚠️ لطفا برای تعیین فقط از دستور تاس استفاده کنید بدون عدد !",
            reply_to_message_id=message_id
        )
        return 0, None

    pv_block = _pv_blocks_group_play(user_id)
    if pv_block:
        await bot.send_message(
            chat_id=chat_id,
            text=pv_block,
            reply_to_message_id=message_id,
        )
        return 0, None

    success, message = add_player_to_game(chat_id, user_id)
    if not success:
        await bot.send_message(chat_id=chat_id, text=f"⚠️ {message}", reply_to_message_id=message_id)
        return 0, None

    remaining = get_remaining_players(chat_id)
    return 2, join_status_note(remaining)


# ─── ثبت تاس در مرحله waiting (تعیین برنده برای راند) ───────────────────────

async def register_and_save_dice(chat_id, user_id, dice_value, bot, message_id):
    from bot.finance import get_playable_balance, format_insufficient_balance_message

    game = get_game(chat_id)
    if not game:
        return False

    if _game_has_money_bet(game):
        bet_mode = _game_bet_mode(game)
        fee_percent = game.get("fee_percent", 0)
        bet_amount = game["bet_amount"]
        costs = calc_bet_costs(bet_amount, fee_percent, bet_mode)
        entry_cost = costs["entry"]
        fee_per = costs["fee_per"]
        total_balance, playable, pending = await get_playable_balance(chat_id, user_id)
        if playable < entry_cost:
            if bet_mode == BET_MODE_FIXED and fee_per > 0:
                fee_line = f"\n   └ حق واسطه ({fee_percent}٪): {fee_per:,} واحد (از جایزه)"
            elif fee_per > 0:
                fee_line = f"\n   ├ شرط: {bet_amount:,} واحد\n   └ حق واسطه: {fee_per:,} واحد"
            else:
                fee_line = ""
            mode_line = " (فیکس)" if bet_mode == BET_MODE_FIXED else " (اضافه)"
            await bot.send_message(
                chat_id=chat_id,
                text=format_insufficient_balance_message(
                    entry_cost=entry_cost,
                    total_balance=total_balance,
                    playable=playable,
                    pending=pending,
                    fee_line=f"{mode_line}{fee_line}",
                ),
                reply_to_message_id=message_id
            )
            remove_player_from_game(chat_id, user_id)
            return False

    err = None
    complete = False
    players: list = []
    players_dice: dict = {}

    with _game_lock(chat_id):
        game = ACTIVE_GAMES.get(chat_id)
        if not game:
            return False

        game = dict(game)
        total = int(game.get("total_players") or 0)
        players = list(game.get("players") or [])[:total]
        game["players"] = players

        if user_id not in players:
            err = "not_in_game"
        else:
            if "players_dice" not in game:
                game["players_dice"] = {}
            if user_id not in game["players_dice"]:
                game["players_dice"][user_id] = dice_value
            game["players_dice"] = {
                pid: game["players_dice"][pid]
                for pid in players
                if pid in game["players_dice"]
            }
            ACTIVE_GAMES[chat_id] = game
            players_dice = dict(game["players_dice"])
            rolled_count = sum(1 for pid in players if pid in players_dice)
            complete = rolled_count >= total

    if err == "not_in_game":
        from bot.helpers import quiet_extra_on
        if not quiet_extra_on(chat_id):
            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ توی این بازی نیستی؛ تاس نریز!",
                reply_to_message_id=message_id,
            )
        return False

    if not complete:
        return True

    from django.core.cache import cache as django_cache
    import time
    finalize_key = f"dice_waiting_finalize_{chat_id}"
    if not django_cache.add(finalize_key, 1, timeout=WAITING_TTL):
        return True

    try:
        max_dice = max(players_dice.values())
        winners = [uid for uid, val in players_dice.items() if val == max_dice]

        user_ids = players
        mention_map = await _bulk_mentions(user_ids, bot, chat_id)

        def safe_name(uid):
            return mention_map.get(uid) or f'<a href="tg://user?id={uid}">بازیکن</a>'

        if len(winners) > 1:
            await bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ تساوی! {len(winners)} نفر امتیاز برابر آوردند.\nلطفاً دوباره بازی را شروع کنید.",
                reply_to_message_id=message_id,
                parse_mode="HTML"
            )
            finish_game_cleanup(chat_id)
            return True

        winner_id = winners[0]
        # اول وضعیت را ثبت کن، بعد پیام بفرست — اگر ارسال fail شود بازی گیر نکند
        WAITING_ROUNDS[chat_id] = winner_id
        with _game_lock(chat_id):
            g = ACTIVE_GAMES.get(chat_id)
            if g:
                g = dict(g)
                g["awaiting_rounds"] = True
                g["expires_at"] = time.time() + max(WAITING_TTL + 60, 180)
                ACTIVE_GAMES[chat_id] = g

        winner_display = safe_name(winner_id)
        lines = ["🎯 ثبت‌نام بازی کامل شد!", "━━━━━━━━━━━━━━━━", "👥 بازیکنان این بازی:", ""]
        for uid in user_ids:
            dice_val = players_dice.get(uid, 0)
            lines.append(f"• {safe_name(uid)}  🎲 {dice_val}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━")
        lines.append(f"✨ نتیجه تعیین: {winner_display} بیشترین تاس را آورد!")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━")
        lines.append(f"{winner_display} عزیز، لطفاً تعداد راندهای بازی را مشخص کن.")
        lines.append("📝 فقط یک عدد بفرست (مثلاً 7 یا 10)")
        lines.append("⏱️ شما ۶۰ ثانیه وقت داری!")

        try:
            await bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                reply_to_message_id=message_id,
                parse_mode="HTML"
            )
        except Exception:
            # وضعیت awaiting ثبت شده؛ یک پیام ساده بدون HTML هم امتحان کن
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "🎯 ثبت‌نام کامل شد!\n"
                        f"برنده تعیین راند: {winner_id}\n"
                        "یک عدد برای تعداد راند بفرستید (مثلاً 7)."
                    ),
                    reply_to_message_id=message_id,
                )
            except Exception:
                pass
        return True
    except Exception:
        # قفل را باز کن تا recover بتواند دوباره تلاش کند
        django_cache.delete(finalize_key)
        raise


async def recover_stuck_registration(chat_id, bot, message_id) -> bool:
    game = get_game(chat_id)
    if not game or game.get("status") != "waiting" or game.get("awaiting_rounds"):
        return False
    if not registration_complete(game):
        return False
    if chat_id in WAITING_ROUNDS:
        return False
    total = int(game.get("total_players") or 0)
    players = list(game.get("players") or [])[:total]
    dice = game.get("players_dice") or {}
    if not players or players[0] not in dice:
        return False
    # اگر قفل finalize هنوز فعال است، finalize در حال اجراست — دخالت نکن
    from django.core.cache import cache as django_cache
    if django_cache.get(f"dice_waiting_finalize_{chat_id}"):
        return False
    await register_and_save_dice(chat_id, players[0], dice[players[0]], bot, message_id)
    return True


async def handle_round_selection(chat_id, user_id, text, bot, message_id):
    if chat_id not in WAITING_ROUNDS:
        return False

    expected_user = WAITING_ROUNDS[chat_id]
    if expected_user != user_id:
        mention_map = await _bulk_mentions([expected_user], bot, chat_id)
        name = mention_map.get(expected_user) or f'<a href="tg://user?id={expected_user}">بازیکن</a>'
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ فقط {name} می‌تواند تعداد راند را تعیین کند!",
            reply_to_message_id=message_id,
            parse_mode="HTML"
        )
        return True

    try:
        rounds_count = int(text)
        if not (1 <= rounds_count <= 1000000000):
            await bot.send_message(chat_id=chat_id, text="❌ تعداد راند باید بین 1 تا یک میلیارد باشد!", reply_to_message_id=message_id)
            return True
    except ValueError:
        return False

    game = get_game(chat_id)
    if not game:
        return False

    game["rounds"] = rounds_count
    game["total_rounds"] = rounds_count
    game["status"] = "playing"
    game["awaiting_rounds"] = False
    import time
    game["expires_at"] = time.time() + PLAYING_TTL

    players_list = game.get("players", [])
    is_two_player = (len(players_list) == 2)
    game["is_turn_based"] = is_two_player

    if is_two_player:
        for player in players_list:
            if player != user_id:
                game["turn"] = player
                break
    else:
        game["turn"] = None

    from bot import cache as bot_cache
    turn_limit = int(bot_cache.DICE_TURN_LIMIT.get(chat_id) or 0)
    game["dice_turn_limit"] = turn_limit

    progress = {}
    for uid in players_list:
        entry = {"total": 0, "remaining": rounds_count}
        if turn_limit > 0:
            entry["actions_left"] = min(turn_limit, rounds_count)
        progress[uid] = entry
    GAME_PROGRESS[chat_id] = progress
    WAITING_ROUNDS.pop(chat_id, None)
    ACTIVE_GAMES[chat_id] = game

    mention_map = await _bulk_mentions(players_list, bot, chat_id)

    def safe_name(uid):
        return mention_map.get(uid) or f'<a href="tg://user?id={uid}">بازیکن</a>'

    limit_line = ""
    if turn_limit > 0:
        limit_line = (
            f"\n📌 محدودیت نوبت تاس: حداکثر {turn_limit}\n"
            f"   می‌توانی زودتر تمام کنی؛ نوبت آخر باید همه باقی‌مانده را بریزی.\n"
        )

    if is_two_player:
        next_player = safe_name(game["turn"])
        await bot.send_message(
            chat_id=chat_id,
            text=(f"🎲 بازی با {rounds_count} راند شروع شد!\n━━━━━━━━━━━━━━━━━━━━\n\n"
                  f"👥 بازیکنان: {len(players_list)} نفر\n"
                  f"🎯 هر بازیکن باید {rounds_count} بار تاس بزند!"
                  f"{limit_line}\n"
                  f"🔁 نوبت اول: {next_player} عزیز\n"
                  f"🎲 لطفاً «تاس» بیندازید."),
            reply_to_message_id=message_id,
            parse_mode="HTML"
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=(f"🎲 بازی با {rounds_count} راند شروع شد!\n━━━━━━━━━━━━━━━━━━━━\n\n"
                  f"👥 بازیکنان: {len(players_list)} نفر\n"
                  f"🎯 هر بازیکن باید {rounds_count} بار تاس بزند!"
                  f"{limit_line}\n"
                  f"💡 همه می‌توانند همزمان تاس بزنند!"),
            reply_to_message_id=message_id,
            parse_mode="HTML"
        )
    return True


_FINALIZE_GUARD: set[int] = set()


async def send_final_results(chat_id, bot, message_id):
    """اعلام نتیجه و بستن بازی — اول نتیجه، بعد پرداخت/چالش تا گیر نکند."""
    cid = int(chat_id)
    if cid in _FINALIZE_GUARD:
        return
    _FINALIZE_GUARD.add(cid)

    game_data = get_game(chat_id)
    progress_src = GAME_PROGRESS.get(chat_id) or GAME_PROGRESS.get(cid) or {}
    if not game_data or not progress_src:
        finish_game_cleanup(chat_id)
        _FINALIZE_GUARD.discard(cid)
        return

    # اسنپ‌شات قبل از پاک‌کردن بازی
    game_snap = dict(game_data)
    progress = {uid: dict(data) for uid, data in progress_src.items()}

    # خیلی مهم: بازی را همین الان ببند تا کسی در وضعیت «تمام راندها» گیر نکند
    finish_game_cleanup(chat_id)

    try:
        if isinstance(game_snap.get("players"), dict):
            players_list = list(game_snap["players"].keys())
        else:
            players_list = list(game_snap.get("players") or [])

        total_rounds = game_snap.get("total_rounds", game_snap.get("rounds", 0))
        results = []
        for uid, data in progress.items():
            total = data.get("total", 0)
            remaining = data.get("remaining", 0)
            count = total_rounds - remaining
            results.append((uid, total, count))

        if not results:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ خطا در دریافت نتایج بازی!",
                reply_to_message_id=message_id,
            )
            return

        results.sort(key=lambda x: x[1], reverse=True)

        user_ids = [r[0] for r in results]
        try:
            mention_map = await asyncio.wait_for(
                _bulk_mentions(user_ids, bot, chat_id), timeout=8,
            )
        except Exception:
            mention_map = {}

        def safe_name(uid):
            return mention_map.get(uid) or f'<a href="tg://user?id={uid}">بازیکن</a>'

        winner_id = None
        winner_display = None
        is_tie = False
        bets_recorded = False
        entry_amount = winner_amount = fee_amount = gross_prize = 0
        bet_mode = _game_bet_mode(game_snap)
        fee_percent = int(game_snap.get("fee_percent") or 0)
        bet_amount = int(game_snap.get("bet_amount") or 0)

        top_score = results[0][1]
        winners_list = [(uid, safe_name(uid)) for uid, total, _ in results if total == top_score]
        if len(winners_list) == 1:
            winner_id, winner_display = winners_list[0]
        else:
            winner_display = " و ".join(d for _, d in winners_list)
            is_tie = True
            winner_id = None

        lines = []
        if winner_display and not is_tie:
            lines.append("🏁 مسابقه تاس تمام شد")
            lines.append(f"🏆 برنده: {winner_display} 🥇")
        else:
            lines.append("🏁 مسابقه تاس به پایان رسید!")
            if is_tie:
                lines.append("⚠️ بازی با تساوی به پایان رسید")
                if _game_has_money_bet(game_snap):
                    lines.append("💰 هیچ مبلغی از کیف پول کسر نشد.")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🏆 نتایج نهایی")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        for i, (uid, total, count) in enumerate(results, start=1):
            display = safe_name(uid)
            medal = "🥇" if i == 1 and not is_tie else ("⭐" if i == 1 else "📌")
            avg = total / count if count > 0 else 0
            lines.append(f"{medal} {i:02}. {display}")
            lines.append(f"   📊 مجموع: {total}")
            lines.append(f"   🎲 تاس: {count}")
            lines.append(f"   📈 میانگین: {avg:.1f}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━")

        # پرداخت قبل از اعلام — تا متن موجودی قطعی باشد
        pay_error = None
        if _game_has_money_bet(game_snap) and not is_tie and winner_id:
            costs = calc_bet_costs(bet_amount, fee_percent, bet_mode, len(players_list))
            entry_amount = costs["entry"]
            winner_amount = costs["winner_total"]
            fee_amount = costs["total_fee"]
            gross_prize = costs["gross_prize"]
            mode_label = "فیکس" if bet_mode == BET_MODE_FIXED else "اضافه"
            lines.append("")
            lines.append("💰 جایزه نقدی")
            lines.append("────────────────────")
            lines.append(f"💳 هزینه ورودی هر نفر: {entry_amount:,} واحد")
            if fee_percent > 0:
                if bet_mode == BET_MODE_FIXED:
                    lines.append(f"💸 حق واسطه ({fee_percent}% از مجموع برد): {fee_amount:,} واحد")
                else:
                    lines.append(f"💸 حق واسطه ({fee_percent}% اضافه): {fee_amount:,} واحد")
            lines.append(f"🏆 مبلغ برد: {winner_amount:,} واحد")

            try:
                pay_err = None
                from bot.finance import allocate_game_no
                game_no = await allocate_game_no(chat_id)
                for attempt in range(1, 4):
                    try:
                        await asyncio.wait_for(
                            settle_dice_game_wallets(
                                chat_id, players_list, entry_amount, winner_id, winner_amount,
                                game_no=game_no,
                            ),
                            timeout=30,
                        )
                        bets_recorded = True
                        pay_err = None
                        break
                    except Exception as attempt_err:
                        pay_err = attempt_err
                        print(f"⚠️ settle attempt {attempt}/3 failed chat={chat_id}: {attempt_err}")
                        await asyncio.sleep(0.4 * attempt)
                if not bets_recorded:
                    raise pay_err or RuntimeError("settle_dice_game_wallets failed")

                starter_id = game_snap.get("starter_admin_id")
                collector_admin_id = None
                if starter_id:
                    from bot.cache_manager import is_owner
                    try:
                        if not is_owner(chat_id, int(starter_id)):
                            collector_admin_id = int(starter_id)
                    except Exception:
                        collector_admin_id = int(starter_id)
                if not collector_admin_id:
                    try:
                        from bot.admin_accounting import active_cashier
                        from bot.cache_manager import is_owner
                        cashier = await active_cashier(chat_id)
                        if cashier and not is_owner(chat_id, int(cashier)):
                            collector_admin_id = int(cashier)
                    except Exception:
                        pass
                if collector_admin_id and fee_amount > 0:
                    try:
                        from bot.admin_accounting import get_admin_share_percent
                        pct = await get_admin_share_percent(chat_id, collector_admin_id)
                    except Exception:
                        pct = 50
                    try:
                        from bot.finance import with_game_id
                        mode_fa = "فیکس" if bet_mode == BET_MODE_FIXED else "اضافه"
                        await record_fee_income(
                            chat_id=chat_id,
                            user_id=int(collector_admin_id),
                            amount=fee_amount,
                            admin_id=int(collector_admin_id),
                            description=with_game_id(f"حق واسطه بازی گروهی ({mode_fa})", game_no),
                        )
                    except Exception as e:
                        print(f"record_fee_income failed: {e}")

                lines.append("")
                lines.append("📊 تغییرات موجودی:")
                for uid in players_list:
                    display = safe_name(uid)
                    if uid == winner_id:
                        lines.append(f"   ✅ {display}: +{winner_amount:,} واحد")
                    else:
                        lines.append(f"   ❌ {display}: -{entry_amount:,} واحد")
            except Exception as e:
                pay_error = e
                import traceback
                print(f"🔴 خطا در پرداخت شرط تاس: {e}")
                traceback.print_exc()
                lines.append("")
                lines.append("⚠️ پرداخت کیف پول با خطا روبه‌رو شد؛ لطفاً موجودی را بررسی کنید.")

        # دکمه‌های افزایش روی نتیجه حذف شد — درخواست افزایش جداگانه در پیوی پس از بازی پیوی
        await bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            reply_to_message_id=message_id,
            parse_mode="HTML",
        )

        if bets_recorded:
            try:
                await asyncio.sleep(1)
                from bot.challenges import flush_challenge_breaks
                await asyncio.wait_for(flush_challenge_breaks(bot, chat_id), timeout=15)
            except Exception:
                pass

        from asgiref.sync import sync_to_async

        @sync_to_async
        def _persist_history():
            import time
            from account.models import DiceGameHistory
            game_session = f"{chat_id}_{int(time.time() * 1000)}"
            has_bet = _game_has_money_bet(game_snap)
            ba = int(game_snap.get("bet_amount") or 0) if has_bet else 0
            ea = wa = 0
            if has_bet:
                costs = calc_bet_costs(
                    ba,
                    int(game_snap.get("fee_percent") or 0),
                    _game_bet_mode(game_snap),
                    len(players_list),
                )
                ea = int(costs["entry"])
                if not is_tie and winner_id:
                    wa = int(costs["winner_total"])
            for uid, total_score, roll_count in results:
                is_w = (uid == winner_id) and not is_tie
                if has_bet and not is_tie and winner_id:
                    amt = (wa - ea) if uid == winner_id else -ea
                else:
                    amt = 0
                avg_val = total_score / roll_count if roll_count > 0 else 0.0
                DiceGameHistory.objects.create(
                    telegram_chat_id=chat_id,
                    telegram_user_id=int(uid),
                    total=int(total_score),
                    average=avg_val,
                    count=int(roll_count),
                    winner=bool(is_w),
                    amount_won=int(amt),
                    # بیشترین شرط = مبلغ ورودی (فیکس/اضافه یکسان)
                    bet_amount=ea if has_bet else 0,
                    game_session=game_session,
                )

        try:
            await asyncio.wait_for(_persist_history(), timeout=20)
        except Exception as e:
            print(f"persist dice history failed: {e}")
    except Exception as e:
        import traceback
        print(f"🔴 خطا در send_final_results: {e}")
        traceback.print_exc()
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ خطا در اعلام نتایج؛ بازی بسته شد. می‌توانید بازی جدید شروع کنید.",
                reply_to_message_id=message_id,
            )
        except Exception:
            pass
    finally:
        finish_game_cleanup(chat_id)
        _FINALIZE_GUARD.discard(cid)


# ─── تولید اعداد تاس (با رعایت تاس متوالی) ─────────────────────────────────

def _generate_dice_numbers(count: int, chat_id: int, dice_option_off: bool):
    results = []
    total = 0
    last = LAST_DICE.get(chat_id)
    for _ in range(count):
        r = secrets.randbelow(6) + 1
        if dice_option_off and last is not None and r == last:
            r = 1 if r == 6 else r + 1
        results.append(r)
        total += r
        last = r
    LAST_DICE[chat_id] = last
    return results, total


def _multinomial_fair(count_):
    freq_ = [0, 0, 0, 0, 0, 0, 0]
    remaining = count_
    for face in range(1, 6):
        faces_left = 7 - face
        p = 1.0 / faces_left
        x = _binomial_approx(remaining, p)
        freq_[face] = x
        remaining -= x
    freq_[6] = remaining
    tmp = freq_[1:]
    random.shuffle(tmp)
    for i in range(6):
        freq_[i + 1] = tmp[i]
    return freq_


# ─── تابع اصلی handle_dice ───────────────────────────────────────────────────

async def handle_dice(text, chat_id, message_id, bot, user_id, dice_option_off, theme_id=1,
                      telegram_emoji_on=False):
    text = text or ""
    theme = get_theme(theme_id)
    separator = theme["separator"]

    # تعیین تعداد تاس
    if text == "تاس":
        dice_count = 1
    elif text.startswith("تاس"):
        match = re.fullmatch(r"تاس\s*([0-9۰-۹٠-٩]+)\s*", text)
        if not match:
            # فقط ورودی عدددارِ بدفرمت را خطا اعلام کن؛ جمله‌هایی مثل
            # «تاس بریز» دستور شمارشی نیستند و باید نادیده گرفته شوند.
            if not any(ch.isdigit() for ch in text[3:]):
                return
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "❌ فرمت دستور تاس اشتباه است.\n\n"
                    "📌 راهنمای فرمت صحیح:\n\n"
                    "1️⃣ تاس + یک فاصله + عدد\n"
                    "✅ تاس 30\n\n"
                    "2️⃣ تاس + عدد\n"
                    "✅ تاس30\n\n"
                    "⚠️ فقط همین دو فرمت قابل قبول هستند.\n"
                    "از گذاشتن فاصله‌های اضافی، رفتن به خط بعد و نوشتن صفر قبل از عدد خودداری کنید."
                ),
                reply_to_message_id=message_id,
            )
            return
        normalized_number = match.group(1).translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        )
        dice_count = int(normalized_number)
        if dice_count <= 0:
            return
        if dice_count > 1_000_000_000:
            dice_count = 1_000_000_000
    else:
        return

    game = get_game(chat_id)

    if game and game.get("status") == "waiting":
        if text == "تاس" and is_game_full(chat_id) and not is_user_in_game(chat_id, user_id):
            from bot.helpers import quiet_extra_on
            if not quiet_extra_on(chat_id):
                await bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ توی این بازی نیستی تاس نریز!!\n",
                    reply_to_message_id=message_id,
                )
            return
        if registration_complete(game) and not game.get("awaiting_rounds"):
            await recover_stuck_registration(chat_id, bot, message_id)

    # چک موجودی برای بازی شرطی در مرحله waiting
    if game and game.get("status") == "waiting" and _game_has_money_bet(game):
        from bot.finance import get_playable_balance, format_insufficient_balance_message

        bet_mode = _game_bet_mode(game)
        fee_percent = game.get("fee_percent", 0)
        bet_amount = game["bet_amount"]
        costs = calc_bet_costs(bet_amount, fee_percent, bet_mode)
        entry_cost = costs["entry"]
        fee_per = costs["fee_per"]
        total_balance, playable, pending = await get_playable_balance(chat_id, user_id)
        if playable < entry_cost:
            if bet_mode == BET_MODE_FIXED and fee_per > 0:
                fee_line = f"\n   └ حق واسطه ({fee_percent}٪): {fee_per:,} واحد (از جایزه)"
            elif fee_per > 0:
                fee_line = f"\n   ├ شرط: {bet_amount:,} واحد\n   └ حق واسطه: {fee_per:,} واحد"
            else:
                fee_line = ""
            mode_line = " (فیکس)" if bet_mode == BET_MODE_FIXED else " (اضافه)"
            await bot.send_message(
                chat_id=chat_id,
                text=format_insufficient_balance_message(
                    entry_cost=entry_cost,
                    total_balance=total_balance,
                    playable=playable,
                    pending=pending,
                    fee_line=f"{mode_line}{fee_line}",
                ),
                reply_to_message_id=message_id
            )
            return

    # چک ثبت‌نام / نوبت
    should_cont, join_note = await should_continue(chat_id, user_id, bot, message_id, text if dice_count == 1 else "تاس")
    if should_cont == 0:
        return

    # بررسی نوبت در بازی playing
    game = get_game(chat_id)
    if game and game.get("status") == "playing":
        allowed, remaining, error_msg = can_player_roll(chat_id, user_id, dice_count)
        if not allowed:
            await bot.send_message(chat_id=chat_id, text=error_msg, reply_to_message_id=message_id)
            return

    # ─── تاس تکی ─────────────────────────────────────────────────────────────
    if dice_count == 1:
        from bot.helpers import db_record_dice_roll, safe_send
        r = None
        if telegram_emoji_on and should_cont != 2:
            try:
                sent = await bot.send_dice(chat_id, emoji="🎲", reply_to_message_id=message_id)
                r = sent.dice.value
            except Exception:
                r = None
        if r is None:
            r = roll_dice(chat_id, dice_option_off)
            msg = build_single_dice_message(r, theme)
            if join_note:
                msg += join_note
            try:
                await safe_send(bot, chat_id, msg, reply_to=message_id)
            except Exception:
                # ارسال نمایشی fail شد؛ ثبت تاس تعیین نباید متوقف شود
                pass
        LAST_DICE[chat_id] = r
        try:
            await db_record_dice_roll(chat_id, user_id, r)
        except Exception:
            pass
        try:
            from bot.challenges import notify_fun_game
            from bot.game_text import race_result_caption
            await notify_fun_game(
                bot, chat_id, user_id, "dice", int(r),
                reply_to=message_id,
                result_text=race_result_caption("dice", int(r)),
                attach_result_only_on_win=True,
            )
        except Exception:
            pass

        game = get_game(chat_id)
        if game and game.get("status") == "playing":
            await _handle_game_roll_silent(chat_id, user_id, 1, r, message_id, bot)
            return

        if should_cont == 2:
            # اول تاس دیده شود، بعد پیام ثبت‌نام کامل
            await asyncio.sleep(0.4)
            try:
                await register_and_save_dice(chat_id, user_id, r, bot, message_id)
            except Exception:
                # یک‌بار دیگر تلاش برای جلوگیری از جوین بدون تاس تعیین
                try:
                    await register_and_save_dice(chat_id, user_id, r, bot, message_id)
                except Exception:
                    pass
        return

    # ─── تاس چندتایی ────────────────────────────────────────────────────────
    game = get_game(chat_id)

    if dice_count <= 30:
        results, total = _generate_dice_numbers(dice_count, chat_id, dice_option_off)
        msg = build_multi_dice_message(results, total, dice_count, theme)

        if game and game.get("status") == "playing":
            await _handle_game_roll(chat_id, user_id, dice_count, total, msg, message_id, bot)
            return

        await bot.send_message(chat_id=chat_id, text=msg, reply_to_message_id=message_id, parse_mode="HTML")

    else:
        # تاس آماری برای تعداد زیاد (> 30)
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
            "💡 هرچه تعداد تاس بیشتر باشد، نتیجه‌ها یکنواخت‌تر می‌شوند."
        ))

        if game and game.get("status") == "playing":
            await _handle_game_roll(chat_id, user_id, dice_count, total, msg, message_id, bot)
            return

        await bot.send_message(chat_id=chat_id, text=msg, reply_to_message_id=message_id, parse_mode="HTML")


async def _handle_game_roll(chat_id, user_id, dice_count, total, msg, message_id, bot):
    finished, total_score, rem = save_roll_result(chat_id, user_id, dice_count, total)

    if finished:
        msg += f"\n\n━━━━━━━━━━━━━━━━\n✅ راندهای شما تمام شد!\n📊 امتیاز نهایی شما: {total_score}\n⏳ منتظر پایان بازی بازیکنان دیگر..."
    elif rem > 0:
        msg += f"\n\n━━━━━━━━━━━━━━━━\n🎯 {rem} راند دیگر باقی مانده\n📊 امتیاز فعلی: {total_score}"
    else:
        msg += f"\n\n━━━━━━━━━━━━━━━━\n✅ راندهای شما تمام شد!\n📊 امتیاز نهایی شما: {total_score}\n⏳ منتظر پایان بازی بازیکنان دیگر..."

    await bot.send_message(chat_id=chat_id, text=msg, reply_to_message_id=message_id, parse_mode="HTML")

    if finished:
        await asyncio.sleep(1)
        await send_final_results(chat_id, bot, message_id)
        return

    game = get_game(chat_id)
    if game and game.get("is_turn_based") and game.get("turn") and game["turn"] != user_id:
        mention_map = await _bulk_mentions([game["turn"]], bot, chat_id)
        next_player = mention_map.get(game["turn"]) or f'<a href="tg://user?id={game["turn"]}">بازیکن بعدی</a>'
        await bot.send_message(
            chat_id=chat_id,
            text=f"🔁 نوبت {next_player} است!\n🎲 لطفاً «تاس» بیندازید.",
            reply_to_message_id=message_id,
            parse_mode="HTML"
        )


async def _handle_game_roll_silent(chat_id, user_id, dice_count, total, message_id, bot):
    """مثل _handle_game_roll ولی بدون ارسال متن تاس — فقط نتیجه ثبت و اعلام وضعیت"""
    finished, total_score, rem = save_roll_result(chat_id, user_id, dice_count, total)

    if finished:
        status = f"✅ راندهای شما تمام شد!\n📊 امتیاز نهایی شما: {total_score}\n⏳ منتظر پایان بازی بازیکنان دیگر..."
        await bot.send_message(chat_id=chat_id, text=status, reply_to_message_id=message_id)
        await asyncio.sleep(1)
        await send_final_results(chat_id, bot, message_id)
        return

    if rem > 0:
        await bot.send_message(
            chat_id=chat_id,
            text=f"🎯 {rem} راند دیگر باقی مانده\n📊 امتیاز فعلی: {total_score}",
            reply_to_message_id=message_id,
        )

    game = get_game(chat_id)
    if game and game.get("is_turn_based") and game.get("turn") and game["turn"] != user_id:
        mention_map = await _bulk_mentions([game["turn"]], bot, chat_id)
        next_player = mention_map.get(game["turn"]) or f'<a href="tg://user?id={game["turn"]}">بازیکن بعدی</a>'
        await bot.send_message(
            chat_id=chat_id,
            text=f"🔁 نوبت {next_player} است!\n🎲 لطفاً «تاس» بیندازید.",
            reply_to_message_id=message_id,
            parse_mode="HTML"
        )


# ─── helpers داخلی ────────────────────────────────────────────────────────────

async def _bulk_mentions(user_ids: list, bot, chat_id: int) -> dict:
    import html as _html
    result = {}
    for uid in user_ids:
        try:
            member = await bot.get_chat_member(chat_id, uid)
            name = member.user.full_name or str(uid)
            result[uid] = f'<a href="tg://user?id={uid}">{_html.escape(name)}</a>'
        except Exception:
            result[uid] = f'<a href="tg://user?id={uid}">{uid}</a>'
    return result


from bot.finance import get_balance, record_game_bet, record_game_win, record_fee_income, settle_dice_game_wallets
