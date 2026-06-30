"""
هندلرهای بازی — پورت کامل از rubpy/bot/func.py و bot/bot.py
"""
import re
import secrets

from aiogram import Router, F, Bot
from aiogram.types import Message

from bot import cache
from bot.helpers import safe_send, db_get_group_commands, db_get_group_theme

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# ─── ۱۵ تم تاس ───────────────────────────────────────────────────────────────

DICE_THEMES = {
    1:  {"name":"کلاسیک",      "dice":["⚀","⚁","⚂","⚃","⚄","⚅"],      "roll":"🎲 {name} تاس انداخت: {icon} {val}"},
    2:  {"name":"سینما",       "dice":["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣"],   "roll":"🎬 {name}: {icon} {val}"},
    3:  {"name":"پادشاهی",     "dice":["👑","🗡","🛡","⚔️","🏰","💎"],      "roll":"🏰 {name}: {icon} {val}"},
    4:  {"name":"ملایم",       "dice":["🌸","🌺","🌻","🌹","🌷","🌼"],      "roll":"🌷 {name}: {icon} {val}"},
    5:  {"name":"نقطه",        "dice":["·","··","···","····","·····","······"],"roll":"· {name}: {icon} {val}"},
    6:  {"name":"کریستال",     "dice":["💠","🔷","🔹","🔵","🔶","💎"],      "roll":"💎 {name}: {icon} {val}"},
    7:  {"name":"سامورایی",    "dice":["⚔️","🗡","🛡","🏯","🎌","🌸"],      "roll":"🏯 {name}: {icon} {val}"},
    8:  {"name":"شبکه",        "dice":["①","②","③","④","⑤","⑥"],          "roll":"📊 {name}: {icon} {val}"},
    9:  {"name":"رعد و برق",   "dice":["⚡","🌩","⛈","🌪","🌊","🔥"],      "roll":"⚡ {name}: {icon} {val}"},
    10: {"name":"کیمیا",       "dice":["🧪","⚗️","🔮","🧬","🌀","✨"],      "roll":"⚗️ {name}: {icon} {val}"},
    11: {"name":"گل رز",       "dice":["🌹","🥀","🌺","🌸","💐","🌷"],      "roll":"💐 {name}: {icon} {val}"},
    12: {"name":"جنگل",        "dice":["🌿","🍃","🌱","🍀","🌲","🌳"],      "roll":"🌲 {name}: {icon} {val}"},
    13: {"name":"طلا",         "dice":["🥇","🥈","🥉","🏅","🎖","🏆"],      "roll":"🏅 {name}: {icon} {val}"},
    14: {"name":"جمجمه",       "dice":["💀","☠️","🦴","🕷","🕯","⚰️"],     "roll":"⚰️ {name}: {icon} {val}"},
    15: {"name":"دروازه اژدها","dice":["🐉","🔥","⚡","💥","🌊","🌪"],      "roll":"🔥 {name}: {icon} {val}"},
}


def get_dice_roll() -> int:
    return secrets.randbelow(6) + 1


async def _reply(message: Message, text: str):
    await safe_send(message.bot, message.chat.id, text, reply_to=message.message_id)


async def _check_enabled(message: Message, cmd: str) -> bool:
    chat_id = message.chat.id
    if chat_id in cache.OFF_GROUP:
        return False
    cmds = await db_get_group_commands(chat_id)
    if cmd not in cmds:
        await _reply(message, "این قابلیت توسط ادمین گروه غیرفعال شده است.")
        return False
    return True


# تاس — در main_group.py هندل می‌شود (سیستم کامل با تم و مسابقه)


# ─── بازی‌های تلگرام ──────────────────────────────────────────────────────────

@router.message(F.text == "بسکتبال")
async def cmd_basketball(message: Message, bot: Bot):
    if not await _check_enabled(message, "بسکتبال"):
        return
    await bot.send_dice(message.chat.id, emoji="🏀")


@router.message(F.text == "پنالتی")
async def cmd_penalty(message: Message, bot: Bot):
    if not await _check_enabled(message, "پنالتی"):
        return
    await bot.send_dice(message.chat.id, emoji="⚽")


