"""
توابع کمکی مشترک برای همه هندلرها
"""
import re
import ast
import html
import operator as op
from typing import Optional

from aiogram import Bot
from aiogram.types import Message, ChatPermissions
from asgiref.sync import sync_to_async

from bot import cache
from bot.cache_manager import is_owner, is_admin, is_vip, has_privilege


# ─── پرمیشن‌ها ────────────────────────────────────────────────────────────────
# Bot API 6.5+ پرمیشن مدیا رو به فیلدهای جدا تقسیم کرده؛
# فیلد تنظیم‌نشده False حساب می‌شه، پس برای رفع محدودیت باید همه صریحاً True باشن.

def full_permissions() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )


async def unrestrict_user(bot: Bot, chat_id: int, user_id: int) -> bool:
    """محدودیت کاربر رو برمی‌داره (پرمیشن‌های پیش‌فرض گروه اگه در دسترس باشه)."""
    permissions = full_permissions()
    try:
        chat = await bot.get_chat(chat_id)
        if chat.permissions:
            permissions = chat.permissions
    except Exception:
        pass
    try:
        await bot.restrict_chat_member(chat_id, user_id, permissions=permissions)
        return True
    except Exception:
        return False


# ─── safe_send ────────────────────────────────────────────────────────────────

async def safe_send(bot: Bot, chat_id: int, text: str,
                    reply_to: Optional[int] = None,
                    reply_markup=None) -> None:
    try:
        await bot.send_message(
            chat_id, text,
            reply_to_message_id=reply_to,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception as e:
        print(f"safe_send error: {e}")


async def send_private(
    bot: Bot,
    user_id: int,
    text: str,
    reply_markup=None,
) -> bool:
    """ارسال به پیوی کاربر. True اگر موفق باشد."""
    try:
        await bot.send_message(
            user_id, text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return True
    except Exception as e:
        print(f"send_private error ({user_id}): {e}")
        return False


_BALANCE_PM_SUFFIXES = frozenset({"پیوی", "پیو", "در پیوی"})
_BALANCE_GROUP_SUFFIXES = frozenset({
    "گروه", "همون گروه", "همین گروه", "در گروه",
})


def parse_balance_command(text: str) -> tuple[str, bool] | None:
    """('pm'|'group', is_my_balance) | None — موجودی → گروه؛ موجودی پیوی → پیوی."""
    if not text:
        return None
    t = text.strip()
    if "مخفی" in t:
        return None
    parts = t.split()
    if not parts or parts[0] != "موجودی":
        return None
    suffix_parts = parts[1:]
    is_my = False
    if suffix_parts and suffix_parts[0] == "من":
        is_my = True
        suffix_parts = suffix_parts[1:]
    if not suffix_parts:
        return ("group", is_my)
    if len(suffix_parts) == 1:
        s = suffix_parts[0]
        if s in _BALANCE_PM_SUFFIXES:
            return ("pm", is_my)
        if s in _BALANCE_GROUP_SUFFIXES:
            return ("group", is_my)
    return None


async def deliver_private_or_warn(
    bot: Bot,
    group_chat_id: int,
    user_id: int,
    group_msg_id: int,
    text: str,
    reply_markup=None,
) -> bool:
    """گزارش شخصی را به پیوی می‌فرستد."""
    try:
        await bot.send_message(
            user_id, text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        await safe_send(
            bot, group_chat_id,
            "📲 گزارش در پیوی ربات ارسال شد.",
            reply_to=group_msg_id,
        )
        return True
    except Exception as e:
        print(f"deliver_private_or_warn error ({user_id}): {e}")
        await safe_send(
            bot, group_chat_id,
            "⚠️ برای دریافت گزارش ابتدا ربات را در پیوی /start کنید.\n"
            "اگر قبلاً استارت کرده‌اید، ربات را از بلاک خارج کنید و دوباره امتحان کنید.",
            reply_to=group_msg_id,
        )
        return False


async def deliver_balance_sensitive(
    bot: Bot,
    group_chat_id: int,
    viewer_id: int,
    group_msg_id: int,
    text: str,
    *,
    private: bool,
    reply_markup=None,
) -> bool:
    """
    private=True → پیوی؛ private=False → گروه.
    فقط خود شخص و ادمین مجازند (مجوز در caller چک می‌شود).
    """
    if private:
        return await deliver_private_or_warn(
            bot, group_chat_id, viewer_id, group_msg_id, text,
            reply_markup=reply_markup,
        )
    await safe_send(
        bot, group_chat_id, text,
        reply_to=group_msg_id,
        reply_markup=reply_markup,
    )
    return True


# ─── get_target_from_reply ────────────────────────────────────────────────────

async def get_target_from_reply(message: Message, bot: Bot) -> Optional[int]:
    """
    در تلگرام کافیه از reply_to_message بخوانیم.
    اگر ریپلای نباشد یا bot باشد، خطا می‌فرستد و None برمی‌گرداند.
    """
    if not message.reply_to_message:
        await safe_send(bot, message.chat.id,
                        "⚠️ لطفاً روی پیام کاربر مورد نظر ریپلای کنید.",
                        reply_to=message.message_id)
        return None

    target = message.reply_to_message.from_user
    if target is None or target.is_bot:
        await safe_send(bot, message.chat.id,
                        "❌ این کاربر معتبر نیست.",
                        reply_to=message.message_id)
        return None

    return target.id


# ─── user_mention ─────────────────────────────────────────────────────────────

@sync_to_async
def _get_member_name(chat_id: int, user_id: int) -> Optional[str]:
    from account.models import TelegramGroupMember
    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).first()
    if m and m.alias:
        return m.alias
    return None


async def user_mention(user_id: int, chat_id: int = 0,
                       fallback: str = "") -> str:
    name = None
    if chat_id:
        name = await _get_member_name(chat_id, user_id)
    if not name:
        name = fallback or str(user_id)
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


async def user_mention_from_msg(message: Message) -> str:
    u = message.from_user
    name = u.full_name or str(u.id)
    return f'<a href="tg://user?id={u.id}">{html.escape(name)}</a>'


async def user_mention_id(user_id: int, bot: Bot, chat_id: int) -> str:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        name = member.user.full_name or str(user_id)
    except Exception:
        name = str(user_id)
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


# ─── get_user_status ──────────────────────────────────────────────────────────

def get_user_status(chat_id: int, user_id: int):
    """(is_owner, is_admin, is_vip)"""
    return (
        is_owner(chat_id, user_id),
        is_admin(chat_id, user_id),
        is_vip(chat_id, user_id),
    )


# ─── DB helpers ───────────────────────────────────────────────────────────────

@sync_to_async
def db_get_or_create_group(chat_id: int, name: str = ""):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=chat_id,
        defaults={"name": name or str(chat_id)},
    )
    return grp


@sync_to_async
def db_set_group_theme(chat_id: int, theme: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(theme=theme)


@sync_to_async
def db_get_group_theme(chat_id: int) -> int:
    from account.models import TelegramGroup
    grp = TelegramGroup.objects.filter(telegram_chat_id=chat_id).first()
    return grp.theme if grp else 1


@sync_to_async
def db_enable_group_off(chat_id: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(off=True)
    cache.OFF_GROUP.add(chat_id)


@sync_to_async
def db_disable_group_off(chat_id: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(off=False)
    cache.OFF_GROUP.discard(chat_id)


@sync_to_async
def db_enable_group_lock(chat_id: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(group_lock=True)
    cache.GROUP_LOCK.add(chat_id)


@sync_to_async
def db_disable_group_lock(chat_id: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(group_lock=False)
    cache.GROUP_LOCK.discard(chat_id)


@sync_to_async
def db_enable_dice_option(chat_id: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(dice_option=True)
    cache.DICE_OPTION.add(chat_id)


@sync_to_async
def db_disable_dice_option(chat_id: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(dice_option=False)
    cache.DICE_OPTION.discard(chat_id)


@sync_to_async
def db_get_dice_turn_limit(chat_id: int) -> int:
    from account.models import TelegramGroup
    if chat_id in cache.DICE_TURN_LIMIT:
        return int(cache.DICE_TURN_LIMIT.get(chat_id) or 0)
    g = TelegramGroup.objects.filter(telegram_chat_id=chat_id).only("dice_turn_limit").first()
    val = int(getattr(g, "dice_turn_limit", 0) or 0) if g else 0
    cache.DICE_TURN_LIMIT[chat_id] = val
    return val


@sync_to_async
def db_set_dice_turn_limit(chat_id: int, limit: int) -> int:
    from account.models import TelegramGroup
    limit = max(0, int(limit))
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(dice_turn_limit=limit)
    cache.DICE_TURN_LIMIT[chat_id] = limit
    return limit


@sync_to_async
def db_enable_speaker(chat_id: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(is_speaker_enabled=True)
    cache.SPEAKER_ON.add(chat_id)


@sync_to_async
def db_disable_speaker(chat_id: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(is_speaker_enabled=False)
    cache.SPEAKER_ON.discard(chat_id)


@sync_to_async
def db_update_lock(chat_id: int, lock_name: str, value: bool):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    locks = grp.locks or {}
    locks[lock_name] = value
    grp.locks = locks
    grp.save(update_fields=["locks"])
    cache.GROUP_LOCKS[chat_id] = locks


@sync_to_async
def db_get_locks(chat_id: int) -> dict:
    from account.models import TelegramGroup, default_locks
    grp = TelegramGroup.objects.filter(telegram_chat_id=chat_id).first()
    if grp:
        return grp.locks or default_locks()
    return default_locks()


@sync_to_async
def db_set_owner(chat_id: int, user_id: int):
    from account.models import TelegramGroup, TelegramGroupMember
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    TelegramGroupMember.objects.filter(telegram_chat_id=chat_id, is_owner=True).update(
        is_owner=False, role="member"
    )
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    m.is_owner = True
    m.is_admin = True
    m.role = "owner"
    m.save(update_fields=["is_owner", "is_admin", "role"])
    cache.OWNER_CACHE[chat_id] = user_id
    cache.ADMINS_CACHE.setdefault(chat_id, set()).add(user_id)
    cache.VIP_USERS_CACHE.setdefault(chat_id, set()).discard(user_id)


@sync_to_async
def db_has_owner(chat_id: int) -> bool:
    return chat_id in cache.OWNER_CACHE


async def sync_telegram_roles(chat_id: int, bot: Bot) -> dict:
    """همگام‌سازی مالک (creator) و ادمین‌های تلگرام — منبع حقیقت: API تلگرام."""
    try:
        tg_admins = await bot.get_chat_administrators(chat_id)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    old_creator = cache.OWNER_CACHE.get(chat_id)
    creator_id = None
    tg_admin_ids: list[int] = []

    for member in tg_admins:
        if member.user.is_bot:
            continue
        if member.status == "creator":
            creator_id = member.user.id
        elif member.status == "administrator":
            tg_admin_ids.append(member.user.id)

    creator_changed = bool(creator_id and creator_id != old_creator)

    if creator_id:
        await db_set_owner(chat_id, creator_id)

    cache.TG_ADMINS_CACHE[chat_id] = set(tg_admin_ids)

    return {
        "ok": True,
        "creator_id": creator_id,
        "creator_changed": creator_changed,
        "old_creator_id": old_creator,
        "tg_admin_ids": tg_admin_ids,
        "tg_admin_count": len(tg_admin_ids),
    }


async def sync_bot_admins_from_telegram(chat_id: int, bot: Bot, creator_id: int | None = None) -> int:
    """ادمین‌های تلگرام را در لیست ادمین ربات ثبت می‌کند."""
    try:
        tg_admins = await bot.get_chat_administrators(chat_id)
    except Exception:
        return 0
    creator_id = creator_id or cache.OWNER_CACHE.get(chat_id)
    count = 0
    for member in tg_admins:
        if member.user.is_bot or member.status == "creator":
            continue
        if creator_id and member.user.id == creator_id:
            continue
        if member.status == "administrator":
            await db_add_admin(chat_id, member.user.id)
            count += 1
    return count


@sync_to_async
def db_add_admin(chat_id: int, user_id: int):
    from account.models import TelegramGroup, TelegramGroupMember
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    m.is_admin = True
    m.role = "admin"
    m.save(update_fields=["is_admin", "role"])
    cache.ADMINS_CACHE.setdefault(chat_id, set()).add(user_id)
    cache.VIP_USERS_CACHE.setdefault(chat_id, set()).discard(user_id)


@sync_to_async
def db_del_admin(chat_id: int, user_id: int):
    from account.models import TelegramGroupMember
    TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).update(is_admin=False, role="member")
    cache.ADMINS_CACHE.setdefault(chat_id, set()).discard(user_id)


@sync_to_async
def db_add_vip(chat_id: int, user_id: int):
    from account.models import TelegramGroup, TelegramGroupMember
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    m.is_vip = True
    m.role = "vip"
    m.save(update_fields=["is_vip", "role"])
    cache.VIP_USERS_CACHE.setdefault(chat_id, set()).add(user_id)


@sync_to_async
def db_del_vip(chat_id: int, user_id: int):
    from account.models import TelegramGroupMember
    TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).update(is_vip=False, role="member")
    cache.VIP_USERS_CACHE.setdefault(chat_id, set()).discard(user_id)


@sync_to_async
def db_get_admins(chat_id: int) -> list:
    from account.models import TelegramGroupMember
    return list(
        TelegramGroupMember.objects.filter(
            telegram_chat_id=chat_id, is_admin=True
        ).values_list("telegram_user_id", flat=True)
    )


@sync_to_async
def db_get_vips(chat_id: int) -> list:
    from account.models import TelegramGroupMember
    return list(
        TelegramGroupMember.objects.filter(
            telegram_chat_id=chat_id, is_vip=True
        ).values_list("telegram_user_id", flat=True)
    )


@sync_to_async
def db_clear_vips(chat_id: int):
    from account.models import TelegramGroupMember
    TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, is_vip=True
    ).update(is_vip=False, role="member")
    cache.VIP_USERS_CACHE[chat_id] = set()


@sync_to_async
def db_ban_user(chat_id: int, user_id: int):
    from account.models import TelegramGroupMember, TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    m.role = "banned"
    m.save(update_fields=["role"])


@sync_to_async
def db_unban_user(chat_id: int, user_id: int):
    from account.models import TelegramGroupMember
    TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).update(role="member")


@sync_to_async
def db_mute_user(chat_id: int, user_id: int):
    from account.models import TelegramGroupMember, TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    m.role = "muted"
    m.save(update_fields=["role"])


@sync_to_async
def db_unmute_user(chat_id: int, user_id: int):
    from account.models import TelegramGroupMember
    TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).update(role="member")


@sync_to_async
def db_add_warning(chat_id: int, user_id: int) -> int:
    from account.models import TelegramGroupMember, TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    m.warnings += 1
    m.save(update_fields=["warnings"])
    return m.warnings


@sync_to_async
def db_reset_warnings(chat_id: int, user_id: int):
    from account.models import TelegramGroupMember
    TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).update(warnings=0)


@sync_to_async
def db_get_warnings(chat_id: int, user_id: int) -> int:
    from account.models import TelegramGroupMember
    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).first()
    return m.warnings if m else 0


@sync_to_async
def db_get_max_warnings(chat_id: int) -> int:
    from account.models import TelegramGroup
    grp = TelegramGroup.objects.filter(telegram_chat_id=chat_id).first()
    return grp.max_warnings if grp else 3


@sync_to_async
def db_set_max_warnings(chat_id: int, max_w: int):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(max_warnings=max_w)


@sync_to_async
def db_get_group_commands(chat_id: int) -> list:
    from account.models import TelegramGroup
    grp = TelegramGroup.objects.filter(telegram_chat_id=chat_id).first()
    if grp:
        return grp.enabled_commands or []
    from account.models import default_commands
    return default_commands()


@sync_to_async
def db_set_group_commands(chat_id: int, commands: list):
    from account.models import TelegramGroup
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(enabled_commands=commands)


@sync_to_async
def db_toggle_group_command(chat_id: int, cmd: str) -> bool:
    """روشن/خاموش یک دستور — برمی‌گرداند وضعیت جدید (True=فعال)."""
    from account.models import TelegramGroup, default_commands
    grp = TelegramGroup.objects.filter(telegram_chat_id=chat_id).first()
    if not grp:
        TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
        cmds = list(default_commands())
    else:
        cmds = list(grp.enabled_commands or default_commands())
    if cmd in cmds:
        cmds = [c for c in cmds if c != cmd]
        enabled = False
    else:
        if cmd not in cmds:
            cmds.append(cmd)
        enabled = True
    TelegramGroup.objects.filter(telegram_chat_id=chat_id).update(enabled_commands=cmds)
    return enabled


@sync_to_async
def db_get_learned_responses(chat_id: int) -> dict:
    from account.models import TelegramGroup, LearnedResponse
    grp = TelegramGroup.objects.filter(telegram_chat_id=chat_id).first()
    if not grp:
        return {}
    return {lr.trigger.lower(): lr.response
            for lr in LearnedResponse.objects.filter(group=grp)}


@sync_to_async
def db_save_learned_response(chat_id: int, trigger: str, response: str, user_id: int):
    from account.models import TelegramGroup, LearnedResponse
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    obj, _ = LearnedResponse.objects.update_or_create(
        group=grp, trigger=trigger,
        defaults={"response": response, "created_by": user_id}
    )
    cache.LEARNED_RESPONSES.setdefault(chat_id, {})[trigger.lower()] = response


@sync_to_async
def db_delete_learned_response(chat_id: int, trigger: str) -> bool:
    from account.models import TelegramGroup, LearnedResponse
    grp = TelegramGroup.objects.filter(telegram_chat_id=chat_id).first()
    if not grp:
        return False
    deleted, _ = LearnedResponse.objects.filter(group=grp, trigger=trigger).delete()
    if deleted:
        cache.LEARNED_RESPONSES.get(chat_id, {}).pop(trigger.lower(), None)
        return True
    return False


@sync_to_async
def db_add_word_filter(chat_id: int, word: str) -> str:
    from wordfilter.models import WordFilter
    _, created = WordFilter.objects.get_or_create(chat_id=chat_id, word=word.lower())
    if created:
        cache.WORD_FILTERS.setdefault(chat_id, []).append(word.lower())
        return f"✅ کلمه «{word}» به لیست فیلتر اضافه شد."
    return f"⚠️ کلمه «{word}» قبلاً در لیست فیلتر بود."


@sync_to_async
def db_remove_word_filter(chat_id: int, word: str) -> str:
    from wordfilter.models import WordFilter
    deleted, _ = WordFilter.objects.filter(chat_id=chat_id, word=word.lower()).delete()
    if deleted:
        wlist = cache.WORD_FILTERS.get(chat_id, [])
        try:
            wlist.remove(word.lower())
        except ValueError:
            pass
        return f"✅ کلمه «{word}» از لیست فیلتر حذف شد."
    return f"❌ کلمه «{word}» در لیست فیلتر نبود."


@sync_to_async
def db_get_word_filters(chat_id: int) -> list:
    return list(cache.WORD_FILTERS.get(chat_id, []))


@sync_to_async
def db_get_top_users(chat_id: int, limit: int = 10) -> list:
    from account.models import TelegramGroupMember
    return list(
        TelegramGroupMember.objects.filter(telegram_chat_id=chat_id)
        .order_by("-message_count")
        .values("telegram_user_id", "message_count", "level", "xp_total", "alias", "role", "warnings")[:limit]
    )


@sync_to_async
def db_get_member(chat_id: int, user_id: int):
    from account.models import TelegramGroupMember
    return TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).first()


@sync_to_async
def db_register_member(chat_id: int, user_id: int, name: str = ""):
    from account.models import TelegramGroup, TelegramGroupMember
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, created = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    if created and name and not m.alias:
        m.alias = name[:255]
        m.save(update_fields=["alias"])
    return m


@sync_to_async
def db_set_alias(chat_id: int, user_id: int, alias: str):
    from account.models import TelegramGroup, TelegramGroupMember
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    m.alias = alias[:255]
    m.save(update_fields=["alias"])


@sync_to_async
def db_get_alias(chat_id: int, user_id: int) -> Optional[str]:
    from account.models import TelegramGroupMember
    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).first()
    return m.alias if m else None


# ─── خوشامدگویی ───────────────────────────────────────────────────────────────

@sync_to_async
def db_get_welcome(chat_id: int) -> dict:
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    return {
        "enabled": grp.welcome_enabled,
        "text": grp.welcome_text or "",
        "gif_file_id": grp.welcome_gif_file_id or "",
    }


@sync_to_async
def db_set_welcome(chat_id: int, enabled=None, text=None, gif_file_id=None):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    fields = []
    if enabled is not None:
        grp.welcome_enabled = enabled
        fields.append("welcome_enabled")
    if text is not None:
        grp.welcome_text = text
        fields.append("welcome_text")
    if gif_file_id is not None:
        grp.welcome_gif_file_id = gif_file_id
        fields.append("welcome_gif_file_id")
    if fields:
        grp.save(update_fields=fields)


# ─── آنتی فلود ────────────────────────────────────────────────────────────────

@sync_to_async
def db_get_anti_flood(chat_id: int) -> dict:
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    return {
        "enabled": grp.anti_flood_enabled,
        "limit": grp.anti_flood_limit,
        "window": grp.anti_flood_window,
    }


@sync_to_async
def db_set_anti_flood(chat_id: int, enabled=None, limit=None, window=None):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    fields = []
    if enabled is not None:
        grp.anti_flood_enabled = enabled
        fields.append("anti_flood_enabled")
    if limit is not None:
        grp.anti_flood_limit = limit
        fields.append("anti_flood_limit")
    if window is not None:
        grp.anti_flood_window = window
        fields.append("anti_flood_window")
    if fields:
        grp.save(update_fields=fields)


# ─── کپچا ─────────────────────────────────────────────────────────────────────

@sync_to_async
def db_get_captcha(chat_id: int) -> dict:
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    return {"enabled": grp.captcha_enabled, "timeout": grp.captcha_timeout}


@sync_to_async
def db_set_captcha(chat_id: int, enabled=None, timeout=None):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    fields = []
    if enabled is not None:
        grp.captcha_enabled = enabled
        fields.append("captcha_enabled")
    if timeout is not None:
        grp.captcha_timeout = timeout
        fields.append("captcha_timeout")
    if fields:
        grp.save(update_fields=fields)


# ─── ضد رید ───────────────────────────────────────────────────────────────────

@sync_to_async
def db_set_antiraid(chat_id: int, enabled: bool):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    grp.antiraid_enabled = enabled
    grp.save(update_fields=["antiraid_enabled"])


# ─── کانال لاگ ────────────────────────────────────────────────────────────────

@sync_to_async
def db_set_log_channel(chat_id: int, log_channel_id: int | None):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    grp.log_channel_id = log_channel_id
    grp.save(update_fields=["log_channel_id"])


async def log_action(bot, chat_id: int, text: str) -> None:
    """اگه کانال لاگ برای گروه تنظیم شده باشه، متن رو اونجا می‌فرسته."""
    log_chat_id = cache.LOG_CHANNEL.get(chat_id)
    if not log_chat_id:
        return
    try:
        await bot.send_message(log_chat_id, text, parse_mode="HTML")
    except Exception as e:
        print(f"log_action error: {e}")


# ─── قوانین گروه ──────────────────────────────────────────────────────────────

@sync_to_async
def db_set_rules(chat_id: int, text: str | None):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    grp.rules_text = text
    grp.save(update_fields=["rules_text"])


@sync_to_async
def db_get_rules(chat_id: int) -> Optional[str]:
    from account.models import TelegramGroup
    grp = TelegramGroup.objects.filter(telegram_chat_id=chat_id).first()
    return grp.rules_text if grp else None


# ─── حالت شب ──────────────────────────────────────────────────────────────────

@sync_to_async
def db_set_night_mode(chat_id: int, enabled: bool, start_hour: int = None, end_hour: int = None):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    grp.night_mode_enabled = enabled
    fields = ["night_mode_enabled"]
    if start_hour is not None:
        grp.night_start_hour = start_hour
        fields.append("night_start_hour")
    if end_hour is not None:
        grp.night_end_hour = end_hour
        fields.append("night_end_hour")
    grp.save(update_fields=fields)


def is_night_time(chat_id: int) -> bool:
    """آیا الان در بازه‌ی حالت شب این گروه هستیم؟ (ساعت محلی سرور)"""
    cfg = cache.NIGHT_MODE.get(chat_id)
    if not cfg:
        return False
    start, end = cfg
    import datetime
    hour = datetime.datetime.now().hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def telegram_emoji_on(chat_id: int) -> bool:
    return chat_id in cache.TELEGRAM_EMOJI_ON


@sync_to_async
def db_set_telegram_emoji(chat_id: int, enabled: bool):
    from account.models import TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    grp.telegram_emoji_enabled = enabled
    grp.save(update_fields=["telegram_emoji_enabled"])
    if enabled:
        cache.TELEGRAM_EMOJI_ON.add(chat_id)
    else:
        cache.TELEGRAM_EMOJI_ON.discard(chat_id)


# ─── یادداشت‌ها (Notes) ───────────────────────────────────────────────────────

@sync_to_async
def db_save_note(chat_id: int, name: str, content: str, user_id: int) -> None:
    from account.models import TelegramGroup, Note
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    Note.objects.update_or_create(
        group=grp, name=name,
        defaults={"content": content, "created_by": user_id},
    )


@sync_to_async
def db_get_note(chat_id: int, name: str) -> Optional[str]:
    from account.models import Note
    note = Note.objects.filter(group__telegram_chat_id=chat_id, name=name).first()
    return note.content if note else None


@sync_to_async
def db_delete_note(chat_id: int, name: str) -> bool:
    from account.models import Note
    deleted, _ = Note.objects.filter(group__telegram_chat_id=chat_id, name=name).delete()
    return deleted > 0


@sync_to_async
def db_list_notes(chat_id: int) -> list[str]:
    from account.models import Note
    return list(
        Note.objects.filter(group__telegram_chat_id=chat_id)
        .order_by("name").values_list("name", flat=True)
    )


# ─── calc ────────────────────────────────────────────────────────────────────

_ALLOWED_OPS = {
    ast.Add: op.add, ast.Sub: op.sub,
    ast.Mult: op.mul, ast.Div: op.truediv,
    ast.USub: op.neg, ast.UAdd: op.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        fn = _ALLOWED_OPS.get(type(node.op))
        if fn is None:
            raise ValueError
        return fn(left, right)
    if isinstance(node, ast.UnaryOp):
        fn = _ALLOWED_OPS.get(type(node.op))
        if fn is None:
            raise ValueError
        return fn(_eval_node(node.operand))
    raise ValueError


def safe_calc(expr: str) -> Optional[str]:
    expr = expr.replace(" ", "").replace("×", "*").replace("÷", "/")
    if not re.fullmatch(r"[0-9+\-*/().]+", expr):
        return None
    try:
        result = _eval_node(ast.parse(expr, mode="eval").body)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result)
    except Exception:
        return None


@sync_to_async
def db_get_all_members_balance(chat_id: int) -> list:
    from account.models import TelegramGroupMember
    return list(
        TelegramGroupMember.objects.filter(telegram_chat_id=chat_id)
        .order_by("-point")
        .values("telegram_user_id", "alias", "point", "message_count", "level")
    )


@sync_to_async
def db_update_point(chat_id: int, user_id: int, delta: int):
    from account.models import TelegramGroup, TelegramGroupMember
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    m.point = (m.point or 0) + delta
    m.save(update_fields=["point"])
    return m.point


@sync_to_async
def db_get_point(chat_id: int, user_id: int) -> int:
    from account.models import TelegramGroupMember
    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).first()
    return m.point if m else 0


