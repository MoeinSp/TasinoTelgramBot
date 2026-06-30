"""
سیستم بازی تاس — پورت کامل از rubpy/bot/dice.py و rubpy/bot/func.py
"""
import asyncio
import math
import random
import secrets
from typing import Optional

import jdatetime

# ─── تم‌های تاس (15 تم) ─────────────────────────────────────────────────────

THEMES = {
    1: {
        "name": "classic",
        "single_header": "<blockquote>تـاس انداخته شـد عدد ↻  : {value} 🎲</blockquote>",
        "multi_header": "<blockquote>🎲 تاس × {count}</blockquote>",
        "separator": "•─────✧─────•",
        "footer": "\n<blockquote>محاسبـه کـل ↻ : {total} 🎲</blockquote>",
        "faces": {1: "⬤", 2: "⬤ ⬤", 3: "⬤ ⬤\n  ⬤", 4: "⬤ ⬤\n⬤ ⬤", 5: "⬤ ⬤\n  ⬤\n⬤ ⬤", 6: "⬤ ⬤\n⬤ ⬤\n⬤ ⬤"}
    },
    2: {
        "name": "cinema",
        "single_header": "🎬 عدد شانس: {value}",
        "multi_header": "🎬 DICE × {count}",
        "separator": "🎞️━━━━━━━━━━━━━━🎞️",
        "footer": "\n🎬 TOTAL = {total}",
        "faces": {1: "■", 2: "■     ■", 3: "■     ■\n    ■", 4: "■     ■\n■     ■", 5: "■     ■\n    ■\n■     ■", 6: "■     ■\n■     ■\n■     ■"}
    },
    3: {
        "name": "kingdom",
        "single_header": "<blockquote>𒆙 ↻  عدد : {value} 🎲</blockquote>",
        "multi_header": "<blockquote>🎲 𒆜 DICES × {count}</blockquote>",
        "separator": "⌬⌬⌬⌬⌬⌬⌬⌬",
        "footer": "\n<blockquote>⌬ ﹝{total}﹞;</blockquote>",
        "faces": {1: "𒊹", 2: "𒊹 𒊹", 3: "𒊹 𒊹\n  𒊹", 4: "𒊹 𒊹\n𒊹 𒊹", 5: "𒊹 𒊹\n  𒊹\n𒊹 𒊹", 6: "𒊹 𒊹\n𒊹 𒊹\n𒊹 𒊹"}
    },
    4: {
        "name": "soft_emoji",
        "single_header": "🌈 نتیجه: {value}",
        "multi_header": "🌈 {count} تاس رنگی",
        "separator": "🌸🌸🌸🌸🌸",
        "footer": "\n🌈 مجموع: {total}",
        "faces": {1: "✨", 2: "✨ ✨", 3: "✨ ✨\n   ✨", 4: "✨ ✨\n✨ ✨", 5: "✨ ✨\n   ✨\n✨ ✨", 6: "✨ ✨\n✨ ✨\n✨ ✨"}
    },
    5: {
        "name": "minimal_dot",
        "single_header": "⌬ تـاس انداخته شـد عدد ↻  : {value} ",
        "multi_header": "⌬ تاس × {count}",
        "separator": "⌬⌬⌬⌬⌬⌬⌬⌬",
        "footer": "⌬\nمحاسبـه کـل ↻ : {total} ",
        "faces": {1: "▰", 2: "▰   ▰", 3: "▰   ▰\n  ▰", 4: "▰   ▰\n▰   ▰", 5: "▰   ▰\n  ▰\n▰   ▰", 6: "▰   ▰\n▰   ▰\n▰   ▰"}
    },
    6: {
        "name": "crystal",
        "single_header": "💎 کریستال ↻ {value}",
        "multi_header": "💎 CRYSTAL × {count}",
        "separator": "◆◇◆◇◆◇◆◇◆",
        "footer": "\n💎 مجموع: {total}",
        "faces": {1: "◆", 2: "◆     ◆", 3: "◆     ◆\n    ◆", 4: "◆     ◆\n◆     ◆", 5: "◆     ◆\n    ◆\n◆     ◆", 6: "◆     ◆\n◆     ◆\n◆     ◆"}
    },
    7: {
        "name": "samurai",
        "single_header": "⚔️ ضربه: {value}",
        "multi_header": "⚔️ ضربه‌ها × {count}",
        "separator": "⛩️⛩️⛩️⛩️⛩️",
        "footer": "\n⛩️ مجموع: {total}",
        "faces": {1: "卍", 2: "卍 卍", 3: "卍 卍\n  卍", 4: "卍 卍\n卍 卍", 5: "卍 卍\n  卍\n卍 卍", 6: "卍 卍\n卍 卍\n卍 卍"}
    },
    8: {
        "name": "grid",
        "single_header": "□ تاس: {value}",
        "multi_header": "□ × {count}",
        "separator": "□□□□□□□□□□",
        "footer": "\n□ مجموع: {total}",
        "faces": {1: "●", 2: "●   ●", 3: "●   ●\n   ●", 4: "●   ●\n●   ●", 5: "●   ●\n   ●\n●   ●", 6: "●   ●\n●   ●\n●   ●"}
    },
    9: {
        "name": "thunder",
        "single_header": "⚡ رعد ↻ {value}",
        "multi_header": "⚡ THUNDER × {count}",
        "separator": "•─────⚡─────•",
        "footer": "\n⚡ قدرت: {total}",
        "faces": {1: "⚡", 2: "⚡     ⚡", 3: "⚡     ⚡\n    ⚡", 4: "⚡     ⚡\n⚡     ⚡", 5: "⚡     ⚡\n    ⚡\n⚡     ⚡", 6: "⚡     ⚡\n⚡     ⚡\n⚡     ⚡"}
    },
    10: {
        "name": "alchemy",
        "single_header": "⚗️ کیمیا ↻ {value}",
        "multi_header": "⚗️ ALCHEMY × {count}",
        "separator": "•─────✧─────•",
        "footer": "\n⚗️ نتیجه نهایی: {total}",
        "faces": {1: "⟠", 2: "⟠     ⟠", 3: "⟠     ⟠\n    ⟠", 4: "⟠     ⟠\n⟠     ⟠", 5: "⟠     ⟠\n    ⟠\n⟠     ⟠", 6: "⟠     ⟠\n⟠     ⟠\n⟠     ⟠"}
    },
    11: {
        "name": "rose",
        "single_header": "🌹 رز ↻ {value} 🎲",
        "multi_header": "🌹 ROSE × {count}",
        "separator": "•─────🌹─────•",
        "footer": "\n🌹 مجموع: {total}",
        "faces": {1: "   ✿", 2: "✿   ✿", 3: "✿   ✿\n   ✿", 4: "✿   ✿\n✿   ✿", 5: "✿   ✿\n   ✿\n✿   ✿", 6: "✿   ✿\n✿   ✿\n✿   ✿"}
    },
    12: {
        "name": "forest",
        "single_header": "🌿 جنگل ↻ {value}",
        "multi_header": "🌿 FOREST × {count}",
        "separator": "•─────🌿─────•",
        "footer": "\n🌿 مجموع: {total}",
        "faces": {1: "❇", 2: "❇   ❇", 3: "❇   ❇\n    ❇", 4: "❇   ❇\n❇   ❇", 5: "❇   ❇\n    ❇\n❇   ❇", 6: "❇   ❇\n❇   ❇\n❇   ❇"}
    },
    13: {
        "name": "gold",
        "single_header": "👑 طلایی ↻ {value}",
        "multi_header": "👑 GOLD × {count}",
        "separator": "•─────👑─────•",
        "footer": "\n👑 مجموع: {total}",
        "faces": {1: "✦", 2: "✦   ✦", 3: "✦   ✦\n    ✦", 4: "✦   ✦\n✦   ✦", 5: "✦   ✦\n    ✦\n✦   ✦", 6: "✦   ✦\n✦   ✦\n✦   ✦"}
    },
    14: {
        "name": "skull",
        "single_header": "☠️ جمجمه ↻ {value}",
        "multi_header": "☠️ SKULL × {count}",
        "separator": "•─────🏴‍☠️─────•",
        "footer": "\n☠️ کــــیــــل ⟪{total}⟫",
        "faces": {1: "☠️", 2: "☠️   ☠️", 3: "☠️   ☠️\n    ☠️", 4: "☠️   ☠️\n☠️   ☠️", 5: "☠️   ☠️\n    ☠️\n☠️   ☠️", 6: "☠️   ☠️\n☠️   ☠️\n☠️   ☠️"}
    },
    15: {
        "name": "dragon_gate",
        "single_header": "<blockquote>🐉 دروازه اژدها: {value}</blockquote>",
        "multi_header": "<blockquote>🐉 عبور از دروازه × {count}</blockquote>",
        "separator": "•─────✧─────•",
        "footer": "\n<blockquote>🐲 نیروی کل: {total}</blockquote>",
        "faces": {1: "龙", 2: "龙  龙", 3: "龙  龙\n   龙", 4: "龙  龙\n龙  龙", 5: "龙  龙\n   龙\n龙  龙", 6: "龙  龙\n龙  龙\n龙  龙"}
    },
}