@router.message(F.text == "بولینگ")
async def cmd_bowling(message: Message, bot: Bot):
    if not await _check_enabled(message, "بولینگ"):
        return
    await bot.send_dice(message.chat.id, emoji="🎳")


@router.message(F.text == "دارت")
async def cmd_dart(message: Message, bot: Bot):
    if not await _check_enabled(message, "دارت"):
        return
    await bot.send_dice(message.chat.id, emoji="🎯")


@router.message(F.text == "اسلات")
async def cmd_slots(message: Message, bot: Bot):
    if not await _check_enabled(message, "اسلات"):
        return
    await bot.send_dice(message.chat.id, emoji="🎰")


# ─── بازی‌های متنی ────────────────────────────────────────────────────────────

_RPS_OPTIONS = ["سنگ 🪨", "کاغذ 📄", "قیچی ✂️"]
_RPS_MAP = {"سنگ 🪨": "قیچی ✂️", "کاغذ 📄": "سنگ 🪨", "قیچی ✂️": "کاغذ 📄"}


@router.message(F.text == "سنگ کاغذ قیچی")
async def cmd_rps(message: Message):
    if not await _check_enabled(message, "سنگ کاغذ قیچی"):
        return
    bot_pick = secrets.choice(_RPS_OPTIONS)
    user_pick = secrets.choice(_RPS_OPTIONS)
    if user_pick == bot_pick:
        result = "🤝 مساوی!"
    elif _RPS_MAP[user_pick] == bot_pick:
        result = "🎉 بُردی!"
    else:
        result = "😢 باختی!"
    text = (
        f"✂️ سنگ کاغذ قیچی\n\n"
        f"👤 انتخاب شما: {user_pick}\n"
        f"🤖 انتخاب ربات: {bot_pick}\n\n"
        f"{result}"
    )
    return await _reply(message, text)


@router.message(F.text == "سکه")
async def cmd_coin(message: Message):
    if not await _check_enabled(message, "سکه"):
        return
    side = secrets.choice(["شیر 🦁", "خط 📝"])
    return await _reply(message, f"🪙 سکه انداخته شد:\n\n{side}")


@router.message(F.text == "شانس")
async def cmd_luck(message: Message):
    if not await _check_enabled(message, "شانس"):
        return
    percent = secrets.randbelow(101)
    emoji = "🍀" if percent >= 90 else "😊" if percent >= 70 else "😐" if percent >= 50 else "😕" if percent >= 30 else "😢"
    return await _reply(message, f"🍀 شانس شما: {percent}% {emoji}")


# ─── سرگرمی ──────────────────────────────────────────────────────────────────

@router.message(F.text == "جوک")
async def cmd_joke(message: Message):
    if not await _check_enabled(message, "جوک"):
        return
    jokes = [
        "یه نفر رفت دکتر گفت: دکتر همه بهم می‌گن دروغگو!\nدکتر گفت: باور نمی‌کنم 😄",
        "استاد: سوال داری؟\nدانشجو: بله!\nاستاد: خب، امتحان موفق 😂",
        "رفیقم گفت: می‌خوام زندگیمو عوض کنم!\nگفتم: پس بیا موبایلمو شارژ بده 😂",
        "معلم: ۲ ضربدر ۲ چنده؟\nشاگرد: ۴!\nمعلم: آفرین!\nشاگرد: باورم نمیشه یه بار حدسم درست بود 😄",
        "اگه هوش مصنوعی جایم رو بگیره، حداقل دیگه مجبور نیستم کار کنم 😂",
    ]
    return await _reply(message, f"😂 جوک:\n\n{secrets.choice(jokes)}")


@router.message(F.text == "سخن")
async def cmd_wisdom(message: Message):
    if not await _check_enabled(message, "سخن"):
        return
    wisdoms = [
        "آنچه را که نمی‌توانی تغییر دهی، بپذیر.",
        "بهترین وقت برای شروع، همین الان است.",
        "موفقیت یعنی هر روز کمی بهتر از دیروز باشی.",
        "هر سختی در خود آسانی دارد.",
        "از اشتباهات خود بیاموز، نه از پشیمانی‌هایت.",
    ]
    return await _reply(message, f"💎 سخن:\n\n{secrets.choice(wisdoms)}")