@sync_to_async
def db_get_group_fee(chat_id: int) -> int:
    from account.models import TelegramGroup
    grp = TelegramGroup.objects.filter(telegram_chat_id=chat_id).first()
    return grp.fee_percent if grp and grp.fee_percent is not None else 10


# ─── lock map ────────────────────────────────────────────────────────────────

LOCK_MAP = {
    "لینک": "link",
    "فوروارد": "forward",
    "ایدی": "username",
    "یوزرنیم": "username",
    "منشن": "username",
    "گیف": "gif",
    "عکس": "photo",
    "مدیا": "media",
    "کلمات": "bad_words",
    "ادیت": "edit_message",
    "ویرایش": "edit_message",
    "سرگرمی": "fun_text",
    "استیکر": "sticker",
    "ویس": "voice",
    "ویدیو": "video",
    "فیلم": "video",
    "ویدیو مسیج": "video_note",
    "ویدئو مسیج": "video_note",
    "موزیک": "audio",
    "آهنگ": "audio",
    "فایل": "document",
    "مخاطب": "contact",
    "لوکیشن": "location",
    "موقعیت": "location",
    "نظرسنجی": "poll",
    "اینلاین": "via_bot",
    "بازی": "game",
}

# نام نمایشی هر قفل (کلید انگلیسی ← برچسب فارسی)
LOCK_NAMES = {
    "link": "لینک",
    "forward": "فوروارد",
    "username": "یوزرنیم",
    "gif": "گیف",
    "photo": "عکس",
    "media": "مدیا",
    "bad_words": "کلمات",
    "edit_message": "ادیت",
    "fun_text": "سرگرمی",
    "sticker": "استیکر",
    "voice": "ویس",
    "video": "ویدیو",
    "video_note": "ویدیو مسیج",
    "audio": "موزیک",
    "document": "فایل",
    "contact": "مخاطب",
    "location": "لوکیشن",
    "poll": "نظرسنجی",
    "via_bot": "اینلاین",
    "game": "بازی",
}

