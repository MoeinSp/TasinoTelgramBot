"""
بازی‌های متنی — ساختار مشابه rubpy/bot/func.py
پیش‌فرض: بدون استیکر/ایموجی متحرک تلگرام
"""
import secrets

from bot.helpers import safe_send

_SEP = "━━━━━━━━━━━━"


def _roll(lo: int, hi: int) -> int:
    return secrets.randbelow(hi - lo + 1) + lo


async def send_basketball(bot, chat_id: int, message_id: int):
    value = _roll(1, 2)
    result = "🏀✅ گل شد!" if value == 1 else "🏀❌ گل نشد!"
    text = f"🏀 پرتاب بسکتبال\n{_SEP}\n{result}\n{_SEP}"
    await safe_send(bot, chat_id, text, reply_to=message_id)


async def send_penalty(bot, chat_id: int, message_id: int):
    value = _roll(1, 2)
    result = "⚽✅ گل!" if value == 1 else "🧤 گل نشد ❌!"
    text = f"⚽ ضربه پنالتی\n{_SEP}\n{result}\n{_SEP}"
    await safe_send(bot, chat_id, text, reply_to=message_id)


async def send_bowling(bot, chat_id: int, message_id: int):
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
    await safe_send(bot, chat_id, text, reply_to=message_id)


async def send_dart(bot, chat_id: int, message_id: int):
    scores = ["🎯 10 امتیاز", "🎯 25 امتیاز", "🎯 50 امتیاز", "🎯 100 امتیاز!"]
    value = _roll(1, 4)
    text = f"🎯 پرتاب دارت\n{_SEP}\n{scores[value - 1]}\n{_SEP}"
    await safe_send(bot, chat_id, text, reply_to=message_id)


async def send_slots(bot, chat_id: int, message_id: int):
    items = ["🍒", "🍋", "🔔", "💎", "7️⃣", "⭐"]
    r1 = items[_roll(0, 5)]
    r2 = items[_roll(0, 5)]
    r3 = items[_roll(0, 5)]
    text = f"🎰 دستگاه اسلات\n{_SEP}\n┃ {r1} ┃ {r2} ┃ {r3} ┃\n{_SEP}"
    await safe_send(bot, chat_id, text, reply_to=message_id)


async def send_rps(bot, chat_id: int, message_id: int):
    choices = ["🪨 سنگ", "📄 کاغذ", "✂️ قیچی"]
    result = choices[_roll(0, 2)]
    text = f"🎮 بازی سنگ کاغذ قیچی\n{_SEP}\n{result}\n{_SEP}"
    await safe_send(bot, chat_id, text, reply_to=message_id)


async def send_coin(bot, chat_id: int, message_id: int):
    value = _roll(1, 2)
    result = "🪙 شیر" if value == 1 else "🪙 خط"
    text = f"🪙 پرتاب سکه\n{_SEP}\n{result}\n{_SEP}"
    await safe_send(bot, chat_id, text, reply_to=message_id)


async def send_luck(bot, chat_id: int, message_id: int):
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
    await safe_send(bot, chat_id, text, reply_to=message_id)


_DICE_FACES = {
    1: "⬤",
    2: "⬤ ⬤",
    3: "⬤ ⬤\n  ⬤",
    4: "⬤ ⬤\n⬤ ⬤",
    5: "⬤ ⬤\n  ⬤\n⬤ ⬤",
    6: "⬤ ⬤\n⬤ ⬤\n⬤ ⬤",
}


def roll_dice_value() -> int:
    return _roll(1, 6)


async def send_single_dice(bot, chat_id: int, message_id: int, value: int | None = None) -> int:
    """تاس تکی متنی — مقدار رو برمی‌گردونه."""
    res = value if value is not None else roll_dice_value()
    text = f"تـاس انداخته شـد عدد ↻  : {res} 🎲\n{_DICE_FACES[res]}"
    await safe_send(bot, chat_id, text, reply_to=message_id)
    return res
