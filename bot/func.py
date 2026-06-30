import random
from aiogram.types import Message


async def send_coin(message: Message):
    result = random.choice(["شیر 🦁", "خط ✏️"])
    await message.reply(f"🪙 سکه: **{result}**", parse_mode="Markdown")


async def send_luck(message: Message):
    score = random.randint(1, 100)
    if score >= 90:
        emoji = "🌟"
    elif score >= 70:
        emoji = "😊"
    elif score >= 40:
        emoji = "😐"
    else:
        emoji = "😢"
    await message.reply(f"{emoji} شانس امروز تو: **{score}%**", parse_mode="Markdown")


async def send_rps(message: Message):
    choices = ["سنگ 🪨", "کاغذ 📄", "قیچی ✂️"]
    bot_choice = random.choice(choices)
    user_choice = random.choice(choices)

    def winner(u, b):
        wins = {"سنگ 🪨": "قیچی ✂️", "کاغذ 📄": "سنگ 🪨", "قیچی ✂️": "کاغذ 📄"}
        if u == b:
            return "🤝 مساوی"
        return "🏆 تو بردی!" if wins[u] == b else "💀 بات برد!"

    result = winner(user_choice, bot_choice)
    await message.reply(
        f"تو: {user_choice}\nبات: {bot_choice}\n\n{result}",
        parse_mode="Markdown"
    )
