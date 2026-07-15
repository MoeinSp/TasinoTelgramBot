"""اطلاع‌رسانی مدیران و نام‌نمایشی."""
from __future__ import annotations

from aiogram import Bot

from bot import cache


async def collect_manager_ids(bot: Bot, chat_id: int) -> list[int]:
    """ادمین‌های ربات + مالک + ادمین‌های تلگرام گروه."""
    ids: set[int] = set()
    ids |= {int(x) for x in (cache.ADMINS_CACHE.get(chat_id, set()) or set())}
    owner = cache.OWNER_CACHE.get(chat_id)
    if owner:
        ids.add(int(owner))
    try:
        from bot.helpers import db_get_admins

        for uid in await db_get_admins(chat_id):
            ids.add(int(uid))
    except Exception:
        pass
    try:
        for adm in await bot.get_chat_administrators(chat_id):
            if adm.user.is_bot:
                continue
            ids.add(int(adm.user.id))
    except Exception:
        pass
    return list(ids)


async def notify_other_admins(bot: Bot, chat_id: int, actor_id: int, text: str) -> None:
    for uid in await collect_manager_ids(bot, chat_id):
        if uid == int(actor_id):
            continue
        try:
            await bot.send_message(uid, text)
        except Exception:
            pass
