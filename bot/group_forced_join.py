from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from asgiref.sync import sync_to_async

from bot.constants import CREATOR_USER_ID

JOINED = {
    ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR, ChatMemberStatus.RESTRICTED,
}
_LAST_MISSING: dict[tuple[int, int], set[int]] = {}
_LAST_PROMPT: dict[tuple[int, int], float] = {}


@dataclass
class JoinTarget:
    channel_id: int
    title: str
    link: str
    source: str


@sync_to_async
def load_targets(group_chat_id: int) -> list[JoinTarget]:
    from account.models import TelegramGroup
    from bot_setting.models import ForcedJoinConfig, GroupForcedJoin

    targets = []
    creator = ForcedJoinConfig.get_singleton()
    from django.utils import timezone
    now = timezone.now()
    creator_in_window = not (creator.active_from and now < creator.active_from) and not (creator.active_until and now > creator.active_until)
    if creator.enabled and creator.channel_id and creator_in_window:
        link = creator.invite_link or (f"https://t.me/{creator.channel_username}" if creator.channel_username else "")
        targets.append(JoinTarget(creator.channel_id, creator.channel_title or "کانال سازنده", link, "creator"))
    group = TelegramGroup.objects.filter(telegram_chat_id=group_chat_id).first()
    own = GroupForcedJoin.objects.filter(group=group, is_active=True).first() if group else None
    if own:
        targets.append(JoinTarget(own.channel_id, own.title or "کانال گروه", own.invite_link, "group"))
    unique = {}
    for target in targets:
        unique[target.channel_id] = target
    return list(unique.values())[:2]


@sync_to_async
def save_group_target(group_chat_id: int, channel_id: int, title: str, link: str):
    from account.models import TelegramGroup
    from bot_setting.models import GroupForcedJoin
    group = TelegramGroup.objects.get(telegram_chat_id=group_chat_id)
    return GroupForcedJoin.objects.update_or_create(
        group=group,
        defaults={"channel_id": channel_id, "title": title, "invite_link": link, "is_active": True},
    )


@sync_to_async
def clear_group_target(group_chat_id: int) -> int:
    from bot_setting.models import GroupForcedJoin
    return GroupForcedJoin.objects.filter(group__telegram_chat_id=group_chat_id).delete()[0]


@sync_to_async
def get_group_target(group_chat_id: int):
    from bot_setting.models import GroupForcedJoin
    obj = GroupForcedJoin.objects.filter(group__telegram_chat_id=group_chat_id).first()
    if not obj:
        return None
    return {"channel_id": obj.channel_id, "title": obj.title, "link": obj.invite_link, "active": obj.is_active}


async def resolve_target(bot: Bot, raw: str) -> JoinTarget:
    raw = (raw or "").strip()
    username = raw.rstrip("/").rsplit("/", 1)[-1].lstrip("@")
    if not username or username.startswith("+"):
        raise ValueError("لینک خصوصی قابل بررسی نیست؛ لینک عمومی یا @username بفرستید.")
    chat = await bot.get_chat(f"@{username}")
    me = await bot.get_me()
    member = await bot.get_chat_member(chat.id, me.id)
    if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        raise ValueError("ابتدا ربات را در کانال مقصد ادمین کنید.")
    return JoinTarget(chat.id, chat.title or username, f"https://t.me/{username}", "group")


async def missing_targets(bot: Bot, group_id: int, user_id: int) -> tuple[list[JoinTarget], list[JoinTarget]]:
    targets = await load_targets(group_id)
    from bot.cache_manager import is_owner, is_admin, is_vip
    is_group_manager = is_owner(group_id, user_id) or is_admin(group_id, user_id)
    is_special_member = is_vip(group_id, user_id)
    try:
        group_member = await bot.get_chat_member(group_id, user_id)
        is_group_manager = is_group_manager or group_member.status in (
            ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR,
        )
    except Exception:
        pass
    applicable = []
    missing = []
    for target in targets:
        # مالک/ادمین از هر دو لینک معاف است؛ عضو ویژه فقط از لینک مالک گروه.
        if target.source == "creator" and is_group_manager:
            continue
        if target.source == "group" and (is_group_manager or is_special_member):
            continue
        applicable.append(target)
        try:
            member = await bot.get_chat_member(target.channel_id, user_id)
            if member.status not in JOINED:
                missing.append(target)
        except Exception:
            missing.append(target)
    return applicable, missing


def keyboard(group_id: int, missing: list[JoinTarget]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"عضویت در {t.title}", url=t.link)] for t in missing if t.link]
    rows.append([InlineKeyboardButton(text="✅ بررسی عضویت", callback_data=f"gfj:check:{group_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def required_text(name: str, missing: list[JoinTarget]) -> str:
    names = "، ".join(f"<b>{t.title}</b>" for t in missing)
    return f"🔒 {name} عزیز، ابتدا در {names} عضو شوید و سپس «بررسی عضویت» را بزنید."


async def delete_later(message: Message, seconds: int = 10):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except Exception:
        pass


async def send_temporary(message: Message, text: str, reply_markup=None):
    sent = await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    asyncio.create_task(delete_later(sent))
    return sent


async def enforce_group_join(message: Message, bot: Bot) -> bool:
    user = message.from_user
    if not user or user.is_bot or user.id == CREATOR_USER_ID:
        return True
    targets, missing = await missing_targets(bot, message.chat.id, user.id)
    if not targets:
        return True
    key = (message.chat.id, user.id)
    old = _LAST_MISSING.get(key, {t.channel_id for t in targets})
    current = {t.channel_id for t in missing}
    joined_now = old - current
    if joined_now:
        joined_names = [t.title for t in targets if t.channel_id in joined_now]
        remaining = [t.title for t in missing]
        suffix = f" هنوز باقی مانده: {', '.join(remaining)}" if remaining else " همهٔ عضویت‌ها تکمیل شد ✅"
        await send_temporary(message, f"✅ {user.full_name} در {', '.join(joined_names)} عضو شد؛{suffix}")
    _LAST_MISSING[key] = current
    if not missing:
        _LAST_PROMPT.pop(key, None)
        return True
    # پیام کاربر تا زمان تکمیل عضویت نباید در گروه باقی بماند.
    try:
        await message.delete()
    except Exception:
        pass

    # هشدار برای هر کاربر در هر گروه حداکثر هر ۱۰ ثانیه یک‌بار ارسال می‌شود.
    now = time.monotonic()
    last_prompt = _LAST_PROMPT.get(key, 0.0)
    if now - last_prompt >= 10.0:
        _LAST_PROMPT[key] = now
        await send_temporary(message, required_text(user.full_name, missing), keyboard(message.chat.id, missing))
    return False