# ترتیب اولویت نمایش و پنل (مهم‌ترین‌ها بالاتر)
LOCK_ORDER = [
    "link", "forward", "username",
    "gif", "photo", "video", "sticker", "voice", "video_note",
    "audio", "document", "media",
    "contact", "location", "poll", "via_bot", "game",
    "bad_words", "edit_message", "fun_text",
]

ALL_TOGGLEABLE = list(LOCK_MAP.keys())

# ─── contains helpers ─────────────────────────────────────────────────────────

URL_RE = re.compile(
    r"(https?://|t\.me/|telegram\.me/|www\.\w|\w+\.(com|ir|org|net|io)\b)", re.IGNORECASE
)
USERNAME_RE = re.compile(r"@\w{4,}")


def contains_link(text: str) -> bool:
    return bool(URL_RE.search(text))


def contains_username(text: str) -> bool:
    return bool(USERNAME_RE.search(text))


# ─── آمار تاس ────────────────────────────────────────────────────────────────

@sync_to_async
def db_record_dice_roll(chat_id: int, user_id: int, value: int):
    from account.models import DiceRollStat
    DiceRollStat.objects.create(
        telegram_chat_id=chat_id,
        telegram_user_id=user_id,
        value=value,
    )


@sync_to_async
def db_get_dice_stats(chat_id: int, period: str) -> list:
    """
    period: 'daily' | 'weekly' | 'total'
    returns list of dicts: {user_id, rolls, total, avg, max_val, min_val}
    """
    from django.db import connection
    from django.utils import timezone
    import datetime

    now = timezone.now()
    if period == "daily":
        since = now - datetime.timedelta(days=1)
        where = "AND rolled_at >= %s"
        params = [chat_id, since]
    elif period == "weekly":
        since = now - datetime.timedelta(weeks=1)
        where = "AND rolled_at >= %s"
        params = [chat_id, since]
    else:
        where = ""
        params = [chat_id]

    sql = f"""
        SELECT
            telegram_user_id,
            COUNT(*)        AS rolls,
            SUM(value)      AS total,
            ROUND(AVG(value)::numeric, 2) AS avg,
            MAX(value)      AS max_val,
            MIN(value)      AS min_val
        FROM account_dicerollstat
        WHERE telegram_chat_id = %s {where}
        GROUP BY telegram_user_id
        ORDER BY rolls DESC
        LIMIT 20
    """
    with connection.cursor() as c:
        c.execute(sql, params)
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, row)) for row in c.fetchall()]


