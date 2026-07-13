"""
سیستم بازی تاس — پورت کامل از rubpy/bot/dice.py و rubpy/bot/func.py
"""
import asyncio
import math
import random
import secrets
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
    return ACTIVE_GAMES.get(chat_id)


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


def is_user_in_game(chat_id, user_id) -> bool:
    game = get_game(chat_id)
    if not game:
        return False
    return user_id in game.get("players", [])


def add_player_to_game(chat_id, user_id):
    game = get_game(chat_id)
    if not game:
        return False, "بازی فعالی وجود ندارد"
    if len(game["players"]) >= game["total_players"]:
        return False, "تعداد بازیکن‌ها پر شده است"
    if user_id in game["players"]:
        return False, "این کاربر قبلاً ثبت نام کرده است"
    game["players"].append(user_id)
    return True, "بازیکن اضافه شد"


def finish_game_cleanup(chat_id):
    delete_game(chat_id)


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

async def should_continue(chat_id, user_id, bot, message_id, text):
    """
    0 = نده (کاربر در بازی است یا بازی پر)
    1 = تاس عادی بریز
    2 = تازه ثبت نام شد، تاسش رو ثبت کن
    """
    if not has_active_game(chat_id):
        return 1

    if is_user_in_game(chat_id, user_id):
        game = get_game(chat_id)
        if chat_id in WAITING_ROUNDS:
            await bot.send_message(
                chat_id=chat_id,
                text="⏳ منتظر بمان... باید اول راند تعیین شه!",
                reply_to_message_id=message_id
            )
            return 0
        if game and game.get("status") == "waiting":
            await bot.send_message(
                chat_id=chat_id,
                text="✅ شما در بازی ثبت‌نام کرده‌اید. منتظر بقیه بازیکنان...",
                reply_to_message_id=message_id
            )
            return 0
        return 1

    if is_game_full(chat_id):
        await bot.send_message(
            chat_id=chat_id,
            text="⚠️ توی این بازی نیستی تاس نریز!!\n",
            reply_to_message_id=message_id
        )
        return 0

    if text != "تاس":
        await bot.send_message(
            chat_id=chat_id,
            text="⚠️ لطفا برای تعیین فقط از دستور تاس استفاده کنید بدون عدد !",
            reply_to_message_id=message_id
        )
        return 0

    success, message = add_player_to_game(chat_id, user_id)
    if not success:
        await bot.send_message(chat_id=chat_id, text=f"⚠️ {message}", reply_to_message_id=message_id)
        return 0

    remaining = get_remaining_players(chat_id)
    await bot.send_message(
        chat_id=chat_id,
        text=f"✅ كاربر به بازی پیوست!\n📌 {remaining} نفر دیگر نیاز است." if remaining > 0
             else f"🎯 بازی کامل شد!\n🎲 بازی در حال شروع...",
        reply_to_message_id=message_id
    )
    return 2


# ─── ثبت تاس در مرحله waiting (تعیین برنده برای راند) ───────────────────────

async def register_and_save_dice(chat_id, user_id, dice_value, bot, message_id):
    game = get_game(chat_id)
    if not game:
        return False

    if user_id not in game["players"]:
        game["players"].append(user_id)

    game["players_dice"][user_id] = dice_value
    current_players = len(game["players"])
    remaining = game["total_players"] - current_players

    if remaining > 0:
        return True

    # همه ثبت نام کردند → تعیین برنده
    max_dice = max(game["players_dice"].values())
    winners = [uid for uid, val in game["players_dice"].items() if val == max_dice]

    user_ids = game["players"]
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
        delete_game(chat_id)
        return True

    winner_id = winners[0]
    winner_display = safe_name(winner_id)

    lines = ["🎯 ثبت‌نام بازی کامل شد!", "━━━━━━━━━━━━━━━━", "👥 بازیکنان این بازی:", ""]
    for uid in user_ids:
        dice_val = game["players_dice"].get(uid, 0)
        lines.append(f"• {safe_name(uid)}  🎲 {dice_val}")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append(f"✨ نتیجه تعیین: {winner_display} بیشترین تاس را آورد!")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append(f"{winner_display} عزیز، لطفاً تعداد راندهای بازی را مشخص کن.")
    lines.append("📝 فقط یک عدد بفرست (مثلاً 7 یا 10)")
    lines.append("⏱️ شما ۶۰ ثانیه وقت داری!")

    await bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        reply_to_message_id=message_id,
        parse_mode="HTML"
    )
    WAITING_ROUNDS[chat_id] = winner_id
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


