"""
Middleware — شمارش پیام گروه + جوین اجباری پیوی
"""
from typing import Any, Awaitable, Callable, Dict, Union

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery
from asgiref.sync import sync_to_async

from bot import cache
from bot.required_join import (
    is_creator, is_forced_join_active, is_user_channel_member,
    is_creator_setup_message, join_required_text, join_required_keyboard,
)


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


class RequiredJoinMiddleware(BaseMiddleware):
    """در پیوی، بدون عضویت در کانال اصلی خدمات داده نمی‌شود."""

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:
        if not is_forced_join_active():
            return await handler(event, data)

        chat = None
        user = None
        if isinstance(event, Message):
            chat = event.chat
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            if event.message:
                chat = event.message.chat

        if not chat or chat.type != "private" or not user or user.is_bot:
            return await handler(event, data)

        if is_creator(user.id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == "join:recheck":
            return await handler(event, data)

        if isinstance(event, Message):
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
            if is_creator_setup_message(event.text):
                return await handler(event, data)

        bot: Bot = data.get("bot")
        if bot and await is_user_channel_member(bot, user.id):
            return await handler(event, data)

        text = join_required_text()
        kb = join_required_keyboard()
        if isinstance(event, CallbackQuery):
            try:
                await event.answer("هنوز عضو کانال نشده‌اید.", show_alert=True)
                if event.message:
                    await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                if event.message:
                    await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
            return None

        await event.answer(text, reply_markup=kb, parse_mode="HTML")
        return None
