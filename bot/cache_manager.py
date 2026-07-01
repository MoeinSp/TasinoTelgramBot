import os
import django
from asgiref.sync import sync_to_async
from bot import cache

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TasinoAiogram3.settings")


@sync_to_async
def _load_from_db():
    from account.models import TelegramGroup, TelegramGroupMember, LearnedResponse
    from wordfilter.models import WordFilter

    for group in TelegramGroup.objects.filter(is_active=True):
        cid = group.telegram_chat_id

        if group.off:
            cache.OFF_GROUP.add(cid)
        if group.group_lock:
            cache.GROUP_LOCK.add(cid)
        if group.warning_enabled:
            cache.WARNING_ENABLED.add(cid)
        if group.is_speaker_enabled:
            cache.SPEAKER_ON.add(cid)
        if group.dice_option:
            cache.DICE_OPTION.add(cid)

        cache.GROUP_LOCKS[cid] = group.locks
        cache.ADMINS_CACHE.setdefault(cid, set())
        cache.VIP_USERS_CACHE.setdefault(cid, set())

        if not group.welcome_enabled:
            cache.WELCOME_DISABLED.add(cid)
        cache.WELCOME_SETTINGS[cid] = {
            "text": group.welcome_text or "",
            "gif_file_id": group.welcome_gif_file_id or "",
        }

        if group.anti_flood_enabled:
            cache.ANTI_FLOOD_ENABLED.add(cid)
        cache.ANTI_FLOOD_SETTINGS[cid] = {
            "limit": group.anti_flood_limit,
            "window": group.anti_flood_window,
        }

    for member in TelegramGroupMember.objects.filter(
        is_owner=True
    ).select_related("group"):
        if member.group:
            cache.OWNER_CACHE[member.telegram_chat_id] = member.telegram_user_id

    for member in TelegramGroupMember.objects.filter(
        is_admin=True
    ):
        cache.ADMINS_CACHE.setdefault(member.telegram_chat_id, set()).add(
            member.telegram_user_id
        )

    for member in TelegramGroupMember.objects.filter(is_vip=True):
        cache.VIP_USERS_CACHE.setdefault(member.telegram_chat_id, set()).add(
            member.telegram_user_id
        )

    for lr in LearnedResponse.objects.select_related("group"):
        cid = lr.group.telegram_chat_id
        cache.LEARNED_RESPONSES.setdefault(cid, {})[lr.trigger.lower()] = lr.response

    for wf in WordFilter.objects.all():
        cache.WORD_FILTERS.setdefault(wf.chat_id, []).append(wf.word.lower())


async def load_all_caches():
    await _load_from_db()
    cache.CACHE_LOADED = True
    print("Cache loaded OK")


def is_owner(chat_id: int, user_id: int) -> bool:
    return cache.OWNER_CACHE.get(chat_id) == user_id


def is_admin(chat_id: int, user_id: int) -> bool:
    return user_id in cache.ADMINS_CACHE.get(chat_id, set())


def is_vip(chat_id: int, user_id: int) -> bool:
    return user_id in cache.VIP_USERS_CACHE.get(chat_id, set())


def has_privilege(chat_id: int, user_id: int) -> bool:
    return is_owner(chat_id, user_id) or is_admin(chat_id, user_id)
