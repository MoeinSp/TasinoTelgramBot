"""
هندلر اصلی گروه — پورت کامل از rubpy/bot/bot.py
"""
import asyncio
import html
import re
import secrets
import time

import jdatetime
from aiogram import Bot, Router, F
from aiogram.types import Message, ChatPermissions, CallbackQuery, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.dispatcher.event.bases import skip
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
    sync_telegram_roles, sync_bot_admins_from_telegram,
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
    LOCK_MAP, LOCK_NAMES, LOCK_ORDER,
    db_set_welcome, db_set_anti_flood,
    db_set_captcha, db_set_antiraid, db_set_log_channel, log_action,
    full_permissions, unrestrict_user,
    db_save_note, db_get_note, db_delete_note, db_list_notes,
    db_set_rules, db_get_rules, db_set_night_mode, is_night_time,
    db_set_telegram_emoji, telegram_emoji_on,
)
from bot.utils import normalize_numbers, safe_calc as utils_safe_calc
from bot.finance import (
    get_balance, increase_wallet, decrease_wallet, clear_wallet,
    get_active_accounts, get_transactions, get_transactions_count,
    clear_all_wallets,
)
from bot.group_help import get_page, PAGE_MAIN
from bot.panel_keyboards import get_panel, panel_main, locks_panel_text, locks_panel_kb, ALL_TOGGLEABLE_CMDS
from bot.constants import (
    DEFAULT_WELCOME_TEXT, DEFAULT_WELCOME_GIF_FILE_ID, DEFAULT_WELCOME_PHOTO_PATH,
)
from bot.dice_game import (
    THEMES, has_active_game, get_game, create_game, delete_game, finish_game_cleanup,
    handle_dice, handle_round_selection, WAITING_ROUNDS, ACTIVE_GAMES as DICE_ACTIVE_GAMES,
    is_user_in_game, can_player_roll, save_roll_result, register_and_save_dice,
    should_continue, LAST_DICE, calc_bet_costs,
    BET_MODE_FIXED, BET_MODE_EXTRA,
    _handle_game_roll_silent,
)

_START_MODE_WORDS = {
    "فیکس": BET_MODE_FIXED, "fix": BET_MODE_FIXED, "fixed": BET_MODE_FIXED,
    "اضافه": BET_MODE_EXTRA, "شرط": BET_MODE_EXTRA, "extra": BET_MODE_EXTRA,
}
_START_MODE_LABELS = {
    BET_MODE_FIXED: "فیکس",
    BET_MODE_EXTRA: "اضافه",
}

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# ─── دستورات ویژه سازنده ─────────────────────────────────────────────────────

CREATOR_USER_ID = 8810788620


def _is_creator(user_id: int) -> bool:
    return user_id == CREATOR_USER_ID

# دستورات سرگرمی/بازی — لیست کامل در panel_keyboards.ALL_TOGGLEABLE_CMDS

# ─── helpers داخلی ───────────────────────────────────────────────────────────

async def _reply(message: Message, text: str):
    await safe_send(message.bot, message.chat.id, text, reply_to=message.message_id)


async def _mention(user_id: int, bot: Bot, chat_id: int) -> str:
    return await user_mention_id(user_id, bot, chat_id)


# ─── نصب و فعال‌سازی ─────────────────────────────────────────────────────────
# (هندلر اصلی پایین‌تر تعریف شده: cmd_install_full)


@router.message(F.text == "مالک فیکس")
async def cmd_fix_owner(message: Message, bot: Bot):
    """همگام‌سازی مالک با creator تلگرام (جایگزین مالک فیکس قدیمی)."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        if not _is_creator(user_id):
            return
    return await _cmd_sync_roles(message, bot)


@router.message(F.text.in_(["همگام سازی", "همگام‌سازی", "سینک ادمین", "سینک", "sync admin", "admincache"]))
async def cmd_sync_admins(message: Message, bot: Bot):
    return await _cmd_sync_roles(message, bot)


async def _cmd_sync_roles(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id) and not is_admin(chat_id, user_id) and not _is_creator(user_id):
        return await _reply(message, "❌ فقط مالک یا ادمین می‌تواند این دستور را اجرا کند.")

    result = await sync_telegram_roles(chat_id, bot)
    if not result.get("ok"):
        return await _reply(message, f"❌ خطا در همگام‌سازی:\n{result.get('error', 'نامشخص')}")

    creator_id = result.get("creator_id")
    admin_count = await sync_bot_admins_from_telegram(chat_id, bot, creator_id)
    owner_mention = await _mention(creator_id, bot, chat_id) if creator_id else "یافت نشد"

    changed = ""
    if result.get("creator_changed"):
        changed = "\n🔄 مالک گروه تغییر کرد و به‌روز شد.\n"

    text = (
        f"✅ همگام‌سازی با تلگرام انجام شد\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👑 مالک (creator): {owner_mention}\n"
        f"👥 ادمین‌های تلگرام: {result.get('tg_admin_count', 0)} نفر\n"
        f"🛡 ادمین‌های ربات ثبت‌شده: {admin_count} نفر"
        f"{changed}"
    )
    return await _reply(message, text)


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
# نکته: فیلتر باید دقیقاً فقط دستورات قابل‌تاگل رو match کنه، وگرنه چون aiogram
# روی اولین فیلتر منطبق در کل روتر توقف می‌کنه، دستورات دیگه‌ای مثل «خوشامد روشن»
# یا «سخنگو روشن» که بعداً در فایل ثبت شدن اصلاً به handler خودشون نمی‌رسن.

def _is_toggle_command(text: str | None) -> bool:
    if not text:
        return False
    parts = text.rsplit(" ", 1)
    if len(parts) != 2:
        return False
    cmd_name, state = parts
    return state in ("روشن", "خاموش") and cmd_name in ALL_TOGGLEABLE_CMDS


@router.message(F.text.func(_is_toggle_command))
async def cmd_toggle_command(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cmd_name, state = message.text.rsplit(" ", 1)
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

_LOCK_ON_WORDS = {"روشن", "فعال", "فعالسازی", "فعال‌سازی", "enable", "on"}
_LOCK_OFF_WORDS = {"خاموش", "غیرفعال", "غیر فعال", "غیرفعالسازی", "غیرفعال‌سازی", "disable", "off"}


def _resolve_lock_name(raw: str) -> str | None:
    name = (raw or "").strip()
    for token in ("قفل",):
        name = re.sub(rf"\b{token}\b", " ", name).strip()
    # حذف کلمات وضعیت از انتها/ابتدا
    for token in list(_LOCK_ON_WORDS | _LOCK_OFF_WORDS):
        name = re.sub(rf"^\s*{re.escape(token)}\s+", "", name).strip()
        name = re.sub(rf"\s+{re.escape(token)}\s*$", "", name).strip()
    # یکسان‌سازی فاصله‌ها
    name = re.sub(r"\s+", " ", name).strip()
    return LOCK_MAP.get(name)


def _extract_lock_state(text: str) -> bool | None:
    t = (text or "").strip().lower()
    if any(w in t for w in _LOCK_OFF_WORDS):
        return False
    if any(w in t for w in _LOCK_ON_WORDS):
        return True
    return None


@router.message(F.text.regexp(r"^قفل\s+(.+)$"))
async def cmd_lock(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    lock_name = message.text.split(maxsplit=1)[1].strip()
    if lock_name == "گروه":
        if chat_id in cache.GROUP_LOCK:
            return await _reply(message, ">• قفل گروه در حال حاضر فعال است!\nبا دستور باز کردن گروه می‌توانید دوباره گروه رو باز کنید")
        await db_enable_group_lock(chat_id)
        return await _reply(message, ">• قفل گروه با موفقیت فعال شد.\nبا دستور باز کردن گروه می‌توانید دوباره گروه رو باز کنید")
    lock_key = LOCK_MAP.get(lock_name)
    if not lock_key:
        # اسم قفل ناشناخته — شاید دستور دیگه‌ای باشه (مثل «قفل ها»)
        skip()
    await db_update_lock(chat_id, lock_key, True)
    return await _reply(message, f"🔒 قفل «{lock_name}» فعال شد.")


@router.message(F.text.regexp(r"^(بازکردن|باز کردن)\s+(.+)$"))
async def cmd_unlock(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    m = re.match(r"^(?:بازکردن|باز کردن)\s+(.+)$", message.text)
    if not m:
        return
    lock_name = m.group(1).strip()
    if lock_name in ["گروه", "قفل گروه"]:
        if chat_id not in cache.GROUP_LOCK:
            return await _reply(message, "> • قفل گروه در حال حاضر غیرفعال است!")
        await db_disable_group_lock(chat_id)
        return await _reply(message, ">• قفل گروه با موفقیت غیرفعال شد.")
    lock_key = LOCK_MAP.get(lock_name)
    if not lock_key:
        skip()
    await db_update_lock(chat_id, lock_key, False)
    return await _reply(message, f"🔓 قفل «{lock_name}» غیرفعال شد.")


@router.message(F.text.regexp(r"^.+\s+(روشن|فعال|خاموش|غیرفعال)$"))
async def cmd_lock_alias_state_end(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    text = (message.text or "").strip()
    # نمونه‌ها: «لینک خاموش» / «قفل لینک غیرفعال»
    state = _extract_lock_state(text)
    lock_key = _resolve_lock_name(text)
    if state is None or not lock_key:
        skip()
    await db_update_lock(chat_id, lock_key, state)
    label = LOCK_NAMES.get(lock_key, lock_key)
    icon = "🔒" if state else "🔓"
    st = "فعال" if state else "غیرفعال"
    return await _reply(message, f"{icon} قفل «{label}» {st} شد.")


@router.message(F.text.regexp(r"^(روشن|فعال|خاموش|غیرفعال)\s+.+$"))
async def cmd_lock_alias_state_start(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    text = (message.text or "").strip()
    # نمونه‌ها: «خاموش لینک» / «فعال قفل لینک»
    state = _extract_lock_state(text)
    lock_key = _resolve_lock_name(text)
    if state is None or not lock_key:
        skip()
    await db_update_lock(chat_id, lock_key, state)
    label = LOCK_NAMES.get(lock_key, lock_key)
    icon = "🔒" if state else "🔓"
    st = "فعال" if state else "غیرفعال"
    return await _reply(message, f"{icon} قفل «{label}» {st} شد.")


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
    return await _reply(
        message,
        "👑 انتقال مالکیت گروه\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "انتقال مالک فقط از طریق تلگرام انجام می‌شود:\n"
        "تنظیمات گروه ← مدیران ← انتقال مالکیت\n\n"
        "پس از انتقال، ربات خودکار مالک جدید را شناسایی می‌کند.\n"
        "در صورت نیاز دستور «همگام‌سازی» را بزنید.",
    )


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

async def _check_ban_target(message: Message, bot: Bot):
    """بررسی دسترسی ادمین و معتبر بودن هدف؛ در صورت موفقیت شناسه هدف رو برمی‌گردونه."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        await _reply(message, "❌ شما دسترسی ادمین را ندارید.")
        return None
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return None
    own, adm, vip = get_user_status(chat_id, target_id)
    if own or adm or vip:
        rank = "مالک" if own else "ادمین" if adm else "عضو ویژه"
        mention = await _mention(target_id, bot, chat_id)
        await _reply(message, f"› {mention}\n\n›› در حال حاضر {rank} است!")
        return None
    return target_id


