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
        if getattr(group, "dice_turn_limit", 0):
            cache.DICE_TURN_LIMIT[cid] = int(group.dice_turn_limit)

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

        if group.captcha_enabled:
            cache.CAPTCHA_ENABLED.add(cid)
        cache.CAPTCHA_TIMEOUT[cid] = group.captcha_timeout

        if group.antiraid_enabled:
            cache.ANTIRAID_ENABLED.add(cid)

        if group.night_mode_enabled:
            cache.NIGHT_MODE[cid] = (group.night_start_hour, group.night_end_hour)

        if group.telegram_emoji_enabled:
            cache.TELEGRAM_EMOJI_ON.add(cid)

        if group.log_channel_id:
            cache.LOG_CHANNEL[cid] = group.log_channel_id

        from account.models import default_commands
        cache.ENABLED_COMMANDS[cid] = list(group.enabled_commands or default_commands())
        cache.GROUP_THEME[cid] = int(group.theme or 1)
        cache.MAX_WARNINGS[cid] = int(group.max_warnings or 3)

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

    # لیست سکوت باید بعد از ری‌استارت هم پابرجا بمونه
    for member in TelegramGroupMember.objects.filter(role="muted"):
        cache.MUTED_USERS.setdefault(member.telegram_chat_id, set()).add(
            member.telegram_user_id
        )

    for lr in LearnedResponse.objects.select_related("group"):
        cid = lr.group.telegram_chat_id
        cache.LEARNED_RESPONSES.setdefault(cid, {})[lr.trigger.lower()] = lr.response

    for wf in WordFilter.objects.all():
        cache.WORD_FILTERS.setdefault(wf.chat_id, []).append(wf.word.lower())

    from bot_setting.models import ForcedJoinConfig, BotSiteConfig
    from bot.required_join import apply_forced_join_cache
    from bot.site_config import apply_site_config_cache
    fj = ForcedJoinConfig.get_singleton()
    apply_forced_join_cache({
        "enabled": fj.enabled,
        "channel_id": fj.channel_id,
        "channel_title": fj.channel_title or "",
        "channel_username": fj.channel_username or "",
        "invite_link": fj.invite_link or "",
    })
    sc = BotSiteConfig.get_singleton()
    apply_site_config_cache({
        "bot_enabled": bool(getattr(sc, "bot_enabled", True)),
        "link_directory_url": sc.link_directory_url,
        "link_directory_title": sc.link_directory_title,
        "support_url": sc.support_url,
        "support_title": sc.support_title,
        "channel_url": sc.channel_url or "",
        "premium_emoji_ids": getattr(sc, "premium_emoji_ids", None) or {},
        "dice_themes": getattr(sc, "dice_themes", None) or {},
    })


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