# ─── کارت بانکی ──────────────────────────────────────────────────────────────

@sync_to_async
def db_update_card(chat_id: int, user_id: int, card_number: str, card_name: str, is_owner_or_admin: bool) -> str:
    import re
    from account.models import TelegramGroupMember, TelegramGroup
    grp, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"group": grp}
    )
    if not is_owner_or_admin:
        m.card_number = card_number
        m.card_number2 = None
        m.card_number3 = None
        m.card_name = card_name
        m.save(update_fields=["card_number", "card_number2", "card_number3", "card_name"])
        return f"✅ کارت با موفقیت ثبت شد.\n💳 <code>{card_number}</code>\n👤 به نام: {card_name}"
    # ادمین/مالک → ۳ کارت
    cards = [m.card_number, m.card_number2, m.card_number3]
    if card_number in cards:
        idx = cards.index(card_number)
    else:
        try:
            idx = cards.index(None)
        except ValueError:
            return "❌ حداکثر ۳ کارت می‌توانید ثبت کنید."
    fields = ["card_number", "card_number2", "card_number3"]
    setattr(m, fields[idx], card_number)
    m.card_name = card_name
    m.save(update_fields=[fields[idx], "card_name"])
    return f"✅ کارت ذخیره شد:\n💳 <code>{card_number}</code>\n👤 به نام: {card_name}"


