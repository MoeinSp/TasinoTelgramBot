"""
Middleware — شمارش پیام گروه + جوین اجباری پیوی
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Union

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery
from asgiref.sync import sync_to_async

from bot import cache
from bot.required_join import (
    is_creator, is_forced_join_active, is_user_channel_member,
    is_creator_setup_message, join_required_text, join_required_keyboard,
)

logger = logging.getLogger(__name__)

# صف XP/شمارش پیام — بدون بلاک کردن هندلر
_PENDING_TRACK: dict[tuple[int, int], dict] = {}
_FLUSH_TASK: asyncio.Task | None = None
_FLUSH_INTERVAL = 1.5
_ALIAS_PLACEHOLDERS = frozenset({"کاربر", "user", "unknown", "کاربر ناشناس", ""})


@sync_to_async
def _flush_track_db(pending: dict[tuple[int, int], dict]) -> list[tuple]:
    """اعمال دسته‌ای XP. برمی‌گرداند [(chat_id, user_id, level, bot, name), ...] برای level-up."""
    from account.models import TelegramGroup, TelegramGroupMember

    leveled: list[tuple] = []
    for (chat_id, user_id), entry in pending.items():
        count = int(entry.get("n") or 0)
        if count <= 0:
            continue
        name = (entry.get("name") or "")[:255]
        bot = entry.get("bot")
        grp, _ = TelegramGroup.objects.get_or_create(
            telegram_chat_id=chat_id, defaults={"name": ""}
        )
        m, _ = TelegramGroupMember.objects.get_or_create(
            telegram_chat_id=chat_id, telegram_user_id=user_id,
            defaults={"group": grp},
        )
        m.message_count = (m.message_count or 0) + count
        xp_gain = 2 * count
        did_level = False
        m.xp_total = (m.xp_total or 0) + xp_gain
        while m.xp_total >= m.level * 100:
            m.xp_total -= m.level * 100
            m.level += 1
            did_level = True
        if name:
            a = (m.alias or "").strip().lower()
            if a in _ALIAS_PLACEHOLDERS:
                m.alias = name
        m.save(update_fields=["xp_total", "level", "message_count", "alias"])
        if did_level:
            leveled.append((chat_id, user_id, m.level, bot, name))
    return leveled


async def _do_flush_tracks() -> None:
    global _FLUSH_TASK
    await asyncio.sleep(_FLUSH_INTERVAL)
    snapshot = dict(_PENDING_TRACK)
    _PENDING_TRACK.clear()
    _FLUSH_TASK = None
    if not snapshot:
        return
    try:
        leveled = await _flush_track_db(snapshot)
    except Exception:
        logger.exception("flush message track failed")
        return

    for chat_id, user_id, level, bot, name in leveled:
        if chat_id not in cache.SPEAKER_ON or not bot:
            continue
        first = (name or "").split()[0] if name else str(user_id)
        try:
            from bot.helpers import safe_send
            await safe_send(bot, chat_id, f"🎉 تبریک! سطح {first} به {level} رسید.")
        except Exception:
            pass

    if _PENDING_TRACK and (_FLUSH_TASK is None or _FLUSH_TASK.done()):
        _FLUSH_TASK = asyncio.create_task(_do_flush_tracks())


def _enqueue_track(chat_id: int, user_id: int, name: str, bot: Bot | None) -> None:
    global _FLUSH_TASK
    key = (chat_id, user_id)
    entry = _PENDING_TRACK.setdefault(
        key, {"n": 0, "name": "", "bot": bot, "chat_id": chat_id, "user_id": user_id}
    )
    entry["n"] += 1
    if name:
        entry["name"] = name
    if bot is not None:
        entry["bot"] = bot
    if _FLUSH_TASK is None or _FLUSH_TASK.done():
        _FLUSH_TASK = asyncio.create_task(_do_flush_tracks())


class MessageTrackingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # فقط پیام‌های گروه از کاربران واقعی — بدون await روی DB
        if (
            event.chat
            and event.chat.type in ("group", "supergroup")
            and event.from_user
            and not event.from_user.is_bot
            and event.chat.id not in cache.OFF_GROUP
        ):
            name = event.from_user.full_name or ""
            _enqueue_track(
                event.chat.id,
                event.from_user.id,
                name,
                data.get("bot"),
            )

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


class GroupRequiredJoinMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not isinstance(event, Message) or event.chat.type not in ("group", "supergroup"):
            return await handler(event, data)
        # تنظیمات پنل باید حتی قبل از عضویت مالک قابل استفاده باشد.
        if event.text and event.text.startswith(("تنظیم جوین اجباری", "حذف جوین اجباری")):
            return await handler(event, data)
        from bot.group_forced_join import enforce_group_join
        if await enforce_group_join(event, data.get("bot")):
            return await handler(event, data)
        return None


class GlobalBotOffMiddleware(BaseMiddleware):
    """اگر ربات سراسری خاموش باشد، فقط سازنده در پیوی می‌تواند کار کند."""

    BOT_OFF_TEXT = (
        "⚫ ربات موقتاً خاموش است.\n"
        "لطفاً بعداً دوباره تلاش کنید."
    )

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:
        from bot.site_config import is_bot_globally_enabled
        from bot.constants import CREATOR_USER_ID

        if is_bot_globally_enabled():
            return await handler(event, data)

        user = event.from_user
        if user and user.id == CREATOR_USER_ID:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            try:
                await event.answer(self.BOT_OFF_TEXT, show_alert=True)
            except Exception:
                pass
            return None

        if isinstance(event, Message):
            try:
                # فقط در پیوی جواب بده؛ در گروه بی‌صدا رد شو
                if event.chat and event.chat.type == "private":
                    await event.answer(self.BOT_OFF_TEXT)
            except Exception:
                pass
            return None

        return None


class PrivateUserSyncMiddleware(BaseMiddleware):
    """در پیوی: chat_id و در صورت نبود نام، alias گروه‌ها از پروفایل تلگرام."""

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:
        from bot.finance import register_pv_user

        user = event.from_user
        chat = None
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat

        if user and not user.is_bot and chat and chat.type == "private":
            now = time.monotonic()
            exp = cache.PV_USER_SYNCED.get(user.id)
            if not exp or exp <= now:
                display = (user.full_name or user.first_name or "").strip()
                await register_pv_user(user.id, chat.id, display)
                cache.PV_USER_SYNCED[user.id] = now + cache.PV_USER_SYNC_TTL

        return await handler(event, data)
