"""
فیلتر پیام‌های گروه: قفل‌ها، فیلتر کلمات، آنتی فلود، حالت شب، کپچا

این روتر قبل از همه‌ی روترهای گروه اجرا می‌شه (bot/routers.py).
اگه پیام تخلفی داشته باشه حذفش می‌کنه و همون‌جا متوقف می‌شه؛
وگرنه با skip() اجازه می‌ده بقیه‌ی هندلرها (دستورات، بازی‌ها و...) اجرا بشن.
"""
import time
from datetime import datetime, timezone, timedelta

from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions
from aiogram.dispatcher.event.bases import skip

from bot import cache
from bot.cache_manager import has_privilege
from bot.helpers import (
    safe_send, contains_link, contains_username, is_night_time, log_action,
    db_add_warning, db_get_max_warnings, db_reset_warnings,
)

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
router.edited_message.filter(F.chat.type.in_({"group", "supergroup"}))

# فقط سازنده ربات (دستورهای خاص)
CREATOR_USER_ID = 8810788620


def _is_flooding(chat_id: int, user_id: int) -> bool:
    if chat_id not in cache.ANTI_FLOOD_ENABLED:
        return False
    cfg = cache.ANTI_FLOOD_SETTINGS.get(chat_id, {"limit": 5, "window": 10})
    limit = cfg.get("limit", 5)
    window = cfg.get("window", 10)
    key = (chat_id, user_id)
    now = time.time()
    ts = [t for t in cache.FLOOD_TRACKER.get(key, []) if now - t < window]
    ts.append(now)
    cache.FLOOD_TRACKER[key] = ts
    return len(ts) > limit