@sync_to_async
def db_get_card(chat_id: int, user_id: int, role: str) -> str:
    """role: 'owner' | 'admin' | 'member'"""
    from account.models import TelegramGroupMember
    if role == "owner":
        m = TelegramGroupMember.objects.filter(
            telegram_chat_id=chat_id, role="owner"
        ).first()
        if not m:
            m = TelegramGroupMember.objects.filter(
                telegram_chat_id=chat_id, is_owner=True
            ).first()
    else:
        m = TelegramGroupMember.objects.filter(
            telegram_chat_id=chat_id, telegram_user_id=user_id
        ).first()
    if not m:
        return "❌ کاربر در دیتابیس یافت نشد."
    cards = [c for c in [m.card_number, m.card_number2, m.card_number3] if c]
    if not cards:
        if role == "owner":
            return "❌ مالک گروه هیچ شماره کارتی ثبت نکرده است."
        return "❌ هیچ شماره کارتی ثبت نشده است."
    name = m.card_name or "نامشخص"
    if role in ("owner", "admin"):
        lines = [
            "💳 <b>اطلاعات حساب بانکی</b>",
            f"{'👑 مالک گروه' if role == 'owner' else '🛡️ ادمین'}",
            "┄┄┄┄┄┄┄┄┄┄┄┄┄",
            "لطفاً جهت واریز از شماره‌های زیر استفاده کنید:\n",
        ]
        for i, c in enumerate(cards, 1):
            lines.append(f"شماره کارت {i}:\n<code>{c}</code>\n")
        lines.append(f"👤 به نام: <b>{name}</b>")
        lines.append("┄┄┄┄┄┄┄┄┄┄┄┄┄")
        lines.append("🙏 پس از واریز رسید را ارسال کنید.")
        return "\n".join(lines)
    return f"💳 شماره کارت:\n<code>{cards[0]}</code>\n👤 به نام: {name}"


