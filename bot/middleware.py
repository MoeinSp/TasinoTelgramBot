"""
Middleware برای شمارش پیام‌ها — قبل از همه handler‌ها اجرا می‌شه
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message
from asgiref.sync import sync_to_async

from bot import cache


@sync_to_async
def _track_message(chat_id: int, user_id: int, name: str = ""):
    from account.models import TelegramGroup, TelegramGroupMember
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    m.message_count += 1
    leveled_up = m.add_xp(2)
    if name and not m.alias:
        m.alias = name[:255]
    m.save(update_fields=["xp_total", "level", "message_count", "alias"])
    return leveled_up, m.level


class MessageTrackingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # فقط پیام‌های گروه از کاربران واقعی
        if (
            event.chat
            and event.chat.type in ("group", "supergroup")
            and event.from_user
            and not event.from_user.is_bot
            and event.chat.id not in cache.OFF_GROUP
        ):
            name = event.from_user.full_name or ""
            leveled_up, level = await _track_message(event.chat.id, event.from_user.id, name)

            if leveled_up and event.chat.id in cache.SPEAKER_ON:
                first = event.from_user.first_name or str(event.from_user.id)
                try:
                    from aiogram import Bot
                    bot: Bot = data.get("bot")
                    if bot:
                        from bot.helpers import safe_send
                        await safe_send(bot, event.chat.id, f"🎉 تبریک! سطح {first} به {level} رسید.")
                except Exception:
                    pass

        return await handler(event, data)
