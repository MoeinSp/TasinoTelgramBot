"""
هندلرهای بازی — پیش‌فرض متنی (rubpy)، با «ایموجی تلگرام روشن» استیکر متحرک تلگرام
"""
import secrets

from aiogram import Router, F, Bot
from aiogram.types import Message

from bot import cache
from bot import game_text
from bot.helpers import safe_send, db_get_group_commands, telegram_emoji_on

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


async def _reply(message: Message, text: str):
    await safe_send(message.bot, message.chat.id, text, reply_to=message.message_id)


async def _check_enabled(message: Message, cmd: str) -> bool:
    chat_id = message.chat.id
    if chat_id in cache.OFF_GROUP:
        return False

    from bot.cache_manager import has_privilege
    locks = cache.GROUP_LOCKS.get(chat_id, {})
    if locks.get("fun_text") and not has_privilege(chat_id, message.from_user.id):
        return False

    cmds = await db_get_group_commands(chat_id)
    if cmd not in cmds:
        await _reply(message, "این قابلیت توسط ادمین گروه غیرفعال شده است.")
        return False
    return True


async def _play_tg_or_text(
    message: Message, bot: Bot, cmd: str, tg_emoji: str, text_fn,
):
    if not await _check_enabled(message, cmd):
        return
    chat_id = message.chat.id
    mid = message.message_id
    if telegram_emoji_on(chat_id):
        await bot.send_dice(chat_id, emoji=tg_emoji, reply_to_message_id=mid)
    else:
        await text_fn(bot, chat_id, mid)


# تاس — در main_group.py هندل می‌شود (سیستم کامل با تم و مسابقه)


@router.message(F.text == "بسکتبال")
async def cmd_basketball(message: Message, bot: Bot):
    await _play_tg_or_text(message, bot, "بسکتبال", "🏀", game_text.send_basketball)


@router.message(F.text == "پنالتی")
async def cmd_penalty(message: Message, bot: Bot):
    await _play_tg_or_text(message, bot, "پنالتی", "⚽", game_text.send_penalty)


@router.message(F.text == "بولینگ")
async def cmd_bowling(message: Message, bot: Bot):
    await _play_tg_or_text(message, bot, "بولینگ", "🎳", game_text.send_bowling)


@router.message(F.text == "دارت")
async def cmd_dart(message: Message, bot: Bot):
    await _play_tg_or_text(message, bot, "دارت", "🎯", game_text.send_dart)


@router.message(F.text == "اسلات")
async def cmd_slots(message: Message, bot: Bot):
    await _play_tg_or_text(message, bot, "اسلات", "🎰", game_text.send_slots)


@router.message(F.text == "سنگ کاغذ قیچی")
async def cmd_rps(message: Message, bot: Bot):
    if not await _check_enabled(message, "سنگ کاغذ قیچی"):
        return
    await game_text.send_rps(bot, message.chat.id, message.message_id)


@router.message(F.text == "سکه")
async def cmd_coin(message: Message, bot: Bot):
    if not await _check_enabled(message, "سکه"):
        return
    await game_text.send_coin(message.bot, message.chat.id, message.message_id)


@router.message(F.text == "شانس")
async def cmd_luck(message: Message, bot: Bot):
    if not await _check_enabled(message, "شانس"):
        return
    await game_text.send_luck(message.bot, message.chat.id, message.message_id)


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