@router.message(F.text.in_(["دانستنی", "فکت"]))
async def cmd_fact(message: Message):
    if not await _check_enabled(message, "دانستنی"):
        return
    facts = [
        "عسل تنها ماده غذایی است که هرگز فاسد نمی‌شود!",
        "اختاپوس‌ها سه قلب دارند.",
        "موز از نظر علمی یک توت است!",
        "مورچه‌ها می‌توانند ۵۰ برابر وزن خود را حمل کنند.",
        "انسان تنها جانوری است که شرم می‌کند.",
    ]
    return await _reply(message, f"💡 دانستنی:\n\n{secrets.choice(facts)}")


@router.message(F.text == "فال")
async def cmd_fortune(message: Message):
    if not await _check_enabled(message, "فال"):
        return
    fortunes = [
        "🌟 روزهای روشنی در انتظار توست.",
        "💫 یک فرصت خوب به زودی سراغت می‌آید.",
        "🌈 صبور باش، پایان خوشی در راه است.",
        "🍀 امروز روز خوش‌شانسی توست!",
        "⭐ به خودت اعتماد کن، موفق می‌شوی.",
    ]
    return await _reply(message, f"📜 فالت:\n\n{secrets.choice(fortunes)}")


@router.message(F.text == "معما")
async def cmd_riddle(message: Message):
    if not await _check_enabled(message, "معما"):
        return
    riddles = [
        ("هر چه بیشتر بکشی کوتاه‌تر می‌شه؟", "مداد"),
        ("چی هست که همه دارن ولی نمی‌شه دید؟", "آینده"),
        ("اول آدم‌هاش می‌نشینن بعد پاشون بالاست؟", "کفش"),
        ("شب سفیده، روز سیاهه؟", "تخته سیاه"),
        ("چی چیزیه که هر چی بزرگترش می‌کنی کوچیکتر می‌شه؟", "حفره"),
    ]
    q, a = secrets.choice(riddles)
    return await _reply(message, f"🤔 معما:\n\n{q}\n\n||جواب: {a}||")


@router.message(F.text == "چالش")
async def cmd_challenge(message: Message):
    if not await _check_enabled(message, "چالش"):
        return
    challenges = [
        "۱۰ تا بالا پایین برو بدون وقفه!",
        "بدون خندیدن یه جوک بخون!",
        "اسم ۱۰ کشور بگو در ۱۰ ثانیه!",
        "یک دقیقه بدون نگاه کردن به گوشی دوام بیار!",
        "یه چیز خنده‌دار به رفیقت بگو بدون اینکه بخندی!",
    ]
    return await _reply(message, f"🎯 چالش امروز:\n\n{secrets.choice(challenges)}")


@router.message(F.text == "شخصیت")
async def cmd_personality(message: Message):
    if not await _check_enabled(message, "شخصیت"):
        return
    personalities = [
        "تو یه رهبر ذاتی هستی! 👑",
        "تو خلاق و هنرمند هستی! 🎨",
        "تو یه تحلیل‌گر دقیق هستی! 🔬",
        "تو یه انسان محبوب و اجتماعی هستی! 💕",
        "تو یه مبارز پر انرژی هستی! ⚡",
    ]
    return await _reply(message, f"💕 شخصیت شما:\n\n{secrets.choice(personalities)}")


@router.message(F.text == "دو راهی")
async def cmd_dilemma(message: Message):
    if not await _check_enabled(message, "دو راهی"):
        return
    dilemmas = [
        "ترجیح می‌دی هرگز گرسنه نشی یا هرگز خوابت نبره؟",
        "ترجیح می‌دی پرنده باشی یا ماهی؟",
        "ترجیح می‌دی ۱۰۰ سال زندگی کنی ولی فقیر باشی یا ۵۰ سال ثروتمند؟",
        "ترجیح می‌دی همه چیز رو بدونی یا هیچ‌چیز نگران‌ت نکنه؟",
        "ترجیح می‌دی در گذشته زندگی کنی یا آینده؟",
    ]
    return await _reply(message, f"⚖️ دو راهی:\n\n{secrets.choice(dilemmas)}")