# ─── حافظه بازی‌ها (in-memory) ───────────────────────────────────────────────

ACTIVE_GAMES: dict = {}
GAME_PROGRESS: dict = {}
LAST_DICE: dict = {}
WAITING_ROUNDS: dict = {}  # chat_id → winner_id (منتظر انتخاب راند)


# ─── توابع مدیریت بازی ───────────────────────────────────────────────────────

def create_game(chat_id, total_players, bet_amount=0, fee_percent=0, has_bet=False):
    game = {
        "chat_id": chat_id,
        "total_players": total_players,
        "players": [],
        "players_dice": {},
        "status": "waiting",
        "has_bet": has_bet,
        "bet_amount": bet_amount,
        "fee_percent": fee_percent,
        "rounds": 0,
        "total_rounds": 0,
        "is_turn_based": False,
        "turn": None,
        "players_rolls": {},
    }
    ACTIVE_GAMES[chat_id] = game
    return game


def get_game(chat_id) -> Optional[dict]:
    return ACTIVE_GAMES.get(chat_id)


def delete_game(chat_id):
    ACTIVE_GAMES.pop(chat_id, None)
    GAME_PROGRESS.pop(chat_id, None)
    WAITING_ROUNDS.pop(chat_id, None)


def has_active_game(chat_id) -> bool:
    return chat_id in ACTIVE_GAMES


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


