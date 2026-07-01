"""
هندلر اصلی گروه — پورت کامل از rubpy/bot/bot.py
"""
import asyncio
import re
import secrets

import jdatetime
from aiogram import Bot, Router, F
from aiogram.types import Message, ChatPermissions, CallbackQuery
from asgiref.sync import sync_to_async

from bot import cache
from bot.cache_manager import is_owner, is_admin, is_vip, has_privilege
from bot.helpers import (
    safe_send, get_target_from_reply, user_mention, user_mention_id,
    get_user_status,
    db_set_group_theme, db_get_group_theme,
    db_enable_group_off, db_disable_group_off,
    db_enable_group_lock, db_disable_group_lock,
    db_enable_dice_option, db_disable_dice_option,
    db_enable_speaker, db_disable_speaker,
    db_update_lock, db_get_locks,
    db_set_owner,
    db_add_admin, db_del_admin,
    db_add_vip, db_del_vip,
    db_get_admins, db_get_vips, db_clear_vips,
    db_add_warning, db_reset_warnings, db_get_warnings, db_get_max_warnings, db_set_max_warnings,
    db_get_group_commands, db_set_group_commands,
    db_add_word_filter, db_remove_word_filter, db_get_word_filters,
    db_save_learned_response, db_delete_learned_response, db_get_learned_responses,
    db_get_top_users, db_get_member, db_register_member,
    db_set_alias, db_get_alias,
    db_get_all_members_balance, db_update_point, db_get_point, db_get_group_fee,
    db_ban_user, db_unban_user, db_mute_user, db_unmute_user,
    db_get_dice_stats, db_record_dice_roll,
    db_update_card, db_get_card, db_delete_card,
    safe_calc, LOCK_MAP, LOCK_NAMES,
    db_set_welcome, db_set_anti_flood,
)
from bot.group_help import get_page, PAGE_MAIN
from bot.panel_keyboards import get_panel, panel_main
from bot.constants import DEFAULT_WELCOME_TEXT, DEFAULT_WELCOME_GIF_FILE_ID
from bot.dice_game import (
    THEMES, has_active_game, get_game, create_game, delete_game, finish_game_cleanup,
    handle_dice, handle_round_selection, WAITING_ROUNDS, ACTIVE_GAMES as DICE_ACTIVE_GAMES,
    is_user_in_game, can_player_roll, save_roll_result, register_and_save_dice,
    should_continue, LAST_DICE,
    _handle_game_roll_silent,
)

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# دستورات سرگرمی/بازی
ALL_TOGGLEABLE_CMDS = [
    "جوک", "فال", "دانستنی", "فکت", "سخن", "معما", "دو راهی", "چالش", "شخصیت",
    "تاس", "بسکتبال", "پنالتی", "بولینگ", "سنگ کاغذ قیچی", "دارت", "شانس", "سکه", "اسلات", "بازی",
]

# ─── helpers داخلی ───────────────────────────────────────────────────────────

async def _reply(message: Message, text: str):
    await safe_send(message.bot, message.chat.id, text, reply_to=message.message_id)


async def _mention(user_id: int, bot: Bot, chat_id: int) -> str:
    return await user_mention_id(user_id, bot, chat_id)


# ─── نصب و فعال‌سازی ─────────────────────────────────────────────────────────
# (هندلر اصلی پایین‌تر تعریف شده: cmd_install_full)