@sync_to_async
def db_delete_card(chat_id: int, user_id: int, arg: str = None) -> str:
    """
    arg می‌تونه باشه:
      - خالی       → حذف همه (با تأیید ضمنی)
      - "1"/"2"/"3" → حذف کارت بر اساس شماره ردیف
      - ۱۶ رقم     → حذف کارت بر اساس شماره دقیق
    """
    from account.models import TelegramGroupMember
    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=chat_id, telegram_user_id=user_id
    ).first()
    if not m:
        return "❌ کارتی ثبت نشده است."

    fields = ["card_number", "card_number2", "card_number3"]
    cards = [getattr(m, f) for f in fields]
    active = [(i, c) for i, c in enumerate(cards) if c]

    if not active:
        return "❌ کارتی ثبت نشده است."

    # حذف بر اساس ردیف (1، 2، 3)
    if arg and arg.strip() in ("1", "2", "3"):
        idx = int(arg.strip()) - 1
        if idx >= len(active):
            return f"❌ کارت شماره {arg.strip()} وجود ندارد.\n\nکارت‌های فعلی شما: {len(active)} عدد"
        real_idx, card_val = active[idx]
        setattr(m, fields[real_idx], None)
        m.save(update_fields=[fields[real_idx]])
        return f"✅ کارت {arg.strip()} حذف شد:\n<code>{card_val}</code>"

    # حذف بر اساس شماره کارت کامل
    if arg and len(arg) == 16 and arg.isdigit():
        found_idx = None
        for i, c in enumerate(cards):
            if c == arg:
                found_idx = i
                break
        if found_idx is None:
            return f"❌ کارت <code>{arg}</code> در لیست شما نیست."
        setattr(m, fields[found_idx], None)
        m.save(update_fields=[fields[found_idx]])
        return f"✅ کارت حذف شد:\n<code>{arg}</code>"

    # بدون آرگومان → حذف همه
    m.card_number = None
    m.card_number2 = None
    m.card_number3 = None
    m.card_name = None
    m.save(update_fields=["card_number", "card_number2", "card_number3", "card_name"])
    return f"✅ {len(active)} کارت حذف شد."
