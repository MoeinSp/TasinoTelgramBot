"""
بازی‌های متنی — ساختار مشابه rubpy/bot/func.py
پیش‌فرض: بدون استیکر/ایموجی متحرک تلگرام

توابع build_* فقط متن+امتیاز می‌سازند (ارسال نمی‌کنند)
تا با اعلام برد چالش در یک پیام ادغام شوند.
"""
import secrets

from bot.helpers import safe_send

_SEP = "━━━━━━━━━━━━"


def _roll(lo: int, hi: int) -> int:
    return secrets.randbelow(hi - lo + 1) + lo


def build_basketball():
    value = _roll(1, 2)
    result = "🏀✅ گل شد!" if value == 1 else "🏀❌ گل نشد!"
    text = f"🏀 پرتاب بسکتبال\n{_SEP}\n{result}\n{_SEP}"
    return (1 if value == 1 else 0), text


def build_penalty():
    value = _roll(1, 2)
    result = "⚽✅ گل!" if value == 1 else "🧤 گل نشد ❌!"
    text = f"⚽ ضربه پنالتی\n{_SEP}\n{result}\n{_SEP}"
    return (1 if value == 1 else 0), text


def build_bowling():
    value = _roll(0, 10)
    if value == 10:
        extra = "💥 STRIKE!\nهمه پین‌ها افتادن 🔥"
    elif value >= 7:
        extra = "🔥 ضربه عالی!"
    elif value >= 4:
        extra = "👍 ضربه معمولی"
    elif value >= 1:
        extra = "😅 چندتا پین افتاد"
    else:
        extra = "💨 GUTTER BALL\nتو جوی افتاد!"
    text = f"🎳 بولینگ\n{_SEP}\n🎯 پین افتاده: {value}\n{extra}\n{_SEP}"
    return value, text


def build_dart():
    scores = ["🎯 10 امتیاز", "🎯 25 امتیاز", "🎯 50 امتیاز", "🎯 100 امتیاز!"]
    points = {1: 10, 2: 25, 3: 50, 4: 100}
    value = _roll(1, 4)
    text = f"🎯 پرتاب دارت\n{_SEP}\n{scores[value - 1]}\n{_SEP}"
    return points[value], text


def build_slots():
    items = ["🍒", "🍋", "🔔", "💎", "7️⃣", "⭐"]
    r1 = items[_roll(0, 5)]
    r2 = items[_roll(0, 5)]
    r3 = items[_roll(0, 5)]
    text = f"🎰 دستگاه اسلات\n{_SEP}\n┃ {r1} ┃ {r2} ┃ {r3} ┃\n{_SEP}"
    return 0, text


def build_rps():
    choices = ["🪨 سنگ", "📄 کاغذ", "✂️ قیچی"]
    result = choices[_roll(0, 2)]
    text = f"🎮 بازی سنگ کاغذ قیچی\n{_SEP}\n{result}\n{_SEP}"
    return 0, text


def build_coin():
    value = _roll(1, 2)
    result = "🪙 شیر" if value == 1 else "🪙 خط"
    text = f"🪙 پرتاب سکه\n{_SEP}\n{result}\n{_SEP}"
    return value, text


def build_luck():
    value = _roll(1, 100)
    if value >= 90:
        label = "🔥 شانس فوق‌العاده!"
    elif value >= 70:
        label = "😎 شانس خوب"
    elif value >= 40:
        label = "🙂 بد نیست"
    elif value >= 20:
        label = "😅 معمولی"
    else:
        label = "💀 امروز شانس نداری"
    text = f"🍀 شانس شما\n{_SEP}\n{value}%\n{label}\n{_SEP}"
    return value, text


_DICE_FACES = {
    1: "⬤",
    2: "⬤ ⬤",
    3: "⬤ ⬤\n  ⬤",
    4: "⬤ ⬤\n⬤ ⬤",
    5: "⬤ ⬤\n  ⬤\n⬤ ⬤",
    6: "⬤ ⬤\n⬤ ⬤\n⬤ ⬤",
}


def build_dice():
    res = _roll(1, 6)
    text = f"تـاس انداخته شـد عدد ↻  : {res} 🎲\n{_DICE_FACES[res]}"
    return res, text


def race_result_caption(game_type: str, score: int) -> str | None:
    """برای حالت ایموجی تلگرام — یک خط خلاصه نتیجه برای ادغام با برد چالش."""
    s = int(score)
    if game_type == "basketball":
        return "🏀✅ گل شد!" if s else "🏀❌ گل نشد!"
    if game_type == "football":
        return "⚽✅ گل!" if s else "🧤 گل نشد ❌!"
    if game_type == "luck":
        return f"🍀 شانس: {s}%"
    if game_type == "dart":
        return f"🎯 امتیاز دارت: {s}"
    if game_type == "dice":
        return f"🎲 تاس: {s}"
    return None


# سازگاری با فراخوانی‌های قدیمی
async def send_basketball(bot, chat_id: int, message_id: int, user_id=None):
    score, text = build_basketball()
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return score


async def send_penalty(bot, chat_id: int, message_id: int, user_id=None):
    score, text = build_penalty()
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return score


async def send_bowling(bot, chat_id: int, message_id: int, user_id=None):
    score, text = build_bowling()
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return score


async def send_dart(bot, chat_id: int, message_id: int, user_id=None):
    score, text = build_dart()
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return score


async def send_slots(bot, chat_id: int, message_id: int, user_id=None):
    score, text = build_slots()
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return score


async def send_rps(bot, chat_id: int, message_id: int, user_id=None):
    score, text = build_rps()
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return score


async def send_coin(bot, chat_id: int, message_id: int, user_id=None):
    score, text = build_coin()
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return score


async def send_luck(bot, chat_id: int, message_id: int, user_id=None):
    score, text = build_luck()
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return score


async def send_dice(bot, chat_id: int, message_id: int, user_id=None):
    score, text = build_dice()
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return score