@router.message(F.text == "مالک فیکس")
async def cmd_fix_owner(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return
    await db_set_owner(chat_id, user_id)
    await _reply(message, "✅ مالکیت تثبیت شد.")


# ─── ربات خاموش/روشن ─────────────────────────────────────────────────────────

@router.message(F.text.in_(["ربات خاموش", "ربات روشن"]))
async def cmd_bot_toggle(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return
    if message.text == "ربات خاموش":
        await db_enable_group_off(chat_id)
        return await _reply(message,
            "ربات با موفقیت خاموش شد\n"
            "از این پس ربات به هیچ دستوری جواب نمی‌دهد\n"
            "برای روشن کردن ربات از دستور ربات روشن استفاده نمایید")
    else:
        await db_disable_group_off(chat_id)
        return await _reply(message, "ربات روشن شد.")


# ─── تاس تم ──────────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^(تاس\s+)?تم\s+(\d+)$"))
async def cmd_dice_theme(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط ادمین‌ها می‌توانند تم را تغییر دهند.")
    m = re.search(r"\d+", message.text)
    if not m:
        return
    theme = int(m.group())
    if not 1 <= theme <= 15:
        return await _reply(message, "❌ تم باید بین ۱ تا ۱۵ باشد.")
    await db_set_group_theme(chat_id, theme)
    return await _reply(message, f"✅ تم تاس به {theme} تغییر یافت.")


# ─── دستور روشن/خاموش ────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^(.+)\s+(روشن|خاموش)$"))
async def cmd_toggle_command(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    parts = message.text.rsplit(" ", 1)
    if len(parts) != 2:
        return
    cmd_name, state = parts
    if cmd_name not in ALL_TOGGLEABLE_CMDS:
        return
    group_cmds = await db_get_group_commands(chat_id)
    if state == "روشن":
        if cmd_name not in group_cmds:
            group_cmds.append(cmd_name)
        await db_set_group_commands(chat_id, group_cmds)
        return await _reply(message, f"✅ دستور «{cmd_name}» روشن شد.")
    else:
        group_cmds = [c for c in group_cmds if c != cmd_name]
        await db_set_group_commands(chat_id, group_cmds)
        return await _reply(message, f"❌ دستور «{cmd_name}» خاموش شد.")


@router.message(F.text.in_(["دستورات خاموش", "لیست دستورات خاموش", "لیست خاموش"]))
async def cmd_list_disabled(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    group_cmds = await db_get_group_commands(chat_id)
    disabled = [c for c in ALL_TOGGLEABLE_CMDS if c not in group_cmds]
    if not disabled:
        return await _reply(message, "✅ هیچ دستوری خاموش نیست.")
    txt = "🚫 دستورات خاموش این گروه:\n\n" + "\n".join(f"• {c}" for c in disabled)
    return await _reply(message, txt)


# تاس متوالی — هندلر اصلی پایین‌تر (cmd_dice_option_on / cmd_dice_option_off)


# ─── قفل‌ها ───────────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^قفل\s+(.+)$"))
async def cmd_lock(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    lock_name = message.text[5:].strip()
    if lock_name == "گروه":
        if chat_id in cache.GROUP_LOCK:
            return await _reply(message, ">• قفل گروه در حال حاضر فعال است!\nبا دستور باز کردن گروه می‌توانید دوباره گروه رو باز کنید")
        await db_enable_group_lock(chat_id)
        return await _reply(message, ">• قفل گروه با موفقیت فعال شد.\nبا دستور باز کردن گروه می‌توانید دوباره گروه رو باز کنید")
    lock_key = LOCK_MAP.get(lock_name)
    if not lock_key:
        return
    await db_update_lock(chat_id, lock_key, True)
    return await _reply(message, f"🔒 قفل «{lock_name}» فعال شد.")


@router.message(F.text.regexp(r"^(بازکردن|باز کردن)\s+(.+)$"))
async def cmd_unlock(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    lock_name = parts[1].strip()
    if lock_name in ["گروه", "قفل گروه"]:
        if chat_id not in cache.GROUP_LOCK:
            return await _reply(message, "> • قفل گروه در حال حاضر غیرفعال است!")
        await db_disable_group_lock(chat_id)
        return await _reply(message, ">• قفل گروه با موفقیت غیرفعال شد.")
    lock_key = LOCK_MAP.get(lock_name)
    if not lock_key:
        return
    await db_update_lock(chat_id, lock_key, False)
    return await _reply(message, f"🔓 قفل «{lock_name}» غیرفعال شد.")


@router.message(F.text.in_(["باز کردن گروه", "گروه باز", "بازکردن گروه", "بازکردن قفل گروه", "باز کردن قفل گروه"]))
async def cmd_unlock_group(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if chat_id not in cache.GROUP_LOCK:
        return await _reply(message, "> • قفل گروه در حال حاضر غیرفعال است!")
    await db_disable_group_lock(chat_id)
    return await _reply(message, ">• قفل گروه با موفقیت غیرفعال شد.")


# قفل ها — هندلر اصلی پایین‌تر (cmd_lock_status_full)


# ─── ادمین مدیریت ────────────────────────────────────────────────────────────

@router.message(F.text.in_(["ادمین", "افزودن ادمین"]))
async def cmd_add_admin(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط مالک می‌تواند ادمین اضافه کند.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    if is_owner(chat_id, target_id):
        return await _reply(message, "❌ این کاربر مالک است.")
    await db_add_admin(chat_id, target_id)
    mention = await _mention(target_id, bot, chat_id)
    return await _reply(message, f"✅ {mention}\n\n›› به ادمین‌های گروه اضافه شد.")


@router.message(F.text == "حذف ادمین")
async def cmd_del_admin(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط مالک می‌تواند ادمین حذف کند.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    if is_owner(chat_id, target_id):
        return await _reply(message, "❌ نمی‌توان مالک را از ادمین حذف کرد.")
    await db_del_admin(chat_id, target_id)
    mention = await _mention(target_id, bot, chat_id)
    return await _reply(message, f"✅ {mention}\n\n›› از ادمین‌های گروه حذف شد.")


# لیست ادمین — هندلر اصلی پایین‌تر (cmd_list_admins_full)


# ─── انتقال مالکیت ───────────────────────────────────────────────────────────

@router.message(F.text == "انتقال مالکیت")
async def cmd_transfer_owner(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط مالک می‌تواند مالکیت را منتقل کند.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    if target_id == user_id:
        return await _reply(message, "❌ نمی‌توانید مالکیت را به خودتان منتقل کنید.")
    await db_set_owner(chat_id, target_id)
    mention = await _mention(target_id, bot, chat_id)
    old_mention = await _mention(user_id, bot, chat_id)
    return await _reply(message, f"✅ مالکیت از {old_mention} به {mention} منتقل شد.")


# ─── عضو ویژه ─────────────────────────────────────────────────────────────────

@router.message(F.text.in_(["ویژه", "افزودن ویژه"]))
async def cmd_add_vip(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی مجاز را ندارید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    if is_owner(chat_id, target_id) or is_admin(chat_id, target_id):
        return await _reply(message, "❌ این کاربر ادمین یا مالک است.")
    await db_add_vip(chat_id, target_id)
    mention = await _mention(target_id, bot, chat_id)
    return await _reply(message, f"⭐ {mention}\n\n›› به اعضای ویژه اضافه شد.")


@router.message(F.text == "حذف ویژه")
async def cmd_del_vip(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی مجاز را ندارید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    await db_del_vip(chat_id, target_id)
    mention = await _mention(target_id, bot, chat_id)
    return await _reply(message, f"✅ {mention}\n\n›› از اعضای ویژه حذف شد.")


# لیست ویژه و پاکسازی ویژه — هندلر اصلی پایین‌تر (cmd_list_vips_full / cmd_clear_vips_orig)


# ─── بن ──────────────────────────────────────────────────────────────────────

@router.message(F.text.in_(["بن", "کیک", "سیک", "ریمو"]))
async def cmd_ban(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی ادمین را ندارید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    own, adm, vip = get_user_status(chat_id, target_id)
    if own or adm or vip:
        rank = "مالک" if own else "ادمین" if adm else "عضو ویژه"
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"› {mention}\n\n›› در حال حاضر {rank} است!")
    try:
        await bot.ban_chat_member(chat_id, target_id)
        await db_ban_user(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"🚫 {mention}\n\n›› از گروه اخراج و بن شد.")
    except Exception as e:
        return await _reply(message, f"❌ خطا در بن کردن: {e}")


@router.message(F.text.in_(["آن بن", "ان بن", "آنبن", "انبن"]))
async def cmd_unban(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی ادمین را ندارید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    try:
        await bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
        await db_unban_user(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"✅ {mention}\n\n›› از لیست بن خارج شد.")
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")


# ─── سکوت ────────────────────────────────────────────────────────────────────

@router.message(F.text.in_(["سکوت", "میوت"]))
async def cmd_mute(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    own, adm, vip = get_user_status(chat_id, target_id)
    if own or adm or vip:
        rank = "مالک" if own else "ادمین" if adm else "عضو ویژه"
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"› {mention}\n\n›› در حال حاضر {rank} است!")
    try:
        from aiogram.types import ChatPermissions
        await bot.restrict_chat_member(
            chat_id, target_id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        cache.MUTED_USERS.setdefault(chat_id, set()).add(target_id)
        await db_mute_user(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"› {mention}\n\n›› در حالت سکوت قرار گرفت.")
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")


@router.message(F.text.regexp(r"^سکوت\s+(\d+)$"))
async def cmd_mute_timed(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not message.reply_to_message:
        return
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    own, adm, vip = get_user_status(chat_id, target_id)
    if own or adm or vip:
        rank = "مالک" if own else "ادمین" if adm else "عضو ویژه"
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"› {mention}\n\n›› در حال حاضر {rank} است!")
    m = re.search(r"\d+", message.text)
    minutes = int(m.group())
    from datetime import datetime, timezone, timedelta
    until = datetime.now(tz=timezone.utc) + timedelta(minutes=minutes)
    try:
        from aiogram.types import ChatPermissions
        await bot.restrict_chat_member(
            chat_id, target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )
        cache.MUTED_USERS.setdefault(chat_id, set()).add(target_id)
        await db_mute_user(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"› {mention}\n\n›› به مدت [ {minutes} دقیقه ] سکوت شد !")
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")


@router.message(F.text.in_(["حذف سکوت", "آن سکوت", "ان سکوت", "آنسکوت", "انسکوت"]))
async def cmd_unmute(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    try:
        from aiogram.types import ChatPermissions
        await bot.restrict_chat_member(
            chat_id, target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        )
        cache.MUTED_USERS.setdefault(chat_id, set()).discard(target_id)
        await db_unmute_user(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"› {mention}\n\n›› از حالت سکوت خارج شد.")
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")


# ─── اخطار ───────────────────────────────────────────────────────────────────

@router.message(F.text == "اخطار")
async def cmd_warn(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    own, adm, vip = get_user_status(chat_id, target_id)
    if own or adm or vip:
        rank = "مالک" if own else "ادمین" if adm else "عضو ویژه"
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"› {mention}\n\n›› در حال حاضر {rank} است!")
    warns = await db_add_warning(chat_id, target_id)
    max_w = await db_get_max_warnings(chat_id)
    mention = await _mention(target_id, bot, chat_id)
    if warns >= max_w:
        try:
            await bot.ban_chat_member(chat_id, target_id)
            return await _reply(message, f"› {mention}\n\n›› شما به دلیل دریافت حداکثر اخطار اخراج می‌شوید!")
        except Exception:
            pass
    return await _reply(message, f"› {mention}\n\n›› شما {warns} از {max_w} اخطار دریافت کردید.")


@router.message(F.text == "حذف اخطار")
async def cmd_unwarn(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "شما دسترسی مجاز را ندارید")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    await db_reset_warnings(chat_id, target_id)
    mention = await _mention(target_id, bot, chat_id)
    return await _reply(message, f"› {mention}\n\n›› تمام اخطارهای شما پاک شد.")


@router.message(F.text.regexp(r"^تعداد اخطار\s+\d+$"))
async def cmd_set_warn_count(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    m = re.search(r"\d+", message.text)
    if not m:
        return
    n = int(m.group())
    if n <= 0:
        return await _reply(message, "❗ تعداد اخطار باید بزرگتر از صفر باشد.")
    await db_set_max_warnings(chat_id, n)
    return await _reply(message, f"✅ تعداد اخطارها برای این گروه به {n} تغییر یافت.")


# ─── فیلتر کلمات ─────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^فیلتر کردن\s+(.+)$"))
async def cmd_add_filter(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    word = message.text[len("فیلتر کردن"):].strip()
    result = await db_add_word_filter(chat_id, word)
    return await _reply(message, result)


@router.message(F.text.regexp(r"^حذف فیلتر\s+(.+)$"))
async def cmd_del_filter(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    word = message.text[len("حذف فیلتر"):].strip()
    result = await db_remove_word_filter(chat_id, word)
    return await _reply(message, result)


@router.message(F.text.in_(["لیست فیلتر", "لیست کلمات"]))
async def cmd_list_filters(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    words = await db_get_word_filters(chat_id)
    if not words:
        return await _reply(message, "ℹ️ لیست فیلتر این گروه خالی است.")
    txt = "🚫 لیست کلمات ممنوعه این گروه:\n\n"
    txt += "\n".join(f"{i+1}. {w}" for i, w in enumerate(words))
    return await _reply(message, txt)


# ─── یادگیری ─────────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^(یاد بگیر|یادبگیر|یادگیری)\s*-\s*.+\s*-\s*.+$"))
async def cmd_learn(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    parts = [p.strip() for p in message.text.split("-")]
    if len(parts) != 3:
        return
    _, trigger, response = parts
    if not trigger or not response:
        return
    await db_save_learned_response(chat_id, trigger, response, user_id)
    return await _reply(message,
        f"✅ یاد گرفتم وقتی یکی گفت:\n«{trigger}»\nجواب بدم:\n💬 {response}")


@router.message(F.text.regexp(r"^(حذف یادگیری|حذف یاد گیری|حذف یادبگیر|حذف یاد بگیر)\s*-\s*.+$"))
async def cmd_forget(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    parts = [p.strip() for p in message.text.split("-")]
    if len(parts) != 2:
        return
    _, trigger = parts
    deleted = await db_delete_learned_response(chat_id, trigger)
    if deleted:
        return await _reply(message, f"🗑 یادگیری حذف شد\nدیگه وقتی بگن «{trigger}» پاسخی نمی‌دم.")
    return await _reply(message, f"❌ اینو یاد نگرفتم که بخوای حذفش کنی🤖:\n«{trigger}»")


@router.message(F.text.in_(["لیست یادگیری", "یادگیری ها", "لیست یادگیری ها", "لیست یادگیری‌ها"]))
async def cmd_list_learns(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    learns = cache.LEARNED_RESPONSES.get(chat_id) or await db_get_learned_responses(chat_id)
    if not learns:
        return await _reply(message, "📭 هنوز چیزی یاد نگرفتم!")
    result = "📚 لیست یادگیری‌های این گروه:\n\n"
    for i, (trigger, resp) in enumerate(learns.items(), 1):
        result += f"{i}. 🟦 وقتی بگن: «{trigger}»\n   🟩 جواب می‌دم: {resp}\n\n"
    return await _reply(message, result)


# ─── سخنگو ───────────────────────────────────────────────────────────────────

@router.message(F.text == "سخنگو")
async def cmd_speaker_status(message: Message):
    chat_id = message.chat.id
    state = "🔊 روشن" if chat_id in cache.SPEAKER_ON else "🔇 خاموش"
    return await _reply(message, f"وضعیت سخنگو: {state}\n\nبرای تغییر:\n  سخنگو روشن\n  سخنگو خاموش")

@router.message(F.text == "سخنگو روشن")
async def cmd_speaker_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.SPEAKER_ON.add(chat_id)
    await db_enable_speaker(chat_id)
    return await _reply(message, "🔊 سخنگو از این لحظه فعال شد ✔️")

@router.message(F.text == "سخنگو خاموش")
async def cmd_speaker_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.SPEAKER_ON.discard(chat_id)
    await db_disable_speaker(chat_id)
    return await _reply(message, "🔇 سخنگو غیرفعال شد ❌")


# ─── لقب/مشخصات ──────────────────────────────────────────────────────────────

@router.message(F.text.in_(["حذف لقب"]))
async def cmd_del_alias_self(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    await db_set_alias(chat_id, user_id, "")
    return await _reply(message, "✔ لقب شما حذف شد.")


@router.message(F.text.regexp(r"^تنظیم\s+(نام|لقب|اصلی|اصل|فامیلی|فامیل)\s+.+$"))
async def cmd_set_profile(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return
    _, key, value = parts
    if key in ("نام", "لقب", "اصلی", "اصل", "فامیلی", "فامیل"):
        target_id = user_id
        if message.reply_to_message and message.reply_to_message.from_user:
            if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
                return await _reply(message, "❌ شما اجازه تغییر اطلاعات بقیه را ندارید.")
            target_id = message.reply_to_message.from_user.id
        if len(value) > 30:
            return await _reply(message, f"❗ کاربر عزیز، طول {key} نمی‌تواند بیش از 30 حرف باشد.")
        if key == "لقب":
            await db_set_alias(chat_id, target_id, value)
            name = await _mention(target_id, bot, chat_id)
            return await _reply(message, f"• لقب {name}\n\n» به [ {value} ] تنظیم شد !")
        return await _reply(message, "✔️ تنظیم شد.")


# ─── لقب و نام کاربر ─────────────────────────────────────────────────────────

@router.message(F.text.in_(["لقب من", "لقبم"]))
async def cmd_my_alias(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    val = await db_get_alias(chat_id, user_id)
    return await _reply(message, val or "❗لقبی ثبت نشده.")


@router.message(F.text.in_(["لقبش", "لقب"]) )
async def cmd_target_alias(message: Message, bot: Bot):
    if not message.reply_to_message:
        return
    chat_id = message.chat.id
    target_id = message.reply_to_message.from_user.id
    val = await db_get_alias(chat_id, target_id)
    mention = await _mention(target_id, bot, chat_id)
    if not val:
        return await _reply(message, f"• این {mention} لقبی ندارد !")
    return await _reply(message, f"• لقب {mention}\n\n‏» [ {val} ] می باشد")


# ─── آمار ────────────────────────────────────────────────────────────────────

@router.message(F.text.in_(["امار", "آمار", "آمار گروه", "امار گروه", "امارم", "آمارم"]))
async def cmd_stats(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    member = await db_get_member(chat_id, user_id)
    top = await db_get_top_users(chat_id, 5)

    now = jdatetime.datetime.now()
    days = {
        'Saturday': 'شنبه', 'Sunday': 'یکشنبه', 'Monday': 'دوشنبه',
        'Tuesday': 'سه‌شنبه', 'Wednesday': 'چهارشنبه',
        'Thursday': 'پنج‌شنبه', 'Friday': 'جمعه'
    }
    j_months = ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور",
                 "مهر","آبان","آذر","دی","بهمن","اسفند"]
    day_name = days.get(now.strftime('%A'), "")
    month_name = j_months[now.month - 1]
    shamsi_date = f"{day_name}: {now.day} {month_name} {now.year}"
    shamsi_time = now.strftime("%H:%M")

    medals = {1: "🥇", 2: "🥈", 3: "🥉", 4: "🔥", 5: "✨"}
    top_lines = []
    for i, u in enumerate(top, 1):
        uid = u["telegram_user_id"]
        m_mention = await _mention(uid, bot, chat_id)
        top_lines.append(f"{medals.get(i, f'{i}.')} {m_mention} | {u['message_count']} پیام")

    role = "مالک" if is_owner(chat_id, user_id) else "ادمین" if is_admin(chat_id, user_id) else "عضو ویژه" if is_vip(chat_id, user_id) else "عضو"
    level = member.level if member else 1
    xp = member.xp_total if member else 0
    warns = member.warnings if member else 0
    msg_count = member.message_count if member else 0

    text = (
        f"📊 آمار فعالیت گروه\n\n"
        f"📅 تاریخ: {shamsi_date}\n"
        f"🕒 ساعت: {shamsi_time}\n\n"
        f"🎖️ نقش: {role}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"💠 آمار شخصی شما\n"
        f"🔺 سطح: {level} | 💎 XP: {xp}\n"
        f"📈 مجموع پیام‌ها: {msg_count}\n"
        f"⚠️ تعداد اخطار: {warns}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🏆 فعال‌ترین‌های گروه\n"
        f"{chr(10).join(top_lines) if top_lines else 'هنوز آماری ثبت نشده'}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🆔 شناسه کاربری: <code>{user_id}</code>"
    )
    return await _reply(message, text)


@router.message(F.text.in_(["امار کاربران", "تاپ کل"]))
async def cmd_top_users(message: Message, bot: Bot):
    chat_id = message.chat.id
    top = await db_get_top_users(chat_id, 50)
    if not top:
        return await _reply(message, "📭 هنوز آماری ثبت نشده است.")
    medals = {1: "🥇", 2: "🥈", 3: "🥉", 4: "🏅", 5: "🎖️"}
    lines = []
    for i, u in enumerate(top, 1):
        uid = u["telegram_user_id"]
        mention = await _mention(uid, bot, chat_id)
        if i <= 5:
            lines.append(f"{medals.get(i, '')} {mention} ─ {u['message_count']} پیام")
        else:
            lines.append(f"`{i:2d}.` {mention} ─ {u['message_count']} پیام")
    text = "🏆 ۵۰ کاربر برتر گروه (همه‌ی روزها)\n\n" + "\n".join(lines)
    return await _reply(message, text)


# ─── تگ همگانی ───────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^تگ(\s+.*)?$"))
async def cmd_tag(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط ادمین‌ها می‌توانند تگ همگانی بزنند.")
    custom_text = message.text[3:].strip()
    top = await db_get_top_users(chat_id, 50)
    if not top:
        return await _reply(message, "📭 هنوز عضوی ثبت نشده.")
    mentions = " ".join(
        f'<a href="tg://user?id={u["telegram_user_id"]}">‏</a>'
        for u in top
    )
    header = custom_text or "📢 اطلاعیه"
    await safe_send(bot, chat_id, f"{header}\n{mentions}")


# ─── لینک ────────────────────────────────────────────────────────────────────

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as IKB

def _link_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="━━ 🔗 لینک گروه ━━", callback_data="lnk:noop")],
        [
            IKB(text="🔗 لینک عادی",           callback_data="lnk:invite"),
            IKB(text="🔒 یک‌بار‌مصرف",         callback_data="lnk:once"),
        ],
        [
            IKB(text="⏰ موقت ۲۴ ساعته",       callback_data="lnk:h24"),
            IKB(text="📅 موقت ۷ روزه",         callback_data="lnk:d7"),
        ],
        [
            IKB(text="✅ با تایید ادمین",       callback_data="lnk:approval"),
            IKB(text="👥 محدود ۱۰ نفر",        callback_data="lnk:limit10"),
        ],
        [IKB(text="━━ 👤 لینک کاربر ━━", callback_data="lnk:noop")],
        [
            IKB(text="👤 پروفایل من",          callback_data="lnk:me"),
            IKB(text="🤖 لینک ربات",           callback_data="lnk:bot"),
        ],
        [IKB(text="❌ بستن", callback_data="lnk:close")],
    ])

@router.message(F.text == "لینک")
async def cmd_link_panel(message: Message):
    await safe_send(
        message.bot, message.chat.id,
        "🔗 <b>ساخت لینک</b>\n\nنوع لینک مورد نظر رو انتخاب کن:",
        reply_markup=_link_panel(),
        reply_to=message.message_id,
    )


# ─── راهنما ──────────────────────────────────────────────────────────────────

_PANEL_TRIGGERS = {"راهنما", "پنل", "داشبورد", "منو", "panel", "menu", "dashboard"}

@router.message(F.text.func(lambda t: t is not None and t.strip() in _PANEL_TRIGGERS))
async def cmd_help(message: Message):
    await safe_send(message.bot, message.chat.id, PAGE_MAIN,
                    reply_markup=panel_main(), reply_to=message.message_id)


# ─── ساعت ────────────────────────────────────────────────────────────────────

@router.message(F.text.in_(["ساعت", "تقویم", "تاریخ"]))
async def cmd_time(message: Message):
    now = jdatetime.datetime.now()
    j_months = ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور",
                 "مهر","آبان","آذر","دی","بهمن","اسفند"]
    days = {
        'Saturday': 'شنبه', 'Sunday': 'یکشنبه', 'Monday': 'دوشنبه',
        'Tuesday': 'سه‌شنبه', 'Wednesday': 'چهارشنبه',
        'Thursday': 'پنج‌شنبه', 'Friday': 'جمعه'
    }
    day_name = days.get(now.strftime('%A'), "")
    month_name = j_months[now.month - 1]
    text = (
        f"🕐 ساعت: {now.strftime('%H:%M:%S')}\n"
        f"📅 تاریخ: {day_name} {now.day} {month_name} {now.year}"
    )
    return await _reply(message, text)


# ─── ماشین حساب ──────────────────────────────────────────────────────────────

_MATH_RE = re.compile(r"^[\d\s\+\-\*\/\(\)\.\،\,×÷]+$")

@router.message(F.text.func(lambda t: bool(t and _MATH_RE.match(t) and any(c in t for c in "+-*/×÷"))))
async def cmd_calc_direct(message: Message):
    result = safe_calc(message.text.strip())
    if result is None:
        return
    return await _reply(message, f"🔢 {message.text.strip()} = {result}")

@router.message(F.text.regexp(r"^حساب\s+.+$"))
async def cmd_calc(message: Message):
    expr = message.text[6:].strip()
    result = safe_calc(expr)
    if result is None:
        return await _reply(message, "❌ عبارت ریاضی معتبر نیست.")
    return await _reply(message, f"🔢 {expr} = {result}")


# ─── وضعیت کاربر ─────────────────────────────────────────────────────────────

@router.message(F.text.in_(["role", "وضعیت", "نقش"]))
async def cmd_role(message: Message, bot: Bot):
    chat_id = message.chat.id
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        target_id = message.from_user.id
    own, adm, vip = get_user_status(chat_id, target_id)
    role = "مالک 👑" if own else "ادمین 🛡" if adm else "عضو ویژه ⭐" if vip else "عضو 👤"
    mention = await _mention(target_id, bot, chat_id)
    return await _reply(message, f"› {mention}\n\n›› نقش: {role}")


# ─── بازی ها ─────────────────────────────────────────────────────────────────

@router.message(F.text.in_(["بازی ها", "بازی‌ها"]))
async def cmd_games_list(message: Message):
    return await _reply(message, """🎮 بازی‌های موجود:

【🎲 تاس】
【🏀 بسکتبال】
【🥅 پنالتی】
【🎳 بولینگ】
【✂️ سنگ ‌کاغذ قیچی】
【🎯 دارت】
【🍀 شانس】
""")


@router.message(F.text.in_(["سرگرمی", "سرگرمی ها"]))
async def cmd_fun_list(message: Message):
    return await _reply(message, """🎮 منوی جامع سرگرمی:

【🤣 جوک】
【📜 فال】
【💡 دانستنی】
【💎 سخن】
【🤔 معما】
【⚖️ دو راهی】
【🎯 چالش】
【💕 شخصیت】
【🍀 شانس】

برای مشاهده لیست بازی‌ها، دستور «بازی ها» را ارسال کنید.
""")


# ─── شناسه کاربری ────────────────────────────────────────────────────────────

@router.message(F.text == "گوید")
async def cmd_id(message: Message):
    return await _reply(message, f"• شناسه کاربری : <code>{message.from_user.id}</code>")


# ─── نصب دستورات متنی اضافه ─────────────────────────────────────────────────

@router.message(F.text.in_(["تاسینو", "ربات", "بات"]))
async def cmd_hi_bot(message: Message):
    import random
    from bot.constants import bot_responses
    answer = random.choice(bot_responses)
    return await _reply(message, answer)


# ─── تاس متوالی کامل (با status) ────────────────────────────────────────────

@router.message(F.text.in_(["تاس متوالی فعال", "تاس متوالی روشن", "فعال کردن تاس متوالی"]))
async def cmd_dice_option_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if chat_id not in cache.DICE_OPTION:
        return await _reply(message, "• تاس متوالی از قبل روشن است!\n• با دستور «تاس متوالی خاموش» می‌توانید آن را خاموش کنید.")
    await db_enable_dice_option(chat_id)
    return await _reply(message, "• تاس متوالی با موفقیت فعال شد.\n• برای خاموش‌کردن از دستور «تاس متوالی خاموش» استفاده کنید.")


@router.message(F.text.in_(["تاس متوالی خاموش", "خاموش تاس متوالی", "غیرفعال کردن تاس متوالی"]))
async def cmd_dice_option_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if chat_id in cache.DICE_OPTION:
        return await _reply(message, "• تاس متوالی از قبل خاموش است!\n• دو عدد پشت هم نمیاد!")
    await db_disable_dice_option(chat_id)
    return await _reply(message, "• تاس متوالی با موفقیت خاموش شد.\n• دیگه دو عدد پشت هم نمیاد!")


# ─── قفل ها با نمایش اخطار ────────────────────────────────────────────────────

@router.message(F.text.in_(["قفل ها", "وضعیت", "محدودیت"]))
async def cmd_lock_status_full(message: Message):
    chat_id = message.chat.id
    locks = cache.GROUP_LOCKS.get(chat_id) or await db_get_locks(chat_id)
    max_w = await db_get_max_warnings(chat_id)

    response = ">🛠 وضعیت قفل‌های گروه\n\n"
    active, inactive = [], []
    for key, name in LOCK_NAMES.items():
        if locks.get(key, False):
            active.append(f"🔒 {name}  ‹اخطار: {max_w}›")
        else:
            inactive.append(f"🔓 {name}  ‹اخطار: {max_w}›")

    if active:
        response += "✅ قفل‌های روشن:\n • " + "\n • ".join(active) + "\n\n"
    if inactive:
        response += ">❌ قفل‌های خاموش:\n • " + "\n • ".join(inactive)

    response += "\n— — — — — — — — —\n"
    response += "📌 تغییر وضعیت قفل:\nقفل [نام قفل]\nبازکردن [نام قفل]\n\n"
    response += "📌 تنظیم اخطار هر قفل:\nاخطار [نام قفل] [عدد]\nمثال: اخطار لینک 10"
    return await _reply(message, response)


# ─── اخطار قفل (اخطار لینک 10) ─────────────────────────────────────────────

@router.message(F.text.regexp(r"^اخطار\s+\S+\s+\d+$"))
async def cmd_warn_lock(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    parts = message.text.strip().split()
    if len(parts) == 3 and parts[1] in LOCK_MAP and parts[2].isdigit():
        lock_key = LOCK_MAP[parts[1]]
        max_val = int(parts[2])
        if max_val < 1:
            return await _reply(message, "❌ حداقل مقدار اخطار ۱ است.")
        await db_set_max_warnings(chat_id, max_val)
        return await _reply(message, f"✅ حداکثر اخطار قفل «{parts[1]}» روی {max_val} تنظیم شد.")
    return await _reply(message, "❌ فرمت نادرست.\n📌 مثال: اخطار لینک 10\n\nقفل‌های موجود:\n" + "  ".join(LOCK_MAP.keys()))


# ─── اخطار کاربر (نمایش وضعیت اخطار) ────────────────────────────────────────

@router.message(F.text == "اخطار کاربر")
async def cmd_warn_status(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "شما دسترسی مجاز را ندارید")
    if not message.reply_to_message:
        return await _reply(message, "⚠️ لطفاً روی پیام کاربر مورد نظر ریپلای کنید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    warns = await db_get_warnings(chat_id, target_id)
    max_w = await db_get_max_warnings(chat_id)
    mention = await _mention(target_id, bot, chat_id)
    if not warns:
        return await _reply(message, f"› {mention}\n\n›› اخطاری ثبت نشده است.")
    return await _reply(message, f"› {mention}\n\n›› وضعیت اخطارها:\n• مجموع اخطار: {warns}/{max_w}")


# ─── لیست ادمین با فرمت کامل ─────────────────────────────────────────────────

@router.message(F.text.in_(["لیست ادمین‌ها", "لیست ادمین", "لیست مدیران", "لیست مدیران گروه"]))
async def cmd_list_admins_full(message: Message, bot: Bot):
    chat_id = message.chat.id
    if not is_admin(chat_id, message.from_user.id) and not is_owner(chat_id, message.from_user.id):
        return
    admins = await db_get_admins(chat_id)
    owner_id = cache.OWNER_CACHE.get(chat_id)

    if not owner_id and not admins:
        return await _reply(message, "🛡️ لیست مدیران گروه\n━━━━━━━━━━━━━━━━\n\n⚠️ هیچ مدیری برای این گروه ثبت نشده.\n━━━━━━━━━━━━━━━━")

    text = "🛡️ لیست مدیران گروه\n━━━━━━━━━━━━━━━━\n\n"
    if owner_id:
        om = await _mention(owner_id, bot, chat_id)
        text += f"👑 مالک گروه\n• {om}\n\n"
    if admins:
        text += f"👥 مدیران ({len(admins)})\n──────────────\n"
        for i, aid in enumerate(admins, 1):
            m = await _mention(aid, bot, chat_id)
            text += f"{i:02d} • {m}\n"
    text += "\n━━━━━━━━━━━━━━━━"
    return await _reply(message, text)


# ─── لیست ویژه با فرمت کامل ──────────────────────────────────────────────────

@router.message(F.text.in_(["لیست کاربران ویژه"]))
async def cmd_list_vips_full(message: Message, bot: Bot):
    chat_id = message.chat.id
    if not is_admin(chat_id, message.from_user.id) and not is_owner(chat_id, message.from_user.id):
        return
    vips = await db_get_vips(chat_id)
    response_text = "🛡 لیست کاربران ویژه\n\n──────────────\n\n"
    if not vips:
        response_text += "هنوز کسی به لیست ویژه اضافه نشده ✨"
        return await _reply(message, response_text)
    for i, vid in enumerate(vips, 1):
        m = await _mention(vid, bot, chat_id)
        response_text += f"{i} • {m}\n"
    return await _reply(message, response_text)


# ─── پاکسازی با فرمت اصلی ────────────────────────────────────────────────────

@router.message(F.text.in_(["پاکسازی لیست ویژه", "پاکسازی ویژه"]))
async def cmd_clear_vips_orig(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    vips = await db_get_vips(chat_id)
    count = len(vips)
    await db_clear_vips(chat_id)
    if count > 0:
        return await _reply(message, f"• لیست کاربران ویژه پاکسازی شد!\n\n›› تعداد کاربران : ( {count}")
    return await _reply(message, "• لیست کاربران ویژه خالی است!")


# ─── لیست بن ─────────────────────────────────────────────────────────────────

@sync_to_async
def _get_banned_from_db(chat_id: int):
    from account.models import TelegramGroupMember
    return list(TelegramGroupMember.objects.filter(telegram_chat_id=chat_id, role="banned").values_list("telegram_user_id", flat=True)[:25])

@sync_to_async
def _count_banned(chat_id: int):
    from account.models import TelegramGroupMember
    return TelegramGroupMember.objects.filter(telegram_chat_id=chat_id, role="banned").count()

@router.message(F.text.in_(["لیست بن", "banned list"]))
async def cmd_list_ban(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی ادمین برای این دستور را ندارید.")
    total = await _count_banned(chat_id)
    if total == 0:
        return await _reply(message, "📭 لیست بن خالی است.\n━━━━━━━━━━━━━━━━━━━━\n\nهیچ کاربر مسدودی در گروه وجود ندارد.")
    banned_ids = await _get_banned_from_db(chat_id)
    text = f"🚫 لیست کاربران مسدود شده\n━━━━━━━━━━━━━━━━━━━━\n🔢 تعداد کل: {total} نفر\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for idx, uid in enumerate(banned_ids, 1):
        m = await _mention(uid, bot, chat_id)
        text += f"{idx}. {m}\n"
    if total > 25:
        text += f"\n━━━━━━━━━━━━━━━━━━━━\n📌 و {total - 25} نفر دیگر ...\n"
    text += f"\n💡 راهنما:\n   • رفع بن: روی پیام کاربر ریپلای کنید آنبن"
    return await _reply(message, text)


@router.message(F.text.in_(["پاکسازی لیست بن", "clear banned list"]))
async def cmd_clear_ban(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی ادمین برای این دستور را ندارید.")
    total = await _count_banned(chat_id)
    if total == 0:
        return await _reply(message, "📭 لیست بن خالی است.\n━━━━━━━━━━━━━━━━━━━━\n\nهیچ کاربر مسدودی برای پاکسازی وجود ندارد.")
    banned_ids = await _get_banned_from_db(chat_id)
    await _reply(message, f"🔄 در حال پاکسازی لیست بن...\n━━━━━━━━━━━━━━━━━━━━\n\n🔢 تعداد: {total} نفر\n\n⏳ لطفاً صبر کنید...")
    success = fail = 0
    for uid in banned_ids:
        try:
            await bot.unban_chat_member(chat_id, uid)
            success += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.5)
    text = (f"✅ پاکسازی لیست بن انجام شد.\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔢 آمار نهایی:\n   • موفق: {success} نفر\n   • ناموفق: {fail} نفر\n\n✅ لیست بن گروه خالی شد.")
    return await _reply(message, text)


# ─── لیست سکوت ───────────────────────────────────────────────────────────────

@router.message(F.text == "لیست سکوت")
async def cmd_list_mute(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    muted_ids = list(cache.MUTED_USERS.get(chat_id, set()))
    if not muted_ids:
        return await _reply(message, "🔇 لیست سکوت خالی است.")
    txt = "🔇 لیست کاربران ساکت شده\n────────────\n"
    for i, uid in enumerate(muted_ids, 1):
        m = await _mention(uid, bot, chat_id)
        txt += f"{i}. {m}\n"
    return await _reply(message, txt)


@router.message(F.text == "پاکسازی لیست سکوت")
async def cmd_clear_mute(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    muted = cache.MUTED_USERS.get(chat_id, set())
    count = len(muted)
    for uid in list(muted):
        try:
            await bot.restrict_chat_member(chat_id, uid, permissions=ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_other_messages=True, can_add_web_page_previews=True
            ))
        except Exception:
            pass
    cache.MUTED_USERS[chat_id] = set()
    if count == 0:
        return await _reply(message, "• لیست کاربران سکوت شده خالی است!")
    return await _reply(message, f"• لیست کاربران سکوت شده پاکسازی شد!\n\n›› تعداد کاربران : ( {count} ")


# ─── مشخصات کاربر (نام/اصلی/فامیلی) ─────────────────────────────────────────

@router.message(F.text.in_(["نام من", "نامم"]))
async def cmd_my_name(message: Message):
    return await _reply(message, "❗نامی ثبت نشده.")


@router.message(F.text.in_(["اصل من", "اصلیم", "اصلم"]))
async def cmd_my_origin(message: Message):
    return await _reply(message, "❗اصلی ثبت نشده.")


@router.message(F.text.in_(["فامیل من", "فامیلی من", "فامیلیم", "فامیلم"]))
async def cmd_my_family(message: Message):
    return await _reply(message, "❗فامیلی ثبت نشده.")


@router.message(F.text == "حذف نام")
async def cmd_del_name(message: Message):
    return await _reply(message, "✔ نام شما حذف شد.")


@router.message(F.text.in_(["حذف اصل", "حذف اصلی"]))
async def cmd_del_origin(message: Message):
    return await _reply(message, "✔ اصل شما حذف شد.")


@router.message(F.text.in_(["حذف فامیل", "حذف فامیلی"]))
async def cmd_del_family(message: Message):
    return await _reply(message, "✔ فامیلی شما حذف شد.")


@router.message(F.text == "تنظیم مشخصات غیرفعال")
async def cmd_profile_lock(message: Message):
    return await _reply(message, "🔒 مشخصات شما قفل شد. دیگران نمی‌توانند آنها را تغییر دهند.")


@router.message(F.text == "تنظیم مشخصات فعال")
async def cmd_profile_unlock(message: Message):
    return await _reply(message, "🔒 مشخصات شما باز شد. دیگران می‌توانند آنها را تغییر دهند.")


@router.message(F.text.in_(["نامش", "فامیلیش", "فامیلش", "اصلیش", "اصلش"]))
async def cmd_target_profile(message: Message, bot: Bot):
    if not message.reply_to_message:
        return
    target_id = message.reply_to_message.from_user.id
    mention = await _mention(target_id, bot, message.chat.id)
    field_map = {
        "نامش": "نامی", "فامیلیش": "فامیلی", "فامیلش": "فامیلی",
        "اصلیش": "اصلی", "اصلش": "اصلی"
    }
    word = field_map.get(message.text, "اطلاعاتی")
    return await _reply(message, f"❗{mention} {word} ثبت نشده.")


# ─── کیف پول و مالی ──────────────────────────────────────────────────────────

@sync_to_async
def _get_wallet(chat_id, user_id):
    from account.models import TelegramGroupMember
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"role": "member"}
    )
    return m

@sync_to_async
def _increase_wallet(chat_id, user_id, amount):
    from account.models import TelegramGroupMember
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"role": "member"}
    )
    if not hasattr(m, 'balance'):
        return 0
    m.balance = (m.balance or 0) + amount
    m.save(update_fields=["balance"])
    return m.balance

@sync_to_async
def _decrease_wallet(chat_id, user_id, amount):
    from account.models import TelegramGroupMember
    m, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_user_id=user_id,
        defaults={"role": "member"}
    )
    if not hasattr(m, 'balance'):
        return 0
    m.balance = (m.balance or 0) - amount
    m.save(update_fields=["balance"])
    return m.balance

@sync_to_async
def _get_balance(chat_id, user_id):
    from account.models import TelegramGroupMember
    try:
        m = TelegramGroupMember.objects.get(telegram_chat_id=chat_id, telegram_user_id=user_id)
        return getattr(m, 'balance', 0) or 0
    except Exception:
        return 0

@sync_to_async
def _clear_wallet(chat_id, user_id):
    from account.models import TelegramGroupMember
    try:
        m = TelegramGroupMember.objects.get(telegram_chat_id=chat_id, telegram_user_id=user_id)
        old = getattr(m, 'balance', 0) or 0
        if hasattr(m, 'balance'):
            m.balance = 0
            m.save(update_fields=["balance"])
        return old
    except Exception:
        return 0

@sync_to_async
def _get_fee(chat_id):
    from account.models import TelegramGroup
    try:
        g = TelegramGroup.objects.get(telegram_chat_id=chat_id)
        return getattr(g, 'fee_percent', 0) or 0
    except Exception:
        return 0

@sync_to_async
def _set_fee(chat_id, fee):
    from account.models import TelegramGroup
    g, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    g.fee_percent = fee
    g.save(update_fields=["fee_percent"])


@router.message(F.text.regexp(r"^(افزایش موجودی|افزایش)\s+\d+"))
async def cmd_increase_wallet(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not message.reply_to_message:
        return await _reply(message, "⚠️ لطفاً روی پیام کاربر مورد نظر ریپلای کنید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    parts = message.text.split()
    amount_text = parts[-1]
    try:
        amount = int(amount_text)
    except ValueError:
        return await _reply(message, "❗ مقدار افزایش عدد معتبر نیست.")
    new_balance = await _increase_wallet(chat_id, target_id, amount)
    user_tag = await _mention(target_id, bot, chat_id)
    admin_tag = await _mention(user_id, bot, chat_id)
    text = (
        "✅ عملیات افزایش موجودی با موفقیت انجام شد\n\n"
        f"👤 کاربر: {user_tag}\n"
        f"🛡 مدیر اجراکننده: {admin_tag}\n\n"
        f"💰 مبلغ افزایش: {amount:,} واحد اعتباری\n"
        f"📊 موجودی فعلی: {new_balance:,} واحد اعتباری"
    )
    return await _reply(message, text)


@router.message(F.text.regexp(r"^(کاهش موجودی|کاهش)\s+\d+"))
async def cmd_decrease_wallet(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not message.reply_to_message:
        return await _reply(message, "⚠️ لطفاً روی پیام کاربر مورد نظر ریپلای کنید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    parts = message.text.split()
    amount_text = parts[-1]
    try:
        amount = int(amount_text)
    except ValueError:
        return await _reply(message, "❗ مقدار کاهش عدد معتبر نیست.")
    new_balance = await _decrease_wallet(chat_id, target_id, amount)
    user_tag = await _mention(target_id, bot, chat_id)
    admin_tag = await _mention(user_id, bot, chat_id)
    text = (
        "⚠️ عملیات کاهش موجودی انجام شد\n\n"
        f"👤 کاربر: {user_tag}\n"
        f"🛡 مدیر اجراکننده: {admin_tag}\n\n"
        f"💳 مبلغ کسر شده: {amount:,} واحد اعتباری\n"
        f"📊 موجودی فعلی: {new_balance:,} واحد اعتباری"
    )
    return await _reply(message, text)


@router.message(F.text.in_(["موجودی", "موجودی من"]))
async def cmd_balance(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        target_id = user_id
    balance = await _get_balance(chat_id, target_id)
    user_tag = await _mention(target_id, bot, chat_id)
    now = jdatetime.datetime.now()
    j_time_str = now.strftime("%Y/%m/%d - %H:%M")
    if balance < 0:
        balance_text = f"🔻 {abs(balance):,} واحد بدهکار"
    else:
        balance_text = f"{balance:,} واحد اعتباری"
    text = (
        "💳 وضعیت موجودی حساب\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 کاربر: {user_tag}\n"
        f"📊 موجودی فعلی: {balance_text}\n"
        f"🕒 زمان استعلام: {j_time_str}\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    return await _reply(message, text)


@router.message(F.text.in_(["تسویه", "تسویه حساب"]))
async def cmd_settle(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not message.reply_to_message:
        return await _reply(message, "⚠️ لطفاً روی پیام کاربر مورد نظر ریپلای کنید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    cleared = await _clear_wallet(chat_id, target_id)
    user_tag = await _mention(target_id, bot, chat_id)
    admin_tag = await _mention(user_id, bot, chat_id)
    j_date = jdatetime.datetime.now()
    j_time_str = j_date.strftime("%Y/%m/%d - %H:%M")
    text = (
        "🧾 عملیات تسویه حساب با موفقیت انجام شد\n\n"
        f"👤 کاربر: {user_tag}\n"
        f"🛡 مدیر اجراکننده: {admin_tag}\n\n"
        f"💸 مبلغ تسویه شده: {cleared:,} واحد اعتباری\n"
        f"📊 موجودی فعلی: 0 واحد اعتباری\n"
        "✔ حساب کاربر به طور کامل تسویه شد."
    )
    return await _reply(message, text)


@router.message(F.text.in_(["حساب ها", "حساب‌ها"]))
async def cmd_accounts(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    members = await db_get_all_members_balance(chat_id)
    if not members:
        return await _reply(message, "📊 هیچ عضوی ثبت نشده.")
    lines = []
    for i, m in enumerate(members[:30], 1):
        name = m["alias"] or str(m["telegram_user_id"])
        balance = m["point"] or 0
        lines.append(f"  {i}. {name}: {balance:,} تومان")
    text = "💰 موجودی اعضا:\n━━━━━━━━━━━━━━━━\n" + "\n".join(lines)
    return await _reply(message, text)


@router.message(F.text.regexp(r"^گزارش(\s+\d+)?$"))
async def cmd_report(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    return await _reply(message, "📭 سیستم گزارش مالی در این نسخه فعال نیست.")


@router.message(F.text.regexp(r"^(کارمزد|حق واسطه|نرخ کارمزد)(\s+\d+)?$"))
async def cmd_fee(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    fee = await _get_fee(chat_id)
    parts = message.text.split()
    if len(parts) == 1:
        text = (
            f"💹 حق واسطه این گروه\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 نرخ فعلی: {fee}%\n\n"
            f"📌 تغییر نرخ:\n   کارمزد 10  یا  حق واسطه 10\n\n"
            f"✅ محدوده مجاز: ۰ تا ۵۰ درصد"
        )
        return await _reply(message, text)
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی ادمین برای این دستور را ندارید.")
    try:
        new_fee = int(parts[-1])
    except ValueError:
        return await _reply(message, "❌ مقدار باید یک عدد باشد.\nمثال: کارمزد 10")
    if not 0 <= new_fee <= 50:
        return await _reply(message, "❌ نرخ حق واسطه باید بین ۰ تا ۵۰ درصد باشد.")
    await _set_fee(chat_id, new_fee)
    admin_tag = await _mention(user_id, bot, chat_id)
    text = (
        f"✅ حق واسطه گروه با موفقیت تغییر کرد\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛡 مدیر: {admin_tag}\n"
        f"💹 نرخ جدید: {new_fee}%\n\n"
    )
    if new_fee == 0:
        text += "🔓 حق واسطه حذف شد. برنده کل جایزه را بدون کسر دریافت می‌کند.\n"
    else:
        text += f"📊 نحوه محاسبه:\n   • هر بازیکن علاوه بر شرط، {new_fee}% اضافه پرداخت می‌کند.\n\n"
    text += f"🔔 از این به بعد مسابقات تاس با حق واسطه {new_fee}% برگزار می‌شود."
    return await _reply(message, text)


# ─── شماره کارت ──────────────────────────────────────────────────────────────

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_CARD_PREFIXES = ("افزودن کارت", "تنظیم کارت", "افزودن شماره کارت", "تنظیم شماره کارت")


@router.message(F.text.in_(["شماره کارت", "کارت"]))
async def cmd_card_self(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    own, adm, _ = get_user_status(chat_id, user_id)
    role = "owner" if own else "admin" if adm else "member"
    text = await db_get_card(chat_id, user_id, role)
    return await safe_send(bot, chat_id, text, reply_to=message.message_id)


@router.message(F.text.in_(["شماره کارت مالک", "کارت مالک", "cart", "Cart", "CART"]))
async def cmd_card_owner(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = await db_get_card(chat_id, user_id, "owner")
    return await safe_send(bot, chat_id, text, reply_to=message.message_id)


@router.message(F.text.func(lambda t: t and any(t.startswith(p) for p in _CARD_PREFIXES)))
async def cmd_add_card(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    # برش prefix
    body = text
    for p in _CARD_PREFIXES:
        if body.startswith(p):
            body = body[len(p):].strip()
            break

    # تبدیل ارقام فارسی
    body = body.translate(_PERSIAN_DIGITS)

    # استخراج ارقام کارت
    digits_only = re.sub(r"\D", "", body)
    if len(digits_only) < 16:
        return await _reply(message,
            "❌ فرمت صحیح:\n"
            "<code>افزودن کارت [شماره ۱۶ رقمی] [نام]</code>\n\n"
            "مثال:\n<code>افزودن کارت 6219861982073383 معین</code>")
    card_number = digits_only[:16]

    # استخراج نام (هر چیزی بعد از شماره کارت)
    card_pattern = r"\d[\d\s\-]{14,}\d"
    name_part = re.sub(card_pattern, "", body, count=1).strip()
    # حذف فاصله‌های اضافی
    name_part = re.sub(r"\s+", " ", name_part).strip()

    if len(name_part) < 2:
        return await _reply(message,
            "❌ نام دارنده کارت را هم بنویسید.\n\n"
            "مثال:\n<code>افزودن کارت 6219861982073383 معین</code>")
    if len(name_part) > 30:
        return await _reply(message, "❌ نام بیش از حد طولانی است (حداکثر ۳۰ کاراکتر).")

    own, adm, _ = get_user_status(chat_id, user_id)
    result = await db_update_card(chat_id, user_id, card_number, name_part, own or adm)
    return await safe_send(bot, chat_id, result, reply_to=message.message_id)


@router.message(F.text.func(lambda t: t and (t.startswith("حذف کارت") or t.startswith("حذف شماره کارت"))))
async def cmd_del_card(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    body = text
    for p in ("حذف شماره کارت", "حذف کارت"):
        if body.startswith(p):
            body = body[len(p):].strip()
            break

    body = body.translate(_PERSIAN_DIGITS).strip()

    # ردیف (1، 2، 3) یا شماره کارت کامل یا خالی
    if body in ("1", "2", "3"):
        arg = body
    else:
        digits = re.sub(r"\D", "", body)
        arg = digits[:16] if len(digits) >= 16 else None

    result = await db_delete_card(chat_id, user_id, arg)
    return await safe_send(bot, chat_id, result, reply_to=message.message_id)


# ─── شروع مسابقه تاس (استفاده از dice_game.py) ───────────────────────────────

@router.message(F.text.regexp(r"^شروع\s+\d+"))
async def cmd_start_game(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "شما دسترسی مجاز را ندارید")
    parts = message.text.split()
    if len(parts) < 2:
        return await _reply(message, "❌ فرمت صحیح:\n• شروع [تعداد] → بازی معمولی\n• شروع [تعداد] [مبلغ] → بازی اعتباری\n\nمثال: شروع 2 یا شروع 2 50")
    try:
        total_players = int(parts[1])
    except ValueError:
        return await _reply(message, "❌ تعداد بازیکن باید عدد باشد!\nمثال: شروع 2")
    bet_amount = 0
    has_bet = False
    if len(parts) >= 3:
        try:
            bet_amount = int(parts[2])
            has_bet = True
            if bet_amount < 5:
                return await _reply(message, "❌ حداقل مبلغ شروع بازی 5 واحد است!")
        except ValueError:
            return await _reply(message, "❌ مبلغ بازی باید عدد باشد!\nمثال: شروع 2 5")
    if total_players < 2:
        return await _reply(message, "❌ حداقل تعداد بازیکن‌ها 2 نفر است!")
    if total_players > 10:
        return await _reply(message, "❌ حداکثر تعداد بازیکن‌ها 10 نفر است!")
    if has_active_game(chat_id):
        return await _reply(message, (
            "⚠️ یک بازی فعال وجود دارد!\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📍 لطفاً صبر کنید تا بازی فعلی تمام شود.\n\n"
            "❌ یا برای توقف، دستور «لغو» را بزنید."
        ))
    fee_percent = await _get_fee(chat_id) if has_bet else 0
    create_game(chat_id, total_players, bet_amount=bet_amount, fee_percent=fee_percent, has_bet=has_bet)
    if has_bet:
        _fee_per = int(bet_amount * fee_percent / 100)
        _entry = bet_amount + _fee_per
        _prize = total_players * bet_amount
        _total_fee = total_players * _fee_per
        msg = (
            f"🎲 رقابت تاس شروع شد!\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 ظرفیت: {total_players} نفر\n\n"
            f"💳 هزینه ورودی هر نفر: {_entry:,} واحد"
            + (f"\n   ├ شرط: {bet_amount:,} واحد\n   └ حق واسطه ({fee_percent}٪): {_fee_per:,} واحد" if fee_percent > 0 else "")
            + f"\n\n🏆 مبلغ برد: {_prize:,} واحد\n"
            + (f"💸 جمع حق واسطه: {_total_fee:,} واحد\n" if fee_percent > 0 else "")
            + f"\n✅ برای شرکت «تاس» بفرست\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ مهلت ثبت‌نام: ۵ دقیقه\n"
            f"📌 جایگاه‌های خالی: {total_players}\n\n"
            f"❌ لغو بازی: «لغو»"
        )
    else:
        msg = (
            f"🎲 رقابت تاس شروع شد!\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 ظرفیت کل: {total_players} نفر\n\n"
            f"✅ برای شرکت در مسابقه، همین حالا\n"
            f"دستور «تاس» را ارسال کنید.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ مهلت ثبت‌نام: ۵ دقیقه\n"
            f"📌 جایگاه‌های خالی: {total_players}\n\n"
            f"❌ لغو بازی: کلمه «لغو»"
        )
    return await _reply(message, msg)


@router.message(F.text == "پایان")
async def cmd_end_game(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "شما دسترسی مجاز را ندارید")
    if not has_active_game(chat_id):
        return await _reply(message, "❌ هیچ بازی فعالی وجود ندارد.")
    game = get_game(chat_id)
    players = game.get("players", [])
    if not players:
        finish_game_cleanup(chat_id)
        return await _reply(message, "❌ هیچ بازیکنی ثبت‌نام نکرده بود. بازی لغو شد.")
    finish_game_cleanup(chat_id)
    return await _reply(message, "✅ بازی با موفقیت پایان یافت.")


@router.message(F.text.in_(["لغو", "لغو بازی", "لغو مسابقه"]))
async def cmd_cancel_game(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "شما دسترسی مجاز را ندارید")
    game = get_game(chat_id)
    if not game:
        return await _reply(message, "❌ هیچ بازی فعالی برای لغو وجود ندارد!")
    total_players = game.get("total_players", 0)
    players_count = len(game.get("players", []))
    status = game.get("status", "unknown")
    status_text = {"waiting": "در حال ثبت‌نام", "playing": "در حال انجام"}.get(status, "فعال")
    finish_game_cleanup(chat_id)
    return await _reply(message, (
        f"✅ بازی با موفقیت لغو شد!\n\n"
        f"📊 وضعیت بازی قبل از لغو:\n"
        f"👥 تعداد بازیکنان: {players_count} از {total_players}\n"
        f"📌 مرحله: {status_text}\n\n"
        f"🎲 می‌توانید با دستور «شروع [تعداد]» یک بازی جدید بسازید."
    ))


def _dice_stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            IKB(text="📅 روزانه",  callback_data="dstat:daily"),
            IKB(text="📆 هفتگی",  callback_data="dstat:weekly"),
            IKB(text="📊 کل",     callback_data="dstat:total"),
        ],
        [IKB(text="❌ بستن", callback_data="dstat:close")],
    ])


async def _build_dice_stats_text(chat_id: int, period: str, bot: Bot) -> str:
    rows = await db_get_dice_stats(chat_id, period)
    labels = {"daily": "📅 روزانه (۲۴ ساعت گذشته)", "weekly": "📆 هفتگی (۷ روز گذشته)", "total": "📊 کل"}
    title = labels.get(period, period)
    if not rows:
        return f"<b>{title}</b>\n\nهنوز تاسی ثبت نشده است."

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"<b>🎲 آمار تاس — {title}</b>", "━━━━━━━━━━━━━━━━"]
    for i, r in enumerate(rows):
        uid = r["telegram_user_id"]
        try:
            member = await bot.get_chat_member(chat_id, uid)
            name = member.user.full_name or str(uid)
        except Exception:
            name = str(uid)
        rank = medals[i] if i < 3 else f"{i+1}."
        avg = float(r["avg"])
        lines.append(
            f"{rank} <b>{name}</b>\n"
            f"   🎲 {r['rolls']} بار  |  مجموع: {r['total']}  |  میانگین: {avg:.1f}\n"
            f"   بیشترین: {r['max_val']}  |  کمترین: {r['min_val']}"
        )
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append(f"👥 تعداد بازیکنان: {len(rows)}")
    return "\n".join(lines)


@router.message(F.text.in_(["آمار تاس", "امار تاس", "آمار بازی", "امار بازی"]))
async def cmd_dice_stats(message: Message, bot: Bot):
    chat_id = message.chat.id
    text = "🎲 <b>آمار تاس</b>\n\nبازه زمانی رو انتخاب کن:"
    await safe_send(bot, chat_id, text,
                    reply_markup=_dice_stats_kb(), reply_to=message.message_id)


@router.message(F.text.in_(["آمار تاس روزانه", "امار تاس روزانه"]))
async def cmd_dice_stats_daily(message: Message, bot: Bot):
    chat_id = message.chat.id
    text = await _build_dice_stats_text(chat_id, "daily", bot)
    await safe_send(bot, chat_id, text,
                    reply_markup=_dice_stats_kb(), reply_to=message.message_id)


@router.message(F.text.in_(["آمار تاس هفتگی", "امار تاس هفتگی", "آمار بازی هفتگی"]))
async def cmd_dice_stats_weekly(message: Message, bot: Bot):
    chat_id = message.chat.id
    text = await _build_dice_stats_text(chat_id, "weekly", bot)
    await safe_send(bot, chat_id, text,
                    reply_markup=_dice_stats_kb(), reply_to=message.message_id)


@router.message(F.text.in_(["آمار تاس کل", "امار تاس کل", "آمار بازی کل", "آمار تاس کلی"]))
async def cmd_dice_stats_total(message: Message, bot: Bot):
    chat_id = message.chat.id
    text = await _build_dice_stats_text(chat_id, "total", bot)
    await safe_send(bot, chat_id, text,
                    reply_markup=_dice_stats_kb(), reply_to=message.message_id)


@router.callback_query(F.data.startswith("dstat:"))
async def cb_dice_stats(call: CallbackQuery, bot: Bot):
    period = call.data[6:]
    if period == "close":
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.answer()
        return
    chat_id = call.message.chat.id
    text = await _build_dice_stats_text(chat_id, period, bot)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=_dice_stats_kb())
    except Exception:
        pass
    await call.answer()


# ─── نصب و ثبت مالکیت ───────────────────────────────────────────────────────
# نصب دیگر با دستور متنی نیست — به‌محض گرفتن دسترسی ادمین کامل توسط ربات،
# نصب و ثبت مالکیت به‌صورت خودکار انجام می‌شود (bot/handlers/group_lifecycle.py)


# ─── هندلر تاس (سیستم کامل) ─────────────────────────────────────────────────

@router.message(F.text.regexp(r"^تاس(\s*\d+)?$"))
async def cmd_dice(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    if chat_id in cache.OFF_GROUP:
        return

    # اگه منتظر انتخاب راند هستیم و این عدده
    if chat_id in WAITING_ROUNDS and text.isdigit():
        await handle_round_selection(chat_id, user_id, text, bot, message.message_id)
        return

    theme_id = await db_get_group_theme(chat_id)
    dice_option_off = chat_id not in cache.DICE_OPTION
    await handle_dice(
        text=text,
        chat_id=chat_id,
        message_id=message.message_id,
        bot=bot,
        user_id=user_id,
        dice_option_off=dice_option_off,
        theme_id=theme_id,
    )


# ─── ایموجی تاس/بازی فرستاده‌شده مستقیم توسط کاربر ──────────────────────────

_DICE_EMOJI_MAP = {
    "🎲": "dice",
    "🎯": "dart",
    "🏀": "basketball",
    "⚽": "football",
    "🎳": "bowling",
    "🎰": "slot",
}


@router.message(F.dice)
async def handle_native_dice(message: Message, bot: Bot):
    chat_id  = message.chat.id
    user_id  = message.from_user.id
    emoji    = message.dice.emoji
    value    = message.dice.value

    if chat_id in cache.OFF_GROUP:
        return

    # فقط تاس 🎲 با game logic کامل درگیر می‌شه
    if emoji == "🎲":
        LAST_DICE[chat_id] = value
        await db_record_dice_roll(chat_id, user_id, value)

        game = get_game(chat_id)
        if game and game.get("status") == "playing":
            allowed, remaining, err = can_player_roll(chat_id, user_id, 1)
            if not allowed:
                await bot.send_message(chat_id, err, reply_to_message_id=message.message_id)
                return
            await _handle_game_roll_silent(chat_id, user_id, 1, value, message.message_id, bot)
            return

        # بازی تعیین (waiting)
        if has_active_game(chat_id):
            should_cont = await should_continue(chat_id, user_id, bot, message.message_id, "تاس")
            if should_cont == 0:
                return
            if should_cont == 2:
                await asyncio.sleep(0.5)
                await register_and_save_dice(chat_id, user_id, value, bot, message.message_id)
        # تاس آزاد — استیکر خودش کافیه، چیزی نمی‌فرستیم
        return

    # بقیه emoji‌ها (🎯🏀⚽🎳🎰) — انیمیشن تلگرام کافیه، ربات چیزی نمی‌گه


# ─── شروع مسابقه (جایگزین کامل) ─────────────────────────────────────────────

# (handler قدیمی حذف شد و در بخش مسابقه تاس جدید زیر آمده)

# ─── انتخاب راند توسط برنده (هر عدد خالص) ────────────────────────────────────

@router.message(F.text.regexp(r"^\d+$"))
async def cmd_round_selection(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id not in WAITING_ROUNDS:
        return
    await handle_round_selection(chat_id, user_id, message.text, bot, message.message_id)


# ─── همگام‌سازی ادمین‌های واقعی تلگرام ──────────────────────────────────────

@router.message(F.text.in_(["همگام سازی", "همگام‌سازی", "سینک ادمین", "سینک", "sync admin"]))
async def cmd_sync_admins(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id) and not is_admin(chat_id, user_id):
        return await _reply(message, "❌ فقط مالک یا ادمین می‌تواند این دستور را اجرا کند.")

    try:
        tg_admins = await bot.get_chat_administrators(chat_id)
    except Exception as e:
        return await _reply(message, f"❌ خطا در دریافت ادمین‌های تلگرام:\n{e}")

    owner_id = None
    admin_ids = []
    for member in tg_admins:
        if member.status == "creator":
            owner_id = member.user.id
        elif member.status == "administrator":
            admin_ids.append(member.user.id)

    if owner_id:
        await db_set_owner(chat_id, owner_id)
        cache.OWNER_CACHE[chat_id] = owner_id

    for aid in admin_ids:
        await db_add_admin(chat_id, aid)
        cache.ADMINS_CACHE.setdefault(chat_id, set()).add(aid)

    owner_mention = await _mention(owner_id, bot, chat_id) if owner_id else "یافت نشد"
    text = (
        f"✅ همگام‌سازی با تلگرام انجام شد\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👑 مالک: {owner_mention}\n"
        f"👥 ادمین‌های همگام‌سازی‌شده: {len(admin_ids)} نفر\n\n"
        f"📌 حالا ربات مالک و ادمین‌های واقعی گروه را می‌شناسد."
    )
    return await _reply(message, text)


@router.message(F.text == "مالک واقعی")
async def cmd_real_owner(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id) and not is_admin(chat_id, user_id):
        return

    try:
        tg_admins = await bot.get_chat_administrators(chat_id)
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")

    creator = next((m for m in tg_admins if m.status == "creator"), None)
    if not creator:
        return await _reply(message, "❌ مالک گروه یافت نشد (شاید گروه creator ندارد).")

    owner_id = creator.user.id
    await db_set_owner(chat_id, owner_id)
    cache.OWNER_CACHE[chat_id] = owner_id
    mention = await _mention(owner_id, bot, chat_id)
    return await _reply(message, f"👑 مالک واقعی گروه:\n{mention}\n\nبه عنوان مالک در ربات ثبت شد.")


# ─── خوشامدگویی ──────────────────────────────────────────────────────────────

@router.message(F.new_chat_members)
async def handle_new_member(message: Message, bot: Bot):
    chat_id = message.chat.id
    if chat_id in cache.OFF_GROUP:
        return
    if chat_id in cache.WELCOME_DISABLED:
        return
    settings = cache.WELCOME_SETTINGS.get(chat_id, {})
    welcome_text = settings.get("text") or DEFAULT_WELCOME_TEXT
    gif_file_id = settings.get("gif_file_id") or DEFAULT_WELCOME_GIF_FILE_ID
    for new_member in message.new_chat_members:
        if new_member.is_bot:
            continue
        name = new_member.first_name or new_member.username or str(new_member.id)
        text = welcome_text.replace("{name}", name).replace("{id}", str(new_member.id))
        if gif_file_id:
            try:
                await bot.send_animation(chat_id, animation=gif_file_id, caption=text, parse_mode="HTML")
                continue
            except Exception:
                pass
        await safe_send(bot, chat_id, text)


@router.message(F.text.in_(["خوشامد روشن", "خوشامدگویی روشن"]))
async def cmd_welcome_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.WELCOME_DISABLED.discard(chat_id)
    await db_set_welcome(chat_id, enabled=True)
    return await _reply(message,
        "✅ خوشامدگویی روشن شد.\n\n"
        "تنظیمات:\n"
        "  متن خوشامد [پیام] — تغییر متن\n"
        "  گیف خوشامد — ریپلای روی گیف\n"
        "  حذف گیف خوشامد\n\n"
        "متغیر: {name} = نام عضو جدید"
    )


@router.message(F.text.in_(["خوشامد خاموش", "خوشامدگویی خاموش"]))
async def cmd_welcome_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.WELCOME_DISABLED.add(chat_id)
    await db_set_welcome(chat_id, enabled=False)
    return await _reply(message, "❌ خوشامدگویی خاموش شد.")


@router.message(F.text.regexp(r"^متن خوشامد\s+.+$"))
async def cmd_set_welcome_text(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    text = message.text[len("متن خوشامد"):].strip()
    if len(text) > 500:
        return await _reply(message, "❌ متن نمی‌تواند بیشتر از ۵۰۰ کاراکتر باشد.")
    cache.WELCOME_SETTINGS.setdefault(chat_id, {})["text"] = text
    await db_set_welcome(chat_id, text=text)
    return await _reply(message,
        f"✅ متن خوشامد تنظیم شد:\n\n{text}\n\n"
        "💡 متغیر: {name} = نام عضو جدید"
    )


@router.message(F.text == "گیف خوشامد")
async def cmd_set_welcome_gif(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not message.reply_to_message or not message.reply_to_message.animation:
        return await _reply(message, "⚠️ لطفاً روی یک گیف (GIF) ریپلای کنید.")
    gif_file_id = message.reply_to_message.animation.file_id
    cache.WELCOME_SETTINGS.setdefault(chat_id, {})["gif_file_id"] = gif_file_id
    await db_set_welcome(chat_id, gif_file_id=gif_file_id)
    return await _reply(message, "✅ گیف خوشامد تنظیم شد.")


@router.message(F.text == "حذف گیف خوشامد")
async def cmd_del_welcome_gif(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.WELCOME_SETTINGS.setdefault(chat_id, {})["gif_file_id"] = ""
    await db_set_welcome(chat_id, gif_file_id="")
    return await _reply(message, "✅ گیف خوشامد حذف شد.")


@router.message(F.text.in_(["خوشامد", "وضعیت خوشامد", "تنظیمات خوشامد"]))
async def cmd_welcome_status(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    enabled = chat_id not in cache.WELCOME_DISABLED
    s = cache.WELCOME_SETTINGS.get(chat_id, {})
    text = s.get("text") or DEFAULT_WELCOME_TEXT + " (پیش‌فرض)"
    has_gif = bool(s.get("gif_file_id"))
    preview = text[:60] + ("..." if len(text) > 60 else "")
    return await _reply(message,
        f"🎉 وضعیت خوشامدگویی\n\n"
        f"  وضعیت: {'✅ روشن' if enabled else '❌ خاموش'}\n"
        f"  متن: {preview}\n"
        f"  گیف: {'✅ تنظیم شده' if has_gif else '❌ ندارد'}"
    )


# ─── آنتی فلود ────────────────────────────────────────────────────────────────

@router.message(F.text.in_(["فلود روشن", "آنتی فلود روشن", "ضد فلود روشن"]))
async def cmd_flood_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.ANTI_FLOOD_ENABLED.add(chat_id)
    await db_set_anti_flood(chat_id, enabled=True)
    cfg = cache.ANTI_FLOOD_SETTINGS.get(chat_id, {"limit": 5, "window": 10})
    return await _reply(message,
        f"✅ آنتی فلود روشن شد.\n\n"
        f"  حد: {cfg['limit']} پیام در {cfg['window']} ثانیه\n\n"
        "برای تغییر حد: حد فلود [تعداد پیام] [ثانیه]\n"
        "مثال: حد فلود 5 10"
    )


@router.message(F.text.in_(["فلود خاموش", "آنتی فلود خاموش", "ضد فلود خاموش"]))
async def cmd_flood_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.ANTI_FLOOD_ENABLED.discard(chat_id)
    await db_set_anti_flood(chat_id, enabled=False)
    return await _reply(message, "❌ آنتی فلود خاموش شد.")


@router.message(F.text.regexp(r"^حد فلود\s+\d+\s+\d+$"))
async def cmd_set_flood_limit(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    parts = message.text.split()
    limit = int(parts[2])
    window = int(parts[3])
    if not 2 <= limit <= 30:
        return await _reply(message, "❌ حد پیام باید بین ۲ تا ۳۰ باشد.")
    if not 3 <= window <= 60:
        return await _reply(message, "❌ بازه زمانی باید بین ۳ تا ۶۰ ثانیه باشد.")
    cache.ANTI_FLOOD_SETTINGS[chat_id] = {"limit": limit, "window": window}
    await db_set_anti_flood(chat_id, limit=limit, window=window)
    return await _reply(message,
        f"✅ حد فلود تنظیم شد:\n\n"
        f"  بیشتر از {limit} پیام در {window} ثانیه = سکوت ۵ دقیقه‌ای"
    )


@router.message(F.text.in_(["فلود", "وضعیت فلود", "وضعیت آنتی فلود"]))
async def cmd_flood_status(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    enabled = chat_id in cache.ANTI_FLOOD_ENABLED
    cfg = cache.ANTI_FLOOD_SETTINGS.get(chat_id, {"limit": 5, "window": 10})
    return await _reply(message,
        f"🚫 وضعیت آنتی فلود\n\n"
        f"  وضعیت: {'✅ روشن' if enabled else '❌ خاموش'}\n"
        f"  حد: {cfg['limit']} پیام در {cfg['window']} ثانیه\n"
        f"  مجازات: سکوت ۵ دقیقه‌ای"
    )


# ─── هندلر پیش‌فرض متن گروه ─────────────────────────────────────────────────
# (یادگیری خودکار و پیام‌های سخنگو)

@router.message(F.text)
async def handle_group_text(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or ""

    if chat_id in cache.OFF_GROUP:
        return

    if chat_id in cache.GROUP_LOCK and not has_privilege(chat_id, user_id):
        try:
            await message.delete()
        except Exception:
            pass
        return

    learns = cache.LEARNED_RESPONSES.get(chat_id, {})
    if learns:
        key = text.lower().strip()
        if key in learns:
            return await _reply(message, learns[key])

    if chat_id in cache.SPEAKER_ON and text and not text.startswith("/"):
        # جستجوی جزئی در یادگیری‌ها
        learns = cache.LEARNED_RESPONSES.get(chat_id, {})
        key = text.lower().strip()
        # اول match کامل، بعد جستجوی جزئی
        response = learns.get(key)
        if response is None:
            for trigger, resp in learns.items():
                if trigger in key or key in trigger:
                    response = resp
                    break
        if response:
            await _reply(message, response)
