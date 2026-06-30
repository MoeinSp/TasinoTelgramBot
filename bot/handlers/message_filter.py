"""
فیلتر پیام‌های گروه: قفل‌ها، فیلتر کلمات، ردیابی XP، پاسخ‌های یادگرفته‌شده
"""
from aiogram import Router, F, Bot
from aiogram.types import Message
from asgiref.sync import sync_to_async

from bot import cache
from bot.cache_manager import has_privilege
from bot.helpers import safe_send, contains_link, contains_username

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))


@sync_to_async
def _track_message(chat_id: int, user_id: int, name: str = ""):
    from account.models import TelegramGroup, TelegramGroupMember
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    leveled_up = m.add_xp(2)
    m.message_count += 1
    if name and not m.alias:
        m.alias = name[:255]
    m.save(update_fields=["xp_total", "level", "message_count", "alias"])
    return leveled_up, m.level


@router.message(F.text)
async def handle_text_filter(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""

    if chat_id in cache.OFF_GROUP:
        return

    if has_privilege(chat_id, user_id):
        pass
    else:
        locks = cache.GROUP_LOCKS.get(chat_id, {})

        if locks.get("link") and contains_link(text):
            try:
                await message.delete()
            except Exception:
                pass
            await safe_send(bot, chat_id,
                            f"🔒 ارسال لینک در این گروه مجاز نیست.",
                            reply_to=message.message_id)
            return

        if locks.get("username") and contains_username(text):
            try:
                await message.delete()
            except Exception:
                pass
            await safe_send(bot, chat_id,
                            "🔒 منشن کردن در این گروه مجاز نیست.",
                            reply_to=message.message_id)
            return

        word_list = cache.WORD_FILTERS.get(chat_id, [])
        if word_list:
            lower = text.lower()
            for w in word_list:
                if w in lower:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    return

    learns = cache.LEARNED_RESPONSES.get(chat_id, {})
    if learns:
        key = text.lower().strip()
        if key in learns:
            await safe_send(bot, chat_id, learns[key], reply_to=message.message_id)
            return

    # شمارش پیام در middleware انجام می‌شه (MessageTrackingMiddleware)


@router.message(F.forward_from | F.forward_from_chat)
async def handle_forward_filter(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id in cache.OFF_GROUP:
        return
    if has_privilege(chat_id, user_id):
        return
    locks = cache.GROUP_LOCKS.get(chat_id, {})
    if locks.get("forward"):
        try:
            await message.delete()
        except Exception:
            pass
        await safe_send(bot, chat_id,
                        "🔒 فوروارد پیام در این گروه مجاز نیست.",
                        reply_to=message.message_id)


@router.message(F.photo | F.video | F.animation | F.document)
async def handle_media_filter(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id in cache.OFF_GROUP:
        return
    if has_privilege(chat_id, user_id):
        return
    locks = cache.GROUP_LOCKS.get(chat_id, {})
    if message.photo and locks.get("photo"):
        try:
            await message.delete()
        except Exception:
            pass
        return
    if (message.video or message.document) and locks.get("media"):
        try:
            await message.delete()
        except Exception:
            pass
        return
    if message.animation and locks.get("gif"):
        try:
            await message.delete()
        except Exception:
            pass
        return