def build_single_dice_message(r: int, theme: dict) -> str:
    return theme["single_header"].format(value=r) + "\n" + theme["faces"][r]


def build_multi_dice_message(results: list, total: int, count: int, theme: dict) -> str:
    separator = theme["separator"]
    lines = [theme["multi_header"].format(count=count), ""]
    for i, r in enumerate(results):
        lines.append(theme["faces"][r])
        if i != count - 1:
            lines.append(separator)
    lines.append(theme["footer"].format(total=total))
    return "\n".join(lines)


# ─── مدیریت راند و امتیاز ────────────────────────────────────────────────────

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
    if finished:
        game["status"] = "finished"

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

    progress = {}
    for uid in players_list:
        progress[uid] = {"total": 0, "remaining": rounds_count}
    GAME_PROGRESS[chat_id] = progress
    WAITING_ROUNDS.pop(chat_id, None)

    mention_map = await _bulk_mentions(players_list, bot, chat_id)

    def safe_name(uid):
        return mention_map.get(uid) or f'<a href="tg://user?id={uid}">بازیکن</a>'

    if is_two_player:
        next_player = safe_name(game["turn"])
        await bot.send_message(
            chat_id=chat_id,
            text=(f"🎲 بازی با {rounds_count} راند شروع شد!\n━━━━━━━━━━━━━━━━━━━━\n\n"
                  f"👥 بازیکنان: {len(players_list)} نفر\n"
                  f"🎯 هر بازیکن باید {rounds_count} بار تاس بزند!\n\n"
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
                  f"🎯 هر بازیکن باید {rounds_count} بار تاس بزند!\n\n"
                  f"💡 همه می‌توانند همزمان تاس بزنند!"),
            reply_to_message_id=message_id,
            parse_mode="HTML"
        )
    return True