async def _delete(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


_VIOLATION_TEXTS = {
    "ارسال لینک": "ارسال لينک ممنوع است",
    "ارسال یوزرنیم": "ارسال آيدی ممنوع است",
    "کلمه ممنوعه": "ارسال كلمات ممنوعه مجاز نيست",
}


async def _warn_and_maybe_kick(message: Message, bot: Bot, reason: str) -> None:
    """اگه اخطار خودکار روشن باشه، به متخلف اخطار می‌ده و در صورت رسیدن به سقف اخراجش می‌کنه."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id not in cache.WARNING_ENABLED:
        await safe_send(bot, chat_id, f"🔒 {reason} در این گروه مجاز نیست.")
        await _delete(message)
        return

    warns = await db_add_warning(chat_id, user_id)
    max_w = await db_get_max_warnings(chat_id)
    name = message.from_user.first_name or str(user_id)
    from bot.helpers import user_mention
    mention = await user_mention(user_id, chat_id, fallback=name)
    violation_text = _VIOLATION_TEXTS.get(reason, "اين عمل ممنوع است")

    if warns >= max_w:
        warning_part = (
            f"شما [ {warns}/{max_w} ] اخطار دريافت كرديد.\n\n"
            f"›› كاربر از گروه اخراج خواهد شد"
        )
    else:
        warning_part = f"شما [ {warns}/{max_w} ] اخطار دريافت كرديد"

    warning_text = f"› {mention}\n\n›› {violation_text}\n\n›› {warning_part}"
    try:
        await bot.send_message(
            chat_id, warning_text,
            parse_mode="HTML",
            reply_to_message_id=message.message_id,
        )
    except Exception:
        await safe_send(bot, chat_id, warning_text, parse_mode="HTML")
    await _delete(message)

    if warns >= max_w:
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
        except Exception:
            pass
        await db_reset_warnings(chat_id, user_id)
        await log_action(bot, chat_id,
                         f"⛔️ اخراج بابت سقف اخطار — <code>{user_id}</code> ({reason})")


# ─── قفل ادیت ─────────────────────────────────────────────────────────────────

@router.edited_message()
async def handle_edited_message(message: Message, bot: Bot):
    chat_id = message.chat.id
    if chat_id in cache.OFF_GROUP or not message.from_user:
        return
    if has_privilege(chat_id, message.from_user.id):
        return
    locks = cache.GROUP_LOCKS.get(chat_id, {})
    if locks.get("edit_message"):
        await _delete(message)
        await safe_send(bot, chat_id, "🔒 ویرایش پیام در این گروه مجاز نیست.")


# ─── پایپ‌لاین اصلی فیلتر (روی همه‌ی انواع پیام) ─────────────────────────────

@router.message()
async def enforce_filters(message: Message, bot: Bot):
    chat_id = message.chat.id

    # پیام‌های سرویس (ورود/خروج عضو و...) باید به هندلرهای خودشون برسن
    if message.new_chat_members or message.left_chat_member or not message.from_user:
        skip()

    # ادمین ناشناس گروه یا پیام خودکار کانال لینک‌شده — معاف از قفل‌ها
    if message.sender_chat and (
        message.sender_chat.id == chat_id or message.is_automatic_forward
    ):
        skip()

    if chat_id in cache.OFF_GROUP:
        skip()

    user_id = message.from_user.id

    # ── خفه: حذف پیام همه (حتی مقام‌دارها) ──
    if chat_id in cache.SILENCE_ALL and user_id != CREATOR_USER_ID:
        await _delete(message)
        try:
            await bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False),
            )
            cache.SILENCE_ALL_USERS.setdefault(chat_id, set()).add(user_id)
        except Exception:
            pass
        return

    # کاربر در انتظار کپچا حق ارسال هیچ پیامی نداره
    if (chat_id, user_id) in cache.PENDING_CAPTCHA and not has_privilege(chat_id, user_id):
        await _delete(message)
        return

    if has_privilege(chat_id, user_id):
        skip()

    # قفل کل گروه
    if chat_id in cache.GROUP_LOCK:
        await _delete(message)
        return

    # حالت شب
    if is_night_time(chat_id):
        await _delete(message)
        return

    # آنتی فلود
    if _is_flooding(chat_id, user_id):
        await _delete(message)
        until = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
        try:
            await bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
        except Exception:
            pass
        await safe_send(bot, chat_id,
                        "⚠️ کاربر به دلیل ارسال سریع پیام ۵ دقیقه سکوت شد.")
        return

    locks = cache.GROUP_LOCKS.get(chat_id, {})

    # ── قفل‌های متنی ──
    text = message.text or message.caption or ""
    if text:
        if locks.get("link") and contains_link(text):
            await _warn_and_maybe_kick(message, bot, "ارسال لینک")
            return

        if locks.get("username") and contains_username(text):
            await _warn_and_maybe_kick(message, bot, "ارسال یوزرنیم")
            return

        if locks.get("bad_words"):
            word_list = cache.WORD_FILTERS.get(chat_id, [])
            lower = text.lower()
            for w in word_list:
                if w in lower:
                    await _warn_and_maybe_kick(message, bot, "کلمه ممنوعه")
                    return

    # ── قفل فوروارد ──
    if locks.get("forward") and message.forward_origin:
        await _delete(message)
        await safe_send(bot, chat_id, "🔒 فوروارد پیام در این گروه مجاز نیست.")
        return

    # ── قفل اینلاین (پیام ارسالی از طریق ربات‌های دیگر) ──
    if locks.get("via_bot") and message.via_bot:
        await _delete(message)
        return

    # ── قفل‌های مدیا ──
    media_checks = (
        ("photo", message.photo),
        ("gif", message.animation),
        ("video", message.video),
        ("video_note", message.video_note),
        ("voice", message.voice),
        ("audio", message.audio),
        ("document", message.document and not message.animation),
        ("sticker", message.sticker),
        ("contact", message.contact),
        ("location", message.location or message.venue),
        ("poll", message.poll),
        ("game", message.game or message.dice),
    )
    for lock_key, present in media_checks:
        if present and locks.get(lock_key):
            await _delete(message)
            return

    # قفل «مدیا» = قفل کلی همه‌ی رسانه‌ها
    if locks.get("media") and (
        message.photo or message.video or message.animation or message.document
        or message.audio or message.voice or message.video_note or message.sticker
    ):
        await _delete(message)
        return

    # پیام سالمه — بذار هندلرهای بعدی (دستورات، بازی، یادگیری و...) اجرا بشن
    skip()
