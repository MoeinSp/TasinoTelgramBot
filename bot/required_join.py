"""جوین اجباری کانال — بررسی عضویت در پیوی ربات."""
from __future__ import annotations

import time

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from asgiref.sync import sync_to_async

from bot import cache
from bot.constants import CREATOR_USER_ID

_JOINED_STATUSES = frozenset({
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.RESTRICTED,
})

_CREATOR_SETUP_PREFIXES = (
    "تنظیم کانال اجباری",
    "جوین اجباری",
    "حذف کانال اجباری",
    "پاک کردن کانال اجباری",
    "فعال کردن جوین اجباری",
    "غیرفعال کردن جوین اجباری",
)


def is_creator(user_id: int) -> bool:
    return user_id == CREATOR_USER_ID


def is_forced_join_active() -> bool:
    cfg = cache.FORCED_JOIN
    return bool(cfg.get("enabled") and cfg.get("channel_id"))


def is_creator_setup_message(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip()
    return any(t.startswith(p) for p in _CREATOR_SETUP_PREFIXES)


@sync_to_async
def db_load_forced_join() -> dict:
    from bot_setting.models import ForcedJoinConfig
    cfg = ForcedJoinConfig.get_singleton()
    return {
        "enabled": cfg.enabled,
        "channel_id": cfg.channel_id,
        "channel_title": cfg.channel_title or "",
        "channel_username": cfg.channel_username or "",
        "invite_link": cfg.invite_link or "",
    }


def apply_forced_join_cache(data: dict) -> None:
    cache.FORCED_JOIN.clear()
    cache.FORCED_JOIN.update(data)
    cache.FORCED_JOIN_MEMBER_CHECK.clear()


@sync_to_async
def db_save_forced_join_channel(
    channel_id: int,
    title: str = "",
    username: str = "",
    invite_link: str = "",
    enabled: bool = True,
) -> dict:
    from bot_setting.models import ForcedJoinConfig
    cfg = ForcedJoinConfig.get_singleton()
    cfg.channel_id = channel_id
    cfg.channel_title = title or ""
    cfg.channel_username = (username or "").lstrip("@")
    cfg.invite_link = invite_link or ""
    cfg.enabled = enabled
    cfg.save()
    data = {
        "enabled": cfg.enabled,
        "channel_id": cfg.channel_id,
        "channel_title": cfg.channel_title,
        "channel_username": cfg.channel_username,
        "invite_link": cfg.invite_link,
    }
    apply_forced_join_cache(data)
    return data


@sync_to_async
def db_set_forced_join_enabled(enabled: bool) -> dict:
    from bot_setting.models import ForcedJoinConfig
    cfg = ForcedJoinConfig.get_singleton()
    cfg.enabled = enabled
    cfg.save(update_fields=["enabled", "updated_at"])
    data = {
        "enabled": cfg.enabled,
        "channel_id": cfg.channel_id,
        "channel_title": cfg.channel_title or "",
        "channel_username": cfg.channel_username or "",
        "invite_link": cfg.invite_link or "",
    }
    apply_forced_join_cache(data)
    return data


@sync_to_async
def db_clear_forced_join() -> dict:
    from bot_setting.models import ForcedJoinConfig
    cfg = ForcedJoinConfig.get_singleton()
    cfg.enabled = False
    cfg.channel_id = None
    cfg.channel_title = ""
    cfg.channel_username = ""
    cfg.invite_link = ""
    cfg.save()
    data = {
        "enabled": False,
        "channel_id": None,
        "channel_title": "",
        "channel_username": "",
        "invite_link": "",
    }
    apply_forced_join_cache(data)
    return data


async def reload_forced_join_cache() -> dict:
    data = await db_load_forced_join()
    apply_forced_join_cache(data)
    return data


async def resolve_channel_invite_link(bot: Bot, channel_id: int, username: str | None) -> str:
    if username:
        return f"https://t.me/{username.lstrip('@')}"
    try:
        return await bot.export_chat_invite_link(channel_id)
    except Exception:
        try:
            link = await bot.create_chat_invite_link(channel_id)
            return link.invite_link
        except Exception:
            return ""


async def verify_bot_channel_access(bot: Bot, channel_id: int) -> tuple[bool, str]:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(channel_id, me.id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            return False, "ربات در این کانال ادمین نیست. ابتدا ربات را ادمین کانال کنید."
        return True, ""
    except Exception as e:
        return False, f"دسترسی به کانال ممکن نیست: {e}"


async def is_user_channel_member(bot: Bot, user_id: int, bypass_cache: bool = False) -> bool:
    if not is_forced_join_active():
        return True
    if is_creator(user_id):
        return True
    channel_id = cache.FORCED_JOIN.get("channel_id")
    if not channel_id:
        return True
    key = (int(channel_id), int(user_id))
    now = time.monotonic()
    cached = cache.FORCED_JOIN_MEMBER_CHECK.get(key)
    if (not bypass_cache) and cached and cached[1] > now:
        return cached[0]
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        is_joined = member.status in _JOINED_STATUSES
        ttl = 300.0 if is_joined else 20.0
        cache.FORCED_JOIN_MEMBER_CHECK[key] = (is_joined, now + ttl)
        return is_joined
    except Exception:
        # در خطاهای لحظه‌ای شبکه، کمی کش کوتاه می‌زنیم تا هر آپدیت دوباره ریکوئست نشود.
        cache.FORCED_JOIN_MEMBER_CHECK[key] = (False, now + 8.0)
        return False


def join_required_keyboard() -> InlineKeyboardMarkup:
    cfg = cache.FORCED_JOIN
    rows = []
    link = cfg.get("invite_link") or ""
    username = cfg.get("channel_username") or ""
    if not link and username:
        link = f"https://t.me/{username.lstrip('@')}"
    if link:
        rows.append([InlineKeyboardButton(text="📣 عضویت در کانال", url=link)])
    rows.append([InlineKeyboardButton(text="✅ بررسی مجدد عضویت", callback_data="join:recheck")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def join_required_text() -> str:
    cfg = cache.FORCED_JOIN
    title = cfg.get("channel_title") or "کانال رسمی تاسینو"
    username = cfg.get("channel_username") or ""
    channel_line = f"@{username.lstrip('@')}" if username else "کانال اصلی ربات"
    return (
        "🔒 <b>دسترسی به ربات نیازمند عضویت است</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "برای استفاده از خدمات ربات تاسینو در پیام خصوصی، "
        "ابتدا باید عضو کانال رسمی ما باشید.\n\n"
        f"📣 کانال: <b>{title}</b>\n"
        f"🔗 {channel_line}\n\n"
        "۱. روی دکمه «عضویت در کانال» بزنید\n"
        "۲. پس از عضویت، «بررسی مجدد» را بزنید\n\n"
        "<i>پس از تأیید عضویت، تمام امکانات ربات برای شما فعال می‌شود.</i>"
    )


def creator_status_text() -> str:
    cfg = cache.FORCED_JOIN
    if not cfg.get("channel_id"):
        return (
            "📋 <b>وضعیت جوین اجباری</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚫ کانال تنظیم نشده\n"
            "⚫ سیستم غیرفعال\n\n"
            "<b>تنظیم:</b>\n"
            "• <code>تنظیم کانال اجباری -1001234567890</code>\n"
            "• یا یک پیام از کانال را فوروارد کنید"
        )
    status = "🟢 فعال" if cfg.get("enabled") else "⚫ غیرفعال"
    uname = f"@{cfg['channel_username']}" if cfg.get("channel_username") else "—"
    return (
        "📋 <b>وضعیت جوین اجباری</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📣 کانال: <b>{cfg.get('channel_title') or '—'}</b>\n"
        f"🔗 {uname}\n"
        f"⚙️ وضعیت: {status}\n\n"
        "<b>دستورات:</b>\n"
        "• <code>جوین اجباری روشن</code>\n"
        "• <code>جوین اجباری خاموش</code>\n"
        "• <code>حذف کانال اجباری</code>"
    )