async def send_final_results(chat_id, bot, message_id):
    await asyncio.sleep(0.5)
    game_data = get_game(chat_id)
    if not game_data:
        return

    progress = GAME_PROGRESS.get(chat_id, {})
    if not progress:
        await bot.send_message(chat_id=chat_id, text="❌ خطا در دریافت نتایج بازی!", reply_to_message_id=message_id)
        finish_game_cleanup(chat_id)
        return

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
    if game_data.get("has_bet") and game_data.get("bet_amount", 0) > 0 and not is_tie and winner_id:
        bet_amount = game_data["bet_amount"]
        fee_percent = game_data.get("fee_percent", 0)
        fee_per_player = int(bet_amount * fee_percent / 100)
        entry_amount = bet_amount + fee_per_player
        winner_amount = bet_amount * len(players_list)

        for player_id in players_list:
            await _decrease_wallet(chat_id, player_id, entry_amount)
        await _increase_wallet(chat_id, winner_id, winner_amount)

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

    if game_data.get("has_bet") and game_data.get("bet_amount", 0) > 0 and not is_tie and winner_id:
        bet_amount = game_data["bet_amount"]
        fee_percent = game_data.get("fee_percent", 0)
        fee_per_player = int(bet_amount * fee_percent / 100)
        entry_amount = bet_amount + fee_per_player
        winner_amount = bet_amount * len(players_list)
        fee_amount = fee_per_player * len(players_list)

        lines.append("")
        lines.append("💰 جایزه نقدی")
        lines.append("────────────────────")
        lines.append(f"💳 هزینه ورودی هر نفر: {entry_amount:,} واحد")
        if fee_percent > 0:
            lines.append(f"💸 حق واسطه ({fee_percent}%): {fee_amount:,} واحد")
        lines.append(f"🏆 مبلغ برد: {winner_amount:,} واحد")
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

async def handle_dice(text, chat_id, message_id, bot, user_id, dice_option_off, theme_id=1):
    text = (text or "").strip()
    theme = THEMES.get(theme_id, THEMES[1])
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
    if game and game.get("status") == "waiting" and game.get("has_bet") and game.get("bet_amount", 0) > 0:
        bet_amount = game["bet_amount"]
        fee_percent = game.get("fee_percent", 0)
        fee_per = int(bet_amount * fee_percent / 100)
        entry_cost = bet_amount + fee_per
        balance = await _get_balance(chat_id, user_id)
        if balance < entry_cost:
            fee_line = f"\n   ├ شرط: {bet_amount:,} واحد\n   └ حق واسطه: {fee_per:,} واحد" if fee_per > 0 else ""
            await bot.send_message(
                chat_id=chat_id,
                text=(f"❌ موجودی ناکافی!\n\n"
                      f"💳 هزینه ورودی: {entry_cost:,} واحد{fee_line}\n\n"
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

    # ─── تاس تکی — native Telegram dice sticker ─────────────────────────────
    if dice_count == 1:
        sent = await bot.send_dice(chat_id, emoji="🎲", reply_to_message_id=message_id)
        r = sent.dice.value
        LAST_DICE[chat_id] = r
        from bot.helpers import db_record_dice_roll
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
    result = {}
    for uid in user_ids:
        try:
            member = await bot.get_chat_member(chat_id, uid)
            name = member.user.full_name or str(uid)
            result[uid] = f'<a href="tg://user?id={uid}">{name}</a>'
        except Exception:
            result[uid] = f'<a href="tg://user?id={uid}">{uid}</a>'
    return result


async def _get_balance(chat_id, user_id):
    from asgiref.sync import sync_to_async
    @sync_to_async
    def _q():
        from account.models import TelegramGroupMember
        try:
            m = TelegramGroupMember.objects.get(telegram_chat_id=chat_id, telegram_user_id=user_id)
            return getattr(m, 'balance', 0) or 0
        except Exception:
            return 0
    return await _q()


async def _increase_wallet(chat_id, user_id, amount):
    from asgiref.sync import sync_to_async
    @sync_to_async
    def _q():
        from account.models import TelegramGroupMember
        m, _ = TelegramGroupMember.objects.get_or_create(telegram_chat_id=chat_id, telegram_user_id=user_id, defaults={"role": "member"})
        m.balance = (getattr(m, 'balance', 0) or 0) + amount
        m.save(update_fields=["balance"])
    await _q()


async def _decrease_wallet(chat_id, user_id, amount):
    from asgiref.sync import sync_to_async
    @sync_to_async
    def _q():
        from account.models import TelegramGroupMember
        m, _ = TelegramGroupMember.objects.get_or_create(telegram_chat_id=chat_id, telegram_user_id=user_id, defaults={"role": "member"})
        m.balance = (getattr(m, 'balance', 0) or 0) - amount
        m.save(update_fields=["balance"])
    await _q()