async def send_final_results(chat_id, bot, message_id):
    lock_key = f"_dice_finalizing_{chat_id}"
    # جلوگیری از ارسال دوبار نتایج در race
    if ACTIVE_GAMES.get(chat_id, {}).get(lock_key):
        return
    game_lock = get_game(chat_id)
    if game_lock is not None:
        game_lock[lock_key] = True

    await asyncio.sleep(0.5)
    game_data = get_game(chat_id)
    if not game_data:
        finish_game_cleanup(chat_id)
        return

    progress = GAME_PROGRESS.get(chat_id, {})
    if not progress:
        try:
            await bot.send_message(chat_id=chat_id, text="❌ خطا در دریافت نتایج بازی!", reply_to_message_id=message_id)
        finally:
            finish_game_cleanup(chat_id)
        return

    try:
        if isinstance(game_data.get("players"), dict):
            players_list = list(game_data["players"].keys())
        else:
            players_list = game_data.get("players", [])

        total_rounds = game_data.get("total_rounds", game_data.get("rounds", 0))
        results = []
        for uid, data in progress.items():
            total = data.get("total", 0)
            remaining = data.get("remaining", 0)
            count = total_rounds - remaining
            results.append((uid, total, count))

        results.sort(key=lambda x: x[1], reverse=True)

        user_ids = [r[0] for r in results]
        mention_map = await _bulk_mentions(user_ids, bot, chat_id)

        def safe_name(uid):
            return mention_map.get(uid) or f'<a href="tg://user?id={uid}">بازیکن</a>'

        winner_id = None
        winner_display = None
        is_tie = False

        if results:
            top_score = results[0][1]
            winners_list = [(uid, safe_name(uid)) for uid, total, _ in results if total == top_score]
            if len(winners_list) == 1:
                winner_id, winner_display = winners_list[0]
                is_tie = False
            else:
                winner_display = " و ".join(d for _, d in winners_list)
                is_tie = True
                winner_id = None

        # پرداخت شرط
        if _game_has_money_bet(game_data) and not is_tie and winner_id:
            bet_amount = game_data["bet_amount"]
            fee_percent = game_data.get("fee_percent", 0)
            bet_mode = _game_bet_mode(game_data)
            costs = calc_bet_costs(bet_amount, fee_percent, bet_mode, len(players_list))
            entry_amount = costs["entry"]
            winner_amount = costs["winner_total"]
            for player_id in players_list:
                await record_game_bet(chat_id, player_id, entry_amount)
            await record_game_win(chat_id, winner_id, winner_amount)
            collector_admin_id = game_data.get("starter_admin_id")
            if collector_admin_id and costs.get("total_fee", 0) > 0:
                await record_fee_income(
                    chat_id=chat_id,
                    user_id=int(collector_admin_id),
                    amount=int(costs["total_fee"]),
                    admin_id=int(collector_admin_id),
                    description=f"حق واسطه مسابقه تاس ({'فیکس' if bet_mode == BET_MODE_FIXED else 'اضافه'})",
                )

        lines = []
        if winner_display and not is_tie:
            lines.append(f"🏁 مسابقه تاس تمام شد")
            lines.append(f"🏆 برنده: {winner_display} 🥇")
        else:
            lines.append("🏁 مسابقه تاس به پایان رسید!")
            if is_tie:
                lines.append("⚠️ بازی با تساوی به پایان رسید")
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

        if _game_has_money_bet(game_data) and not is_tie and winner_id:
            bet_amount = game_data["bet_amount"]
            fee_percent = game_data.get("fee_percent", 0)
            bet_mode = _game_bet_mode(game_data)
            costs = calc_bet_costs(bet_amount, fee_percent, bet_mode, len(players_list))
            entry_amount = costs["entry"]
            winner_amount = costs["winner_total"]
            fee_amount = costs["total_fee"]
            gross_prize = costs["gross_prize"]

            lines.append("")
            lines.append("💰 جایزه نقدی")
            lines.append("────────────────────")
            mode_label = "فیکس" if bet_mode == BET_MODE_FIXED else "اضافه"
            lines.append(f"💳 ورودی هر نفر: {entry_amount:,} واحد ({mode_label})")
            if fee_percent > 0:
                lines.append(f"💰 جمع ورودی‌ها: {gross_prize:,} واحد")
                lines.append(f"💸 حق واسطه ({fee_percent}%): {fee_amount:,} واحد")
            if bet_mode == BET_MODE_FIXED and fee_percent > 0:
                lines.append(f"🏆 برد برنده: {winner_amount:,} واحد  ({gross_prize:,} − {fee_amount:,})")
            else:
                lines.append(f"🏆 برد برنده: {winner_amount:,} واحد")
            lines.append("")
            lines.append("📊 تغییرات موجودی:")
            for uid in players_list:
                display = safe_name(uid)
                if uid == winner_id:
                    lines.append(f"   ✅ {display}: +{winner_amount:,} واحد")
                else:
                    lines.append(f"   ❌ {display}: -{entry_amount:,} واحد")

        await bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            reply_to_message_id=message_id,
            parse_mode="HTML"
        )
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
    text = (text or "").strip()
    theme = get_theme(theme_id)
    separator = theme["separator"]

    # تعیین تعداد تاس
    if text == "تاس":
        dice_count = 1
    elif text.startswith("تاس"):
        arg = text[3:].strip()
        if not arg.isdigit():
            return
        dice_count = int(arg)
        if dice_count <= 0:
            return
        if dice_count > 1_000_000_000:
            dice_count = 1_000_000_000
    else:
        return

    game = get_game(chat_id)

    # چک موجودی برای بازی شرطی در مرحله waiting
    if game and game.get("status") == "waiting" and _game_has_money_bet(game):
        bet_mode = _game_bet_mode(game)
        fee_percent = game.get("fee_percent", 0)
        bet_amount = game["bet_amount"]
        costs = calc_bet_costs(bet_amount, fee_percent, bet_mode)
        entry_cost = costs["entry"]
        fee_per = costs["fee_per"]
        balance = await get_balance(chat_id, user_id)
        if balance < entry_cost:
            if bet_mode == BET_MODE_FIXED and fee_per > 0:
                fee_line = f"\n   └ حق واسطه ({fee_percent}٪): {fee_per:,} واحد (از جایزه)"
            elif fee_per > 0:
                fee_line = f"\n   ├ شرط: {bet_amount:,} واحد\n   └ حق واسطه: {fee_per:,} واحد"
            else:
                fee_line = ""
            mode_line = " (فیکس)" if bet_mode == BET_MODE_FIXED else " (اضافه)"
            await bot.send_message(
                chat_id=chat_id,
                text=(f"❌ موجودی ناکافی!\n\n"
                      f"💳 هزینه ورودی: {entry_cost:,} واحد{mode_line}{fee_line}\n\n"
                      f"💰 موجودی فعلی شما: {balance:,} واحد\n"
                      f"🔻 کمبود: {entry_cost - balance:,} واحد\n\n"
                      f"💡 برای افزایش موجودی با ادمین تماس بگیرید."),
                reply_to_message_id=message_id
            )
            return

    # چک ثبت‌نام / نوبت
    should_cont = await should_continue(chat_id, user_id, bot, message_id, text if dice_count == 1 else "تاس")
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
        if telegram_emoji_on:
            sent = await bot.send_dice(chat_id, emoji="🎲", reply_to_message_id=message_id)
            r = sent.dice.value
        else:
            r = roll_dice(chat_id, dice_option_off)
            msg = build_single_dice_message(r, theme)
            await safe_send(bot, chat_id, msg, reply_to=message_id)
        LAST_DICE[chat_id] = r
        await db_record_dice_roll(chat_id, user_id, r)

        game = get_game(chat_id)
        if game and game.get("status") == "playing":
            await _handle_game_roll_silent(chat_id, user_id, 1, r, message_id, bot)
            return

        if should_cont == 2:
            await asyncio.sleep(0.5)
            await register_and_save_dice(chat_id, user_id, r, bot, message_id)
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


from bot.finance import get_balance, record_game_bet, record_game_win, record_fee_income