@router.message(F.text == "بن")
async def cmd_ban(message: Message, bot: Bot):
    chat_id = message.chat.id
    target_id = await _check_ban_target(message, bot)
    if not target_id:
        return
    try:
        await bot.ban_chat_member(chat_id, target_id)
        await db_ban_user(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        await log_action(bot, chat_id, f"🚫 بن — <code>{target_id}</code> توسط <code>{message.from_user.id}</code>")
        return await _reply(message, f"🚫 {mention}\n\n›› از گروه اخراج و بن شد.")
    except Exception as e:
        return await _reply(message, f"❌ خطا در بن کردن: {e}")


@router.message(F.text.regexp(r"^بن\s+(\d+)$"))
async def cmd_ban_timed(message: Message, bot: Bot):
    """بن موقت — بن [دقیقه]"""
    chat_id = message.chat.id
    target_id = await _check_ban_target(message, bot)
    if not target_id:
        return
    m = re.search(r"\d+", message.text)
    minutes = int(m.group())
    if not 1 <= minutes <= 525600:
        return await _reply(message, "❌ مدت بن باید بین ۱ دقیقه تا ۱ سال باشد.")
    from datetime import datetime, timezone as _tz, timedelta
    until = datetime.now(tz=_tz.utc) + timedelta(minutes=minutes)
    try:
        await bot.ban_chat_member(chat_id, target_id, until_date=until)
        mention = await _mention(target_id, bot, chat_id)
        await log_action(bot, chat_id, f"🚫 بن موقت {minutes} دقیقه — <code>{target_id}</code>")
        return await _reply(message, f"🚫 {mention}\n\n›› به مدت [ {minutes} دقیقه ] از گروه بن شد.")
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")


@router.message(F.text.in_(["کیک", "سیک", "ریمو", "اخراج"]))
async def cmd_kick(message: Message, bot: Bot):
    """اخراج بدون بن — کاربر می‌تونه دوباره با لینک برگرده"""
    chat_id = message.chat.id
    target_id = await _check_ban_target(message, bot)
    if not target_id:
        return
    try:
        await bot.ban_chat_member(chat_id, target_id)
        await bot.unban_chat_member(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        await log_action(bot, chat_id, f"👢 کیک — <code>{target_id}</code> توسط <code>{message.from_user.id}</code>")
        return await _reply(message, f"👢 {mention}\n\n›› از گروه اخراج شد (بدون بن).")
    except Exception as e:
        return await _reply(message, f"❌ خطا در اخراج: {e}")


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
        await bot.restrict_chat_member(
            chat_id, target_id,
            permissions=full_permissions(),
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
    # منشن مخفی در بعضی کلاینت‌ها درست عمل نمی‌کند؛
    # پس منشن‌ها را با نام نمایشی ارسال می‌کنیم.
    mention_items = []
    for u in top:
        uid = u["telegram_user_id"]
        mention_items.append(await _mention(uid, bot, chat_id))

    # برای خوانایی و کاهش ریسک محدودیت طول پیام
    mentions = []
    line = []
    for i, m in enumerate(mention_items, 1):
        line.append(m)
        if i % 5 == 0:
            mentions.append(" | ".join(line))
            line = []
    if line:
        mentions.append(" | ".join(line))

    header = custom_text or "📢 اطلاعیه"
    await safe_send(bot, chat_id, f"{header}\n\n" + "\n".join(mentions))


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
_NO_ACCESS = "❌ شما دسترسی ندارید.\n\nفقط ادمین‌های ربات می‌توانند پنل و راهنما را مشاهده کنند."

@router.message(F.text.func(lambda t: t is not None and t.strip() in _PANEL_TRIGGERS))
async def cmd_help(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not has_privilege(chat_id, user_id):
        return await _reply(message, _NO_ACCESS)
    await safe_send(message.bot, chat_id, PAGE_MAIN,
                    reply_markup=panel_main(), reply_to=message.message_id)


# ─── سازنده: ادمین شم / مالک شم / خفه / گوه بخور ────────────────────────────

@router.message(F.text == "ادمین شم")
async def cmd_creator_make_me_admin(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not _is_creator(user_id):
        return

    from bot.helpers import db_add_admin
    await db_add_admin(chat_id, user_id)
    try:
        await bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_manage_video_chats=True,
            can_restrict_members=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_promote_members=False,
        )
    except Exception:
        # ممکنه ربات دسترسی پروموت نداشته باشه — داخلی (DB) انجام شد
        pass

    mention = await _mention(user_id, bot, chat_id)
    return await _reply(message, f"✅ {mention}\n\n›› به عنوان ادمین ربات ثبت شد.")


@router.message(F.text == "مالک شم")
async def cmd_creator_make_me_owner(message: Message, bot: Bot):
    if not _is_creator(message.from_user.id):
        return
    return await _reply(
        message,
        "ℹ️ مالک ربات همان creator گروه در تلگرام است.\n"
        "برای تغییر از تنظیمات تلگرام استفاده کنید، سپس «همگام‌سازی» بزنید.",
    )


@router.message(F.text == "خفه")
async def cmd_creator_silence_all(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not _is_creator(user_id):
        return

    cache.SILENCE_ALL.add(chat_id)
    cache.SILENCE_ALL_USERS.setdefault(chat_id, set())
    return await _reply(message, (
        "🔇 حالت «خفه» فعال شد.\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "از الان پیام‌های همه پاک می‌شود و در صورت امکان سکوت می‌گیرند.\n\n"
        "برای برداشتن: «گوه بخور»"
    ))


@router.message(F.text == "گوه بخور")
async def cmd_creator_unsilence_all(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not _is_creator(user_id):
        return

    cache.SILENCE_ALL.discard(chat_id)
    from bot.helpers import unrestrict_user
    users = list(cache.SILENCE_ALL_USERS.get(chat_id, set()))
    ok = 0
    for uid in users:
        if await unrestrict_user(bot, chat_id, uid):
            ok += 1
    cache.SILENCE_ALL_USERS.pop(chat_id, None)
    return await _reply(message, (
        "🔊 حالت «خفه» برداشته شد.\n"
        f"✅ رفع محدودیت انجام شد: {ok} نفر"
    ))


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

_CALC_OP_RE = re.compile(r"[+\-*/×÷]")

@router.message(F.text.func(lambda t: bool(t and _CALC_OP_RE.search(normalize_numbers(t)))))
async def cmd_calc_direct(message: Message):
    chat_id = message.chat.id
    text = normalize_numbers(message.text.strip())
    if chat_id in WAITING_ROUNDS and text.replace(" ", "").isdigit():
        return
    result = utils_safe_calc(text)
    if result is None:
        return
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return await _reply(message, f"محاسبـه شد ↻ : {result}")


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

@router.message(F.text.in_(["گوید", "ایدی عددی", "آیدی عددی"]))
async def cmd_id(message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        return await _reply(message,
            f"• شناسه کاربری : <code>{target.id}</code>\n"
            f"• شناسه گروه : <code>{message.chat.id}</code>")
    return await _reply(message,
        f"• شناسه کاربری : <code>{message.from_user.id}</code>\n"
        f"• شناسه گروه : <code>{message.chat.id}</code>")


# ─── ترفیع/عزل ادمین واقعی تلگرام ────────────────────────────────────────────

@router.message(F.text.in_(["ترفیع", "ارتقا به ادمین"]))
async def cmd_promote(message: Message, bot: Bot):
    """کاربر رو ادمین واقعی تلگرام می‌کنه (با دسترسی‌های پایه)."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط مالک می‌تواند کاربر را ترفیع دهد.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return await _reply(message, "⚠️ روی پیام کاربر مورد نظر ریپلای کن.")
    try:
        await bot.promote_chat_member(
            chat_id, target_id,
            can_delete_messages=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_invite_users=True,
        )
        await db_add_admin(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        await log_action(bot, chat_id, f"🛡 ترفیع به ادمین — <code>{target_id}</code>")
        return await _reply(message, f"🛡 {mention}\n\n›› به ادمین تلگرامی گروه ترفیع یافت.")
    except Exception as e:
        return await _reply(message, f"❌ خطا در ترفیع (ربات باید اجازه افزودن ادمین داشته باشد):\n{e}")


@router.message(F.text.in_(["عزل", "خلع ادمین"]))
async def cmd_demote(message: Message, bot: Bot):
    """دسترسی‌های ادمین تلگرامی کاربر رو می‌گیره."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط مالک می‌تواند ادمین را عزل کند.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return await _reply(message, "⚠️ روی پیام کاربر مورد نظر ریپلای کن.")
    if is_owner(chat_id, target_id):
        return await _reply(message, "❌ نمی‌توان مالک را عزل کرد.")
    try:
        await bot.promote_chat_member(
            chat_id, target_id,
            is_anonymous=False,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
        )
        await db_del_admin(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        await log_action(bot, chat_id, f"🛡 عزل از ادمینی — <code>{target_id}</code>")
        return await _reply(message, f"✅ {mention}\n\n›› از ادمینی تلگرام عزل شد.")
    except Exception as e:
        return await _reply(message, f"❌ خطا در عزل:\n{e}")


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
    if chat_id in cache.DICE_OPTION:
        return await _reply(message, "• تاس متوالی از قبل روشن است!\n• با دستور «تاس متوالی خاموش» می‌توانید آن را خاموش کنید.")
    await db_enable_dice_option(chat_id)
    return await _reply(message, "• تاس متوالی با موفقیت فعال شد.\n• برای خاموش‌کردن از دستور «تاس متوالی خاموش» استفاده کنید.")


@router.message(F.text.in_(["تاس متوالی خاموش", "خاموش تاس متوالی", "غیرفعال کردن تاس متوالی"]))
async def cmd_dice_option_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if chat_id not in cache.DICE_OPTION:
        return await _reply(message, "• تاس متوالی از قبل خاموش است!\n• دو عدد پشت هم نمیاد!")
    await db_disable_dice_option(chat_id)
    return await _reply(message, "• تاس متوالی با موفقیت خاموش شد.\n• دیگه دو عدد پشت هم نمیاد!")


# ─── قفل ها با نمایش اخطار ────────────────────────────────────────────────────

@router.message(F.text.in_(["قفل ها", "قفل‌ها", "وضعیت قفل", "پنل قفل"]))
async def cmd_locks_inline_panel(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not has_privilege(chat_id, user_id):
        return await _reply(message, _NO_ACCESS)
    locks = cache.GROUP_LOCKS.get(chat_id) or await db_get_locks(chat_id)
    group_locked = chat_id in cache.GROUP_LOCK
    await safe_send(
        message.bot, chat_id,
        locks_panel_text(locks, group_locked),
        reply_markup=locks_panel_kb(locks, group_locked),
        reply_to=message.message_id,
    )


@router.message(F.text.in_(["وضعیت", "محدودیت"]))
async def cmd_lock_status_full(message: Message):
    chat_id = message.chat.id
    locks = cache.GROUP_LOCKS.get(chat_id) or await db_get_locks(chat_id)
    max_w = await db_get_max_warnings(chat_id)

    response = ">🛠 وضعیت قفل‌های گروه\n\n"
    active, inactive = [], []
    for key in LOCK_ORDER:
        name = LOCK_NAMES.get(key, key)
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


# ─── مالک گروه ───────────────────────────────────────────────────────────────

@router.message(F.text.in_(["مالک", "مالک فعلی", "مالک گروه", "owner", "مالک واقعی"]))
async def cmd_owner_info(message: Message, bot: Bot):
    chat_id = message.chat.id
    result = await sync_telegram_roles(chat_id, bot)

    if not result.get("ok"):
        return await _reply(message, f"❌ خطا در دریافت مالک گروه:\n{result.get('error', 'نامشخص')}")

    creator_id = result.get("creator_id")
    if not creator_id:
        return await _reply(
            message,
            "👑 مالک گروه\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "⚠️ creator گروه در تلگرام یافت نشد.\n\n"
            "📌 ربات را ادمین کامل کنید و «همگام‌سازی» بزنید.",
        )

    mention = await _mention(creator_id, bot, chat_id)
    tg_count = result.get("tg_admin_count", 0)
    return await _reply(
        message,
        "👑 مالک گروه\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"• {mention}\n"
        f"👥 ادمین تلگرام: {tg_count} نفر\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "انتقال مالک: از تنظیمات تلگرام\n"
        "به‌روزرسانی: «همگام‌سازی»",
    )


# ─── لیست ادمین با فرمت کامل ─────────────────────────────────────────────────

@router.message(F.text.in_([
    "لیست ادمین‌ها", "لیست ادمین", "لیست مدیران", "لیست مدیران گروه",
    "مدیران", "مدیر ها", "مدیرها",
    "ادمین ها", "ادمین‌ها", "ادمینها",
]))
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
            await bot.restrict_chat_member(chat_id, uid, permissions=full_permissions())
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
def _get_fee(chat_id):
    from account.models import TelegramGroup
    try:
        g = TelegramGroup.objects.get(telegram_chat_id=chat_id)
        return getattr(g, 'fee_percent', 10) if g.fee_percent is not None else 10
    except TelegramGroup.DoesNotExist:
        return 10
    except Exception:
        return 10

@sync_to_async
def _set_fee(chat_id, fee):
    from account.models import TelegramGroup
    g, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    g.fee_percent = fee
    g.save(update_fields=["fee_percent"])


def _tx_label(tx_type: str) -> tuple[str, str]:
    labels = {
        "admin_increase": ("➕ افزایش", "➕"),
        "admin_decrease": ("➖ کاهش", "➖"),
        "admin_clear": ("🧾 تسویه", "🧾"),
        "bet": ("🎲 شرط مسابقه", "🎲"),
        "win": ("🏆 برد در مسابقه", "🏆"),
    }
    return labels.get(tx_type, ("🔹 تراکنش", "🔹"))


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
    try:
        amount = int(parts[-1])
    except ValueError:
        return await _reply(message, "❗ مقدار افزایش عدد معتبر نیست.")
    new_balance = await increase_wallet(chat_id, target_id, amount, admin_id=user_id)
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
    try:
        amount = int(parts[-1])
    except ValueError:
        return await _reply(message, "❗ مقدار کاهش عدد معتبر نیست.")
    new_balance = await decrease_wallet(chat_id, target_id, amount, admin_id=user_id)
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


@router.message(F.text.regexp(r"^موجودی(\s|$)"))
async def cmd_balance(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) > 2:
        return await _reply(message, "❌ دستور نامعتبر است.")
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        target_id = user_id
    balance = await get_balance(chat_id, target_id)
    user_tag = await _mention(target_id, bot, chat_id)
    j_time_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
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


@router.message(F.text.startswith("تسویه"))
async def cmd_settle(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    if text in ("تسویه همه حساب ها", "تسویه تمام حساب ها", "تسویه حساب ها"):
        if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
            return
        results = await clear_all_wallets(chat_id, admin_id=user_id)
        if not results:
            return await _reply(message, "✅ همه حساب‌ها از قبل صفر بودند.")
        admin_tag = await _mention(user_id, bot, chat_id)
        lines = []
        total = 0
        for uid, cleared in results[:35]:
            tag = await _mention(uid, bot, chat_id)
            total += cleared
            if cleared < 0:
                lines.append(f"🔻 {tag} → {abs(cleared):,} واحد بدهکار تسویه شد")
            else:
                lines.append(f"✅ {tag} → {cleared:,} واحد تسویه شد")
        extra = f"\n… و {len(results) - 35} حساب دیگر" if len(results) > 35 else ""
        result_text = (
            "🧾 گزارش تسویه کامل حساب‌ها\n━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines) + extra
            + f"\n━━━━━━━━━━━━━━━━━━\n🛡 مدیر اجراکننده: {admin_tag}\n"
            f"🔢 تعداد تسویه‌شده: {len(results)}\n"
            f"💰 مجموع کل: {total:,} واحد اعتباری"
        )
        return await _reply(message, result_text)

    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return

    parts = text.split()

    if "کاربر" in text:
        number = next((int(p) for p in parts if p.isdigit()), None)
        if number is None:
            return await _reply(message, "❌ فرمت صحیح: `تسویه کاربر 1`")
        accounts = await get_active_accounts(chat_id)
        if not accounts:
            return await _reply(message, "📭 همه حساب‌ها صاف هستند!")
        if number < 1 or number > len(accounts):
            return await _reply(
                message,
                f"❌ شماره وارد شده نامعتبر است!\n\n"
                f"📊 تعداد حساب‌های فعال: {len(accounts)} عدد\n"
                f"🔢 شماره مجاز: ۱ تا {len(accounts)}\n\n"
                f"💡 برای مشاهده لیست: `حساب ها`",
            )
        target_id = accounts[number - 1]["telegram_user_id"]
        cleared = await clear_wallet(chat_id, target_id, admin_id=user_id)
        user_tag = await _mention(target_id, bot, chat_id)
        admin_tag = await _mention(user_id, bot, chat_id)
        return await _reply(
            message,
            f"🧾 تسویه حساب کاربر شماره {number}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 کاربر: {user_tag}\n"
            f"🛡 مدیر اجراکننده: {admin_tag}\n\n"
            f"💸 مبلغ تسویه شده: {cleared:,} واحد\n"
            f"📊 موجودی فعلی: 0 واحد\n"
            f"✅ حساب کاربر به طور کامل تسویه شد.",
        )

    if len(parts) >= 2 and parts[1].isdigit() and not message.reply_to_message:
        amount = int(parts[1])
        accounts = await get_active_accounts(chat_id)
        return await _reply(
            message,
            f"⚠️ روش صحیح کاهش موجودی\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"شما دستور `تسویه {amount}` را بدون ریپلای ارسال کردید.\n\n"
            f"📌 برای کاهش موجودی: روی پیام کاربر ریپلای کنید و `تسویه {amount}` بفرستید.\n"
            f"📌 برای تسویه کامل: روی پیام کاربر ریپلای کنید و `تسویه` بفرستید.\n"
            f"📌 برای تسویه از روی لیست: `تسویه کاربر 1`\n\n"
            f"📊 تعداد حساب‌های فعال: {len(accounts)} عدد",
        )

    if not message.reply_to_message:
        accounts = await get_active_accounts(chat_id)
        return await _reply(
            message,
            f"📖 راهنمای دستور تسویه\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔹 تسویه یک کاربر (با ریپلای): `تسویه`\n"
            f"🔹 کاهش مبلغ (با ریپلای): `تسویه 5000`\n"
            f"🔹 تسویه از لیست: `تسویه کاربر 1`\n"
            f"🔹 تسویه همه: `تسویه همه حساب ها`\n\n"
            f"📊 تعداد حساب‌های فعال: {len(accounts)} عدد",
        )

    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return

    if len(parts) >= 2 and parts[1].isdigit():
        amount = int(parts[1])
        new_balance = await decrease_wallet(chat_id, target_id, amount, admin_id=user_id)
        user_tag = await _mention(target_id, bot, chat_id)
        admin_tag = await _mention(user_id, bot, chat_id)
        return await _reply(
            message,
            "⚠️ عملیات کاهش موجودی انجام شد\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 کاربر: {user_tag}\n"
            f"🛡 مدیر اجراکننده: {admin_tag}\n\n"
            f"💳 مبلغ کسر شده: {amount:,} واحد\n"
            f"📊 موجودی فعلی: {new_balance:,} واحد",
        )

    cleared = await clear_wallet(chat_id, target_id, admin_id=user_id)
    user_tag = await _mention(target_id, bot, chat_id)
    admin_tag = await _mention(user_id, bot, chat_id)
    return await _reply(
        message,
        "🧾 عملیات تسویه حساب با موفقیت انجام شد\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 کاربر: {user_tag}\n"
        f"🛡 مدیر اجراکننده: {admin_tag}\n\n"
        f"💸 مبلغ تسویه شده: {cleared:,} واحد\n"
        f"📊 موجودی فعلی: 0 واحد\n"
        f"✅ حساب کاربر به طور کامل تسویه شد.",
    )


@router.message(F.text.func(lambda t: bool(t and (t.startswith("حساب ها") or t.startswith("حساب‌ها")))))
async def cmd_accounts(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    accounts = await get_active_accounts(chat_id)
    if not accounts:
        return await _reply(message, "✅ همه حساب‌ها صاف شده!")
    lines = []
    total_balance = 0
    limit = 34
    for idx, acc in enumerate(accounts[:limit], start=1):
        uid = acc["telegram_user_id"]
        balance = acc["point"] or 0
        total_balance += balance
        tag = await _mention(uid, bot, chat_id)
        if balance < 0:
            lines.append(f"{idx}. {tag} — 🔻 {abs(balance):,} واحد بدهکار")
        else:
            lines.append(f"{idx}. {tag} — {balance:,} واحد")
    if len(accounts) > limit:
        lines.append(f"… و {len(accounts) - limit} حساب دیگر")
    text = (
        "📒 لیست حساب‌های فعال گروه\n"
        "━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines)
        + "\n━━━━━━━━━━━━━━━━━━\n"
        f"💼 مجموع تراز گروه: {total_balance:,} واحد\n"
        f"🔢 تعداد حساب‌های تسویه نشده: {len(accounts)}"
    )
    return await _reply(message, text)


@router.message(F.text.regexp(r"^گزارش(\s+\d+)?$"))
async def cmd_report(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    parts = message.text.split()
    page = 1
    if len(parts) >= 2:
        try:
            page = max(1, int(parts[1]))
        except ValueError:
            page = 1
    limit = 5
    offset = (page - 1) * limit
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        target_id = user_id
    total_transactions = await get_transactions_count(chat_id, target_id)
    total_pages = (total_transactions + limit - 1) // limit if total_transactions > 0 else 1
    if page > total_pages and total_pages > 0:
        target_tag = await _mention(target_id, bot, chat_id)
        return await _reply(
            message,
            f"❌ صفحه مورد نظر یافت نشد!\n\n"
            f"👤 {target_tag}\n"
            f"📊 تعداد کل تراکنش‌ها: {total_transactions} عدد\n"
            f"📄 آخرین صفحه موجود: {total_pages}\n\n"
            f"💡 برای مشاهده صفحه آخر: `گزارش {total_pages}`",
        )
    transactions = await get_transactions(chat_id, target_id, limit, offset)
    if not transactions:
        return await _reply(message, "📭 گزارشی برای این کاربر ثبت نشده است.")
    target_tag = await _mention(target_id, bot, chat_id)
    current_balance = await get_balance(chat_id, target_id)
    text = (
        f"📊 گزارش مالی\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 {target_tag}\n"
        f"🆔 <code>{target_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📄 صفحه {page} از {total_pages}\n"
        f"💰 موجودی فعلی: {current_balance:,} واحد\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    for t in transactions:
        action, emoji = _tx_label(t.type)
        j_time_str = jdatetime.datetime.fromgregorian(datetime=t.created_at).strftime("%Y/%m/%d - %H:%M")
        text += f"{emoji} {action}\n"
        text += f"   💰 مبلغ: {t.amount:,} واحد\n"
        text += f"   📊 موجودی پس از تراکنش: {t.balance_after:,} واحد\n"
        if t.type in ("bet", "win"):
            text += "   🤖 عامل: ربات (سیستم خودکار)\n"
        elif t.admin_id:
            admin_tag = await _mention(t.admin_id, bot, chat_id)
            text += f"   👤 عامل: {admin_tag}\n"
        else:
            text += "   🤖 عامل: ربات (سیستم خودکار)\n"
        if t.description:
            text += f"   📝 توضیح: {t.description}\n"
        text += f"   🕒 {j_time_str}\n\n"
    if total_pages > 1:
        text += f"💡 صفحه بعد: `گزارش {page + 1}`" if page < total_pages else ""
    return await _reply(message, text)


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
            f"📌 تغییر نرخ:\n"
            f"   <code>حق واسطه 10</code>\n\n"
            f"✅ محدوده مجاز: ۰ تا ۵۰ درصد\n\n"
            f"ℹ️ پیش‌فرض گروه‌های جدید: ۱۰٪"
        )
        return await _reply(message, text)
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی ادمین برای این دستور را ندارید.")
    try:
        new_fee = int(parts[-1])
    except ValueError:
        return await _reply(message, "❌ مقدار باید یک عدد باشد.\nمثال: حق واسطه 10")
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
        text += (
            f"📊 نحوه محاسبه:\n"
            f"   • حالت فیکس (پیش‌فرض): ورودی ثابت، حق واسطه از جایزه\n"
            f"   • حالت اضافه: ورودی = شرط + حق واسطه\n\n"
        )
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
    parts = normalize_numbers(message.text).split()
    bet_mode = BET_MODE_FIXED
    if parts and parts[-1].lower() in _START_MODE_WORDS:
        bet_mode = _START_MODE_WORDS[parts[-1].lower()]
        parts = parts[:-1]
    if len(parts) < 2:
        return await _reply(message, (
            "❌ فرمت صحیح:\n"
            "• شروع [تعداد] → بازی رایگان\n"
            "• شروع [تعداد] [مبلغ] → ورودی ثابت (فیکس)\n"
            "• شروع [تعداد] [مبلغ] اضافه → ورودی = شرط + حق واسطه\n\n"
            "مثال‌ها:\n"
            "  شروع 2\n"
            "  شروع 2 50        → ورودی 50، برد = جمع − حق واسطه\n"
            "  شروع 2 50 اضافه  → ورودی 55، برد = 2×50"
        ))
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
            return await _reply(message, (
                "❌ مبلغ بازی باید عدد باشد!\n"
                "مثال: شروع 2 50  |  شروع 2 50 اضافه"
            ))
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
    create_game(
        chat_id, total_players,
        bet_amount=bet_amount, fee_percent=fee_percent,
        has_bet=has_bet, bet_mode=bet_mode if has_bet else BET_MODE_FIXED,
    )
    mode_label = _START_MODE_LABELS.get(bet_mode, bet_mode)
    if has_bet:
        costs = calc_bet_costs(bet_amount, fee_percent, bet_mode, total_players)
        _entry = costs["entry"]
        _fee_per = costs["fee_per"]
        _gross = costs["gross_prize"]
        _total_fee = costs["total_fee"]
        _prize = costs["winner_total"]
        msg = (
            f"🎲 رقابت تاس شروع شد!\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 ظرفیت: {total_players} نفر\n"
            f"📌 نوع: {mode_label}\n\n"
            f"💳 ورودی هر نفر: {_entry:,} واحد"
        )
        if bet_mode == BET_MODE_FIXED:
            if fee_percent > 0:
                msg += (
                    f"\n💰 جمع ورودی‌ها: {_gross:,} واحد"
                    f"\n💸 حق واسطه ({fee_percent}٪): {_total_fee:,} واحد (از جایزه)"
                    f"\n\n🏆 برد برنده: {_prize:,} واحد  ({_gross:,} − {_total_fee:,})"
                )
            else:
                msg += f"\n\n🏆 برد برنده: {_prize:,} واحد"
        else:
            if fee_percent > 0:
                msg += (
                    f"\n   ├ شرط: {bet_amount:,} واحد"
                    f"\n   └ حق واسطه ({fee_percent}٪): {_fee_per:,} واحد"
                )
            msg += f"\n\n🏆 برد برنده: {_prize:,} واحد  ({total_players} × {bet_amount:,})"
        msg += (
            f"\n✅ برای شرکت «تاس» بفرست\n\n"
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
        telegram_emoji_on=telegram_emoji_on(chat_id),
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

    # وقتی ایموجی تلگرام خاموشه، استیکرهای متحرک کاربر (غیر از بازی فعال) نادیده گرفته می‌شن
    if emoji == "🎲":
        game = get_game(chat_id)
        in_active_game = game and game.get("status") in ("waiting", "playing")
        if not telegram_emoji_on(chat_id) and not in_active_game:
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


# ─── خوشامدگویی ──────────────────────────────────────────────────────────────

async def _send_welcome(chat_id: int, user_id: int, name: str, bot: Bot):
    if chat_id in cache.WELCOME_DISABLED:
        return
    settings = cache.WELCOME_SETTINGS.get(chat_id, {})
    welcome_text = settings.get("text") or DEFAULT_WELCOME_TEXT
    gif_file_id = settings.get("gif_file_id") or DEFAULT_WELCOME_GIF_FILE_ID
    try:
        chat = await bot.get_chat(chat_id)
        group_name = chat.title or "گروه"
    except Exception:
        group_name = "گروه"
    mention = await user_mention(user_id, chat_id, fallback=name)
    text = (
        welcome_text
        .replace("{mention}", mention)
        .replace("{name}", mention)
        .replace("{id}", str(user_id))
        .replace("{group}", html.escape(group_name))
    )
    if gif_file_id:
        try:
            await bot.send_animation(chat_id, animation=gif_file_id, caption=text, parse_mode="HTML")
            return
        except Exception:
            pass
    from aiogram.types import FSInputFile
    photo = settings.get("photo_file_id") or FSInputFile(DEFAULT_WELCOME_PHOTO_PATH)
    try:
        await bot.send_photo(chat_id, photo=photo, caption=text, parse_mode="HTML")
    except Exception:
        await safe_send(bot, chat_id, text)


# ورود عضو از دو مسیر می‌رسه: پیام سرویس new_chat_members و آپدیت chat_member
# (وقتی ربات ادمین باشه). این دیکشنری جلوی پردازش دوباره رو می‌گیره.
_RECENT_JOINS: dict[tuple[int, int], float] = {}
_JOIN_DEDUP_WINDOW = 60  # ثانیه


def _mark_join_handled(chat_id: int, user_id: int) -> bool:
    """True یعنی اولین باره؛ False یعنی همین چند لحظه پیش هندل شده."""
    now = time.monotonic()
    for key, ts in list(_RECENT_JOINS.items()):
        if now - ts > _JOIN_DEDUP_WINDOW:
            _RECENT_JOINS.pop(key, None)
    if (chat_id, user_id) in _RECENT_JOINS:
        return False
    _RECENT_JOINS[(chat_id, user_id)] = now
    return True


async def _process_new_member(chat_id: int, member, bot: Bot):
    if member.is_bot:
        return
    user_id = member.id
    if not _mark_join_handled(chat_id, user_id):
        return

    name = member.first_name or member.username or str(user_id)
    await db_register_member(chat_id, user_id, name)

    if chat_id in cache.ANTIRAID_ENABLED:
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
        except Exception:
            pass
        await log_action(bot, chat_id,
            f"🚨 حالت ضد رید فعال است — {name} (<code>{user_id}</code>) به‌محض ورود اخراج شد")
        return

    if chat_id in cache.CAPTCHA_ENABLED:
        await _start_captcha(chat_id, user_id, name, bot)
        return

    await _send_welcome(chat_id, user_id, name, bot)


@router.message(F.new_chat_members)
async def handle_new_member(message: Message, bot: Bot):
    chat_id = message.chat.id
    if chat_id in cache.OFF_GROUP:
        return

    try:
        await message.delete()
    except Exception:
        pass

    for new_member in message.new_chat_members:
        await _process_new_member(chat_id, new_member, bot)


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def handle_chat_member_join(event: ChatMemberUpdated, bot: Bot):
    if event.chat.type not in ("group", "supergroup"):
        return
    chat_id = event.chat.id
    if chat_id in cache.OFF_GROUP:
        return
    await _process_new_member(chat_id, event.new_chat_member.user, bot)


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def handle_chat_member_leave(event: ChatMemberUpdated, bot: Bot):
    if event.chat.type not in ("group", "supergroup"):
        return
    await _cancel_pending_captcha(event.chat.id, event.new_chat_member.user.id, bot=bot)


@router.message(F.left_chat_member)
async def handle_left_member(message: Message, bot: Bot):
    if message.chat.id in cache.OFF_GROUP:
        return
    # پاکسازی پیام سرویس «کاربر گروه را ترک کرد»
    try:
        await message.delete()
    except Exception:
        pass
    member = message.left_chat_member
    if not member or member.is_bot:
        return
    await _cancel_pending_captcha(message.chat.id, member.id, bot=bot)


# ─── کپچا (تایید انسان بودن اعضای جدید) ──────────────────────────────────────

DEFAULT_CAPTCHA_TIMEOUT = 180  # ثانیه


async def _cancel_pending_captcha(
    chat_id: int, user_id: int, bot: Bot | None = None, delete_message: bool = True,
):
    pending = cache.PENDING_CAPTCHA.pop((chat_id, user_id), None)
    if not pending:
        return None
    pending["task"].cancel()
    if delete_message and bot:
        try:
            await bot.delete_message(chat_id, pending["message_id"])
        except Exception:
            pass
    return pending


async def _cancel_all_pending_captcha(chat_id: int, bot: Bot | None = None):
    for uid in [uid for (cid, uid) in cache.PENDING_CAPTCHA if cid == chat_id]:
        await _cancel_pending_captcha(chat_id, uid, bot=bot)


async def _start_captcha(chat_id: int, user_id: int, name: str, bot: Bot):
    await _cancel_pending_captcha(chat_id, user_id, bot=bot)

    restricted = False
    try:
        await bot.restrict_chat_member(
            chat_id, user_id,
            permissions=ChatPermissions(can_send_messages=False),
        )
        restricted = True
    except Exception:
        pass

    timeout = cache.CAPTCHA_TIMEOUT.get(chat_id, DEFAULT_CAPTCHA_TIMEOUT)
    minutes = max(1, timeout // 60)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        IKB(text="✅ من ربات نیستم", callback_data=f"captcha:{user_id}"),
    ]])
    text = (
        f"🔐 {name} عزیز، خوش اومدی!\n\n"
        f"• برای شروع گفتگو در گروه، ظرف {minutes} دقیقه دکمه‌ی زیر رو بزن\n"
        f"• در غیر این صورت از گروه حذف می‌شی"
    )
    if not restricted:
        text += "\n\n⚠️ ربات دسترسی محدودسازی نداره — لطفاً ربات رو ادمین کن."
    try:
        msg = await bot.send_message(chat_id, text, reply_markup=kb)
    except Exception:
        # پیام کپچا نرفت — کاربر رو محدود رها نکن
        if restricted:
            await unrestrict_user(bot, chat_id, user_id)
        return

    task = asyncio.create_task(_captcha_timeout(chat_id, user_id, msg.message_id, bot))
    cache.PENDING_CAPTCHA[(chat_id, user_id)] = {"message_id": msg.message_id, "task": task}
    await log_action(bot, chat_id,
        f"🔐 کپچا برای {name} (<code>{user_id}</code>) — مهلت {timeout} ثانیه")


async def _captcha_timeout(chat_id: int, user_id: int, message_id: int, bot: Bot):
    timeout = cache.CAPTCHA_TIMEOUT.get(chat_id, DEFAULT_CAPTCHA_TIMEOUT)
    try:
        await asyncio.sleep(timeout)
    except asyncio.CancelledError:
        return

    pending = cache.PENDING_CAPTCHA.pop((chat_id, user_id), None)
    if not pending:
        return  # قبلاً تایید شده

    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)
    except Exception:
        pass
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass
    await log_action(bot, chat_id,
        f"⏰ کپچا منقضی شد — کاربر <code>{user_id}</code> بابت عدم تایید اخراج شد")


@router.callback_query(F.data.startswith("captcha:"))
async def cb_captcha_verify(call: CallbackQuery, bot: Bot):
    try:
        target_id = int(call.data.split(":", 1)[1])
    except ValueError:
        await call.answer()
        return

    if call.from_user.id != target_id:
        await call.answer("❌ این دکمه برای شما نیست!", show_alert=True)
        return

    chat_id = call.message.chat.id
    pending = cache.PENDING_CAPTCHA.pop((chat_id, target_id), None)
    if pending:
        pending["task"].cancel()
    # اگه pending نبود (مثلاً بعد از ری‌استارت ربات)، باز هم کاربر رو آزاد می‌کنیم
    # وگرنه برای همیشه محدود می‌مونه.

    await unrestrict_user(bot, chat_id, target_id)
    try:
        await call.message.delete()
    except Exception:
        pass

    await call.answer("✅ تایید شد! خوش اومدی")
    name = call.from_user.first_name or call.from_user.username or str(target_id)
    await log_action(bot, chat_id,
        f"✅ کپچا تایید شد — {name} (<code>{target_id}</code>)")
    await _send_welcome(chat_id, target_id, name, bot)


@router.message(F.text.in_(["کپچا روشن", "کپچا فعال"]))
async def cmd_captcha_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.CAPTCHA_ENABLED.add(chat_id)
    await db_set_captcha(chat_id, enabled=True)
    timeout = cache.CAPTCHA_TIMEOUT.get(chat_id, DEFAULT_CAPTCHA_TIMEOUT)
    return await _reply(message,
        "✅ کپچا روشن شد.\n\n"
        f"• اعضای جدید باید ظرف {timeout // 60} دقیقه دکمه‌ی تایید رو بزنن\n"
        "• برای تغییر مهلت:  زمان کپچا [ثانیه]"
    )


@router.message(F.text.in_(["کپچا خاموش", "کپچا غیرفعال"]))
async def cmd_captcha_off(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.CAPTCHA_ENABLED.discard(chat_id)
    await db_set_captcha(chat_id, enabled=False)
    await _cancel_all_pending_captcha(chat_id, bot=bot)
    return await _reply(message, "❌ کپچا خاموش شد.")


@router.message(F.text.regexp(r"^زمان کپچا\s+(\d+)$"))
async def cmd_set_captcha_timeout(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    m = re.search(r"\d+", message.text)
    seconds = int(m.group())
    if not 30 <= seconds <= 1800:
        return await _reply(message, "❌ مهلت باید بین ۳۰ تا ۱۸۰۰ ثانیه باشد.")
    cache.CAPTCHA_TIMEOUT[chat_id] = seconds
    await db_set_captcha(chat_id, timeout=seconds)
    return await _reply(message, f"✅ مهلت کپچا روی {seconds} ثانیه تنظیم شد.")


@router.message(F.text.in_(["کپچا", "وضعیت کپچا"]))
async def cmd_captcha_status(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    enabled = chat_id in cache.CAPTCHA_ENABLED
    timeout = cache.CAPTCHA_TIMEOUT.get(chat_id, DEFAULT_CAPTCHA_TIMEOUT)
    return await _reply(message,
        f"🔐 وضعیت کپچا\n\n"
        f"• وضعیت: {'✅ روشن' if enabled else '❌ خاموش'}\n"
        f"• مهلت: {timeout} ثانیه"
    )


# ─── حالت ضد رید ──────────────────────────────────────────────────────────────

@router.message(F.text.in_(["ضد رید روشن", "حالت ضد رید روشن"]))
async def cmd_antiraid_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.ANTIRAID_ENABLED.add(chat_id)
    await db_set_antiraid(chat_id, True)
    return await _reply(message,
        "🚨 حالت ضد رید فعال شد.\n\n"
        "• از این لحظه هر عضو جدیدی وارد بشه، بلافاصله اخراج می‌شه\n"
        "• بعد از رفع خطر، حتماً با «ضد رید خاموش» غیرفعالش کن"
    )


@router.message(F.text.in_(["ضد رید خاموش", "حالت ضد رید خاموش"]))
async def cmd_antiraid_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.ANTIRAID_ENABLED.discard(chat_id)
    await db_set_antiraid(chat_id, False)
    return await _reply(message, "✅ حالت ضد رید غیرفعال شد.")


@router.message(F.text.in_(["ضد رید", "وضعیت ضد رید"]))
async def cmd_antiraid_status(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    enabled = chat_id in cache.ANTIRAID_ENABLED
    return await _reply(message, f"🚨 وضعیت ضد رید: {'✅ روشن' if enabled else '❌ خاموش'}")


# ─── کانال لاگ ────────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^تنظیم کانال لاگ\s+(-?\d+)$"))
async def cmd_set_log_channel(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط مالک می‌تواند کانال لاگ را تنظیم کند.")
    m = re.search(r"-?\d+", message.text)
    log_chat_id = int(m.group())
    try:
        await bot.send_message(
            log_chat_id,
            f"✅ این کانال به‌عنوان کانال لاگ گروه «{message.chat.title or chat_id}» تنظیم شد."
        )
    except Exception as e:
        return await _reply(message,
            f"❌ خطا در دسترسی به کانال:\n{e}\n\n"
            "مطمئن شو ربات در کانال ادمین است و شناسه رو درست وارد کردی."
        )
    cache.LOG_CHANNEL[chat_id] = log_chat_id
    await db_set_log_channel(chat_id, log_chat_id)
    return await _reply(message, "✅ کانال لاگ با موفقیت تنظیم شد.")


@router.message(F.text.in_(["حذف کانال لاگ", "غیرفعال کردن کانال لاگ"]))
async def cmd_del_log_channel(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return
    cache.LOG_CHANNEL.pop(chat_id, None)
    await db_set_log_channel(chat_id, None)
    return await _reply(message, "✅ کانال لاگ حذف شد.")


@router.message(F.text.in_(["کانال لاگ", "وضعیت کانال لاگ"]))
async def cmd_log_channel_status(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    log_id = cache.LOG_CHANNEL.get(chat_id)
    if log_id:
        return await _reply(message, f"📋 کانال لاگ تنظیم‌شده:\n<code>{log_id}</code>")
    return await _reply(message,
        "📋 کانال لاگی تنظیم نشده.\n\n"
        "• ربات رو به یک کانال، ادمین کن\n"
        "• شناسه عددی کانال رو بفرست:\n"
        "  تنظیم کانال لاگ -1001234567890"
    )


# ─── یادداشت‌ها (Notes) ───────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^ذخیره یادداشت\s+(\S+)\s+([\s\S]+)$"))
async def cmd_save_note(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    m = re.match(r"^ذخیره یادداشت\s+(\S+)\s+([\s\S]+)$", message.text)
    name, content = m.group(1), m.group(2).strip()
    if len(name) > 100:
        return await _reply(message, "❌ نام یادداشت خیلی طولانیه.")
    await db_save_note(chat_id, name, content, user_id)
    return await _reply(message, f"✅ یادداشت «{name}» ذخیره شد.\n\nبرای دیدنش بنویس:  #{name}")


@router.message(F.text.regexp(r"^حذف یادداشت\s+(\S+)$"))
async def cmd_delete_note(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    m = re.match(r"^حذف یادداشت\s+(\S+)$", message.text)
    name = m.group(1)
    deleted = await db_delete_note(chat_id, name)
    if deleted:
        return await _reply(message, f"🗑 یادداشت «{name}» حذف شد.")
    return await _reply(message, f"❌ یادداشتی با نام «{name}» پیدا نشد.")


@router.message(F.text.in_(["لیست یادداشت", "لیست یادداشت‌ها", "یادداشت ها"]))
async def cmd_list_notes(message: Message):
    chat_id = message.chat.id
    names = await db_list_notes(chat_id)
    if not names:
        return await _reply(message, "📝 هنوز یادداشتی ذخیره نشده.\n\nبرای ذخیره:  ذخیره یادداشت [نام] [متن]")
    lines = "\n".join(f"  • #{n}" for n in names)
    return await _reply(message, f"📝 یادداشت‌های این گروه:\n\n{lines}")


@router.message(F.text.regexp(r"^#(\S+)$"))
async def cmd_get_note(message: Message):
    m = re.match(r"^#(\S+)$", message.text)
    name = m.group(1)
    content = await db_get_note(message.chat.id, name)
    if content is None:
        # این پیام یک یادداشت واقعی نیست (هشتگ معمولیه) — بذار بقیه‌ی
        # فیلترها (قفل‌ها، فیلتر کلمه، یادگیری) هم روش اجرا بشن.
        skip()
    return await _reply(message, content)


# ─── گزارش به ادمین (Report) ──────────────────────────────────────────────────

@router.message(F.text.func(lambda t: t is not None and t.strip() in
                            ("ریپورت", "گزارش تخلف", "گزارش به ادمین", "@admin", "@admins")))
async def cmd_report_to_admins(message: Message, bot: Bot):
    chat_id = message.chat.id
    if not message.reply_to_message:
        return await _reply(message, "⚠️ روی پیام مورد نظر ریپلای کن و «ریپورت» رو بفرست.")

    reporter_id = message.from_user.id
    if is_admin(chat_id, reporter_id) or is_owner(chat_id, reporter_id):
        return

    reported_user = message.reply_to_message.from_user
    if reported_user and (is_admin(chat_id, reported_user.id) or is_owner(chat_id, reported_user.id)):
        return await _reply(message, "❌ نمی‌تونی ادمین‌ها رو گزارش کنی.")

    admin_ids = set(cache.ADMINS_CACHE.get(chat_id, set()))
    owner_id = cache.OWNER_CACHE.get(chat_id)
    if owner_id:
        admin_ids.add(owner_id)
    if not admin_ids:
        return await _reply(message, "❌ ادمینی برای این گروه ثبت نشده.")

    mentions = " ".join(f'<a href="tg://user?id={aid}">‏</a>' for aid in admin_ids)
    reporter_mention = await _mention(reporter_id, bot, chat_id)
    reported_mention = (
        await _mention(reported_user.id, bot, chat_id) if reported_user else "کاربر"
    )
    text = (
        "🚨 گزارش تخلف\n\n"
        f"👤 گزارش‌دهنده: {reporter_mention}\n"
        f"⚠️ گزارش‌شده: {reported_mention}\n\n"
        f"{mentions}"
    )
    await bot.send_message(
        chat_id, text,
        reply_to_message_id=message.reply_to_message.message_id,
        parse_mode="HTML",
    )


# ─── پاکسازی پیام‌ها (Purge) ──────────────────────────────────────────────────

@router.message(F.text.regexp(r"^پاکسازی\s+(\d+)$"))
async def cmd_purge_last_n(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return

    try:
        count = int(message.text.split()[1])
    except Exception:
        return await _reply(message, "❌ فرمت نادرست است. مثال: <code>پاکسازی 100</code>")

    if count < 1:
        return await _reply(message, "❌ عدد باید حداقل ۱ باشد.")
    if count > 300:
        return await _reply(message, "❌ حداکثر در هر بار ۳۰۰ پیام قابل پاکسازی است.")

    # فرمان پاکسازی هم جزو حذف‌شده‌ها حساب می‌شود.
    start_id = max(1, message.message_id - count + 1)
    end_id = message.message_id

    deleted = 0
    for mid in range(end_id, start_id - 1, -1):
        try:
            await bot.delete_message(chat_id, mid)
            deleted += 1
        except Exception:
            pass

    status_msg = await bot.send_message(chat_id, f"🧹 {deleted} پیام از آخرین پیام‌ها پاکسازی شد.")
    await log_action(bot, chat_id, f"🧹 پاکسازی عددی: {deleted} پیام توسط ادمین انجام شد")
    await asyncio.sleep(3)
    try:
        await status_msg.delete()
    except Exception:
        pass


@router.message(F.text.in_(["پاکسازی", "پاکسازی پیام", "پاکسازی پیام‌ها"]))
async def cmd_purge(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not message.reply_to_message:
        return await _reply(message, "⚠️ روی پیامی که می‌خوای پاکسازی از اونجا شروع بشه ریپلای کن.")

    start_id = message.reply_to_message.message_id
    end_id = message.message_id
    if end_id <= start_id:
        return await _reply(message, "❌ پیام ریپلای‌شده باید قبل از این پیام باشه.")

    count = end_id - start_id + 1
    if count > 200:
        return await _reply(message, "❌ حداکثر ۲۰۰ پیام رو یک‌جا می‌تونی پاک کنی.")

    deleted = 0
    for mid in range(start_id, end_id + 1):
        try:
            await bot.delete_message(chat_id, mid)
            deleted += 1
        except Exception:
            pass

    status_msg = await bot.send_message(chat_id, f"🧹 {deleted} پیام پاکسازی شد.")
    await log_action(bot, chat_id, f"🧹 پاکسازی: {deleted} پیام توسط <code>{user_id}</code> حذف شد")
    await asyncio.sleep(3)
    try:
        await status_msg.delete()
    except Exception:
        pass


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
        "متغیرها: {mention} = منشن عضو، {group} = نام گروه"
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
        "💡 متغیرها: {mention} = منشن عضو، {group} = نام گروه"
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


# ─── ایموجی متحرک تلگرام (بازی‌ها) ───────────────────────────────────────────

@router.message(F.text.in_(["ایموجی تلگرام روشن", "ایموجی تلگرامی روشن"]))
async def cmd_tg_emoji_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    await db_set_telegram_emoji(chat_id, True)
    return await _reply(message,
        "✅ ایموجی تلگرام روشن شد.\n\n"
        "بازی‌ها (بسکتبال، پنالتی، تاس و...) با استیکر متحرک تلگرام اجرا می‌شن.\n"
        "برای برگشت به حالت متنی:  ایموجی تلگرام خاموش"
    )


@router.message(F.text.in_(["ایموجی تلگرام خاموش", "ایموجی تلگرامی خاموش"]))
async def cmd_tg_emoji_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    await db_set_telegram_emoji(chat_id, False)
    return await _reply(message,
        "❌ ایموجی تلگرام خاموش شد.\n\n"
        "بازی‌ها دوباره به‌صورت متنی (مثل حالت پیش‌فرض) اجرا می‌شن."
    )


@router.message(F.text.in_(["ایموجی تلگرام", "وضعیت ایموجی تلگرام"]))
async def cmd_tg_emoji_status(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    on = telegram_emoji_on(chat_id)
    return await _reply(message,
        f"🎮 حالت ایموجی تلگرام: {'✅ روشن (استیکر متحرک)' if on else '❌ خاموش (متنی)'}\n\n"
        "دستورات:\n"
        "  ایموجی تلگرام روشن\n"
        "  ایموجی تلگرام خاموش"
    )


# ─── حذف پیام با ریپلای ───────────────────────────────────────────────────────

@router.message(F.text.in_(["حذف", "حذف پیام", "دل"]))
async def cmd_delete_message(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not message.reply_to_message:
        return await _reply(message, "⚠️ روی پیامی که می‌خوای حذف بشه ریپلای کن.")
    try:
        await message.reply_to_message.delete()
    except Exception:
        return await _reply(message, "❌ نتونستم پیام رو حذف کنم — دسترسی حذف پیام رو بررسی کن.")
    try:
        await message.delete()
    except Exception:
        pass


# ─── سنجاق (پین) ─────────────────────────────────────────────────────────────

@router.message(F.text.in_(["سنجاق", "پین", "سنجاق پیام"]))
async def cmd_pin(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not message.reply_to_message:
        return await _reply(message, "⚠️ روی پیامی که می‌خوای سنجاق بشه ریپلای کن.")
    try:
        await bot.pin_chat_message(chat_id, message.reply_to_message.message_id,
                                   disable_notification=True)
        return await _reply(message, "📌 پیام سنجاق شد.")
    except Exception as e:
        return await _reply(message, f"❌ خطا در سنجاق کردن:\n{e}")


@router.message(F.text.in_(["حذف سنجاق", "آنپین", "برداشتن سنجاق"]))
async def cmd_unpin(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    try:
        if message.reply_to_message:
            await bot.unpin_chat_message(chat_id, message.reply_to_message.message_id)
        else:
            await bot.unpin_chat_message(chat_id)
        return await _reply(message, "📌 سنجاق برداشته شد.")
    except Exception as e:
        return await _reply(message, f"❌ خطا:\n{e}")


# ─── قوانین گروه ─────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^(تنظیم قوانین|ثبت قوانین)\s+([\s\S]+)$"))
async def cmd_set_rules(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    text = re.sub(r"^(تنظیم قوانین|ثبت قوانین)\s+", "", message.text).strip()
    if len(text) > 3500:
        return await _reply(message, "❌ متن قوانین خیلی طولانیه (حداکثر ۳۵۰۰ کاراکتر).")
    await db_set_rules(chat_id, text)
    return await _reply(message, "✅ قوانین گروه ثبت شد.\n\nاعضا با دستور «قوانین» می‌تونن ببیننش.")


@router.message(F.text.in_(["قوانین", "قوانین گروه", "rules"]))
async def cmd_show_rules(message: Message):
    rules = await db_get_rules(message.chat.id)
    if not rules:
        return await _reply(message,
            "📜 هنوز قوانینی برای این گروه ثبت نشده.\n\n"
            "ادمین‌ها می‌تونن با دستور زیر ثبت کنن:\n"
            "تنظیم قوانین [متن]")
    return await _reply(message, f"📜 قوانین گروه\n━━━━━━━━━━━━━━━━\n\n{rules}")


@router.message(F.text.in_(["حذف قوانین", "پاک کردن قوانین"]))
async def cmd_del_rules(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    await db_set_rules(chat_id, None)
    return await _reply(message, "🗑 قوانین گروه حذف شد.")


# ─── حالت شب ─────────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^حالت شب روشن(\s+\d{1,2}\s+\d{1,2})?$"))
async def cmd_night_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    nums = re.findall(r"\d{1,2}", message.text)
    start, end = (int(nums[0]), int(nums[1])) if len(nums) == 2 else (0, 8)
    if not (0 <= start <= 23 and 0 <= end <= 23):
        return await _reply(message, "❌ ساعت باید بین ۰ تا ۲۳ باشد.")
    if start == end:
        return await _reply(message, "❌ ساعت شروع و پایان نمی‌تونن یکی باشن.")
    cache.NIGHT_MODE[chat_id] = (start, end)
    await db_set_night_mode(chat_id, True, start, end)
    return await _reply(message,
        f"🌙 حالت شب روشن شد.\n\n"
        f"• از ساعت {start}:00 تا {end}:00 فقط ادمین‌ها می‌تونن پیام بدن\n"
        f"• پیام بقیه به‌صورت خودکار حذف می‌شه\n\n"
        f"برای تغییر بازه:  حالت شب روشن [شروع] [پایان]")


@router.message(F.text == "حالت شب خاموش")
async def cmd_night_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cache.NIGHT_MODE.pop(chat_id, None)
    await db_set_night_mode(chat_id, False)
    return await _reply(message, "🌤 حالت شب خاموش شد.")


@router.message(F.text.in_(["حالت شب", "وضعیت حالت شب"]))
async def cmd_night_status(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cfg = cache.NIGHT_MODE.get(chat_id)
    if cfg:
        return await _reply(message,
            f"🌙 حالت شب: ✅ روشن\n\n"
            f"• بازه: {cfg[0]}:00 تا {cfg[1]}:00\n"
            f"• الان {'در بازه‌ی حالت شب هستیم' if is_night_time(chat_id) else 'خارج از بازه‌ایم'}")
    return await _reply(message,
        "🌙 حالت شب: ❌ خاموش\n\n"
        "برای روشن کردن:  حالت شب روشن [شروع] [پایان]\n"
        "مثال:  حالت شب روشن 23 7")


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
