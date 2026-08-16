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
from aiogram.types import (
    Message, ChatPermissions, CallbackQuery, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton as IKB,
)
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.dispatcher.event.bases import skip
from asgiref.sync import sync_to_async

from bot import cache
from bot.cache_manager import is_owner, is_admin, is_vip, has_privilege
from bot.helpers import (
    safe_send, get_target_from_reply, user_mention, user_mention_id,
    get_user_status,
    db_set_group_theme, db_get_group_theme, get_group_theme,
    db_enable_group_off, db_disable_group_off,
    db_enable_group_lock, db_disable_group_lock,
    db_enable_dice_option, db_disable_dice_option,
    db_enable_quiet_extra, db_disable_quiet_extra, quiet_extra_on,
    db_get_dice_turn_limit, db_set_dice_turn_limit,
    db_enable_speaker, db_disable_speaker,
    db_update_lock, db_get_locks,
    db_set_owner,
    sync_telegram_roles, sync_bot_admins_from_telegram,
    db_add_admin, db_del_admin,
    db_add_vip, db_del_vip,
    db_get_admins, db_get_vips, db_clear_vips,
    db_add_warning, db_reset_warnings, db_get_warnings, db_get_max_warnings, db_set_max_warnings,
    get_max_warnings, get_group_commands,
    db_get_group_commands, db_set_group_commands,
    db_add_word_filter, db_remove_word_filter, db_get_word_filters,
    db_save_learned_response, db_delete_learned_response, db_get_learned_responses,
    db_get_top_users, db_get_member, db_register_member,
    db_set_alias, db_get_alias,
    db_get_all_members_balance, db_update_point, db_get_point, db_get_group_fee,
    db_ban_user, db_unban_user, db_mute_user, db_unmute_user,
    db_get_dice_stats, db_record_dice_roll,
    db_fetch_dice_game_history,
    db_fetch_user_dice_game_history,
    db_update_card, db_get_card, db_delete_card,
    LOCK_MAP, LOCK_NAMES, LOCK_ORDER,
    db_set_welcome, db_set_anti_flood,
    db_set_captcha, db_set_antiraid, db_set_log_channel, log_action,
    full_permissions, unrestrict_user,
    db_save_note, db_get_note, db_delete_note, db_list_notes,
    db_set_rules, db_get_rules, db_set_night_mode, is_night_time,
    db_set_telegram_emoji, telegram_emoji_on,
    deliver_private_or_warn, send_private, deliver_balance_sensitive,
    parse_balance_command,
    parse_unban_target, resolve_unban_target_id,
)
from bot.utils import normalize_numbers, safe_calc as utils_safe_calc, is_pure_calc_expr
from bot.finance import (
    get_balance, increase_wallet, decrease_wallet, clear_wallet, transfer_wallet,
    get_transfer_enabled, set_transfer_enabled,
    get_active_accounts, get_transactions, get_transactions_count,
    clear_all_wallets,
    is_balance_hidden,
)
from bot.fee_reports import (
    fee_report_kb, send_fee_report, build_fee_text_by_mode,
    build_fee_admin_text, ADMIN_DENY_TEXT, parse_fee_report_command,
)
from bot.hidden_increase import (
    parse_increase_command, start_increase_pv_flow, start_increase_request_flow, TIP_DIRECT,
    INCREASE_COMMAND_RE, SETTLE_COMMAND_RE, MEMBER_INCREASE_TEXTS, MEMBER_SETTLE_TEXTS,
)
from bot.tx_reports import tx_report_kb, build_tx_report_text, parse_report_command, send_tx_report_pm
from bot.accounts_panel import (
    build_accounts_pm_payload, handle_accounts_callback, parse_accounts_command,
    deliver_accounts_pm, GROUP_LIST_PER_PAGE,
)
from bot.admin_accounting import (
    report as admin_accounting_report,
    render as render_admin_accounting,
    start_activity,
    end_activity,
    active_cashier,
    list_activity_sessions,
    list_activity_day_keys,
    render_activities_list,
    activities_keyboard,
    report_keyboard,
    remember_context,
    handle_report_callback,
)
from bot.group_help import get_page, PAGE_MAIN
from bot.panel_keyboards import get_panel, panel_main, panel_home_text, locks_panel_text, locks_panel_kb, ALL_TOGGLEABLE_CMDS
from bot.constants import (
    DEFAULT_WELCOME_TEXT, DEFAULT_WELCOME_GIF_FILE_ID, DEFAULT_WELCOME_PHOTO_PATH,
)
from bot.dice_game import (
    has_active_game, get_game, create_game, delete_game, finish_game_cleanup,
    handle_dice, handle_round_selection, WAITING_ROUNDS, ACTIVE_GAMES as DICE_ACTIVE_GAMES,
    is_user_in_game, can_player_roll, claim_roll_slots, save_roll_result, register_and_save_dice,
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


@router.message(F.text.regexp(r"^حساب ادمین( ها|‌ها)?( امروز| دیروز| پریروز| هفتگی)?$"))
async def cmd_admin_accounts(message: Message, bot: Bot):
    chat_id, uid = message.chat.id, message.from_user.id
    if not is_owner(chat_id, uid):
        return await _reply(message, "❌ این دستور فقط برای مالک گپ است.")
    tail = message.text.replace("حساب ادمین ها", "").replace("حساب ادمین‌ها", "").strip()
    mode = {"": "0", "امروز": "0", "دیروز": "1", "پریروز": "2", "هفتگی": "w"}.get(tail, "0")
    rows = await admin_accounting_report(chat_id, mode)
    remember_context(chat_id, uid)
    keyboard = report_keyboard(chat_id, rows, mode)
    await bot.send_message(uid, render_admin_accounting(rows, mode), parse_mode="HTML", reply_markup=keyboard)
    return await _reply(message, "✅ گزارش کامل در پی‌وی شما ارسال شد.")


@router.message(F.text.regexp(r"^فعالیت\s*(?:ها|‌ها)?$"))
async def cmd_admin_activities(message: Message, bot: Bot):
    chat_id, uid = message.chat.id, message.from_user.id
    if not is_owner(chat_id, uid):
        return await _reply(message, "❌ این دستور فقط برای مالک گپ است.")
    sessions = await list_activity_sessions(chat_id)
    day_keys = await list_activity_day_keys(chat_id)
    remember_context(chat_id, uid)
    await bot.send_message(
        uid,
        render_activities_list(sessions, day_keys),
        parse_mode="HTML",
        reply_markup=activities_keyboard(chat_id, sessions, day_keys=day_keys),
    )
    return await _reply(message, "✅ لیست بازه‌های فعالیت در پی‌وی شما ارسال شد.")


@router.callback_query(F.data.startswith("aareport:"))
async def cb_admin_accounts(call: CallbackQuery, bot: Bot):
    try:
        chat_id = int(call.data.split(":")[1])
        if not is_owner(chat_id, call.from_user.id):
            return await call.answer("فقط مالک گروه دسترسی دارد.", show_alert=True)
        handled = await handle_report_callback(call, bot)
        if not handled:
            await call.answer("گزارش قابل نمایش نیست.", show_alert=True)
    except Exception:
        await call.answer("گزارش قابل نمایش نیست؛ دوباره تلاش کنید.", show_alert=True)


@router.message(F.text == "شروع فعالیت")
async def cmd_start_admin_activity(message: Message, bot: Bot):
    chat_id, uid = message.chat.id, message.from_user.id
    if not (is_owner(chat_id, uid) or is_admin(chat_id, uid)):
        return await _reply(message, "❌ فقط مالک و ادمین‌ها می‌توانند فعالیت را شروع کنند.")
    from bot.admin_accounting import start_activity, format_start_activity_group, deliver_closed_session_pm
    result = await start_activity(chat_id, uid)
    if not result.get("already_active"):
        await deliver_closed_session_pm(bot, chat_id, result.get("closed_session"))
    return await _reply(message, format_start_activity_group(result))


@router.message(F.text.in_(["فعالیت تاکنون", "فعالیت تا کنون"]))
async def cmd_activity_so_far(message: Message, bot: Bot):
    chat_id, uid = message.chat.id, message.from_user.id
    if not (is_owner(chat_id, uid) or is_admin(chat_id, uid)):
        return await _reply(message, ADMIN_DENY_TEXT)
    from bot.admin_accounting import (
        get_active_session_live,
        deliver_active_session_pm,
        format_activity_so_far_group,
    )
    session = await get_active_session_live(chat_id)
    if not session:
        return await _reply(message, "ℹ️ فعالیت فعالی وجود ندارد.")
    await deliver_active_session_pm(bot, chat_id, session)
    return await _reply(message, format_activity_so_far_group(session))


@router.message(F.text == "پایان فعالیت")
async def cmd_end_admin_activity(message: Message, bot: Bot):
    chat_id, uid = message.chat.id, message.from_user.id
    if not (is_owner(chat_id, uid) or is_admin(chat_id, uid)):
        return await _reply(message, "❌ فقط مالک و ادمین‌ها می‌توانند فعالیت را پایان دهند.")
    from bot.admin_accounting import end_activity, format_end_activity_group, deliver_closed_session_pm
    result = await end_activity(chat_id)
    await deliver_closed_session_pm(bot, chat_id, result.get("closed_session"))
    return await _reply(message, format_end_activity_group(result))


@router.message(F.text.regexp(r"^سهم ادمین\s+\d+\s+\d+$"))
async def cmd_set_admin_share(message: Message):
    chat_id, uid = message.chat.id, message.from_user.id
    if not is_owner(chat_id, uid):
        return await _reply(message, "❌ فقط مالک می‌تواند سهم ادمین را تغییر دهد.")
    parts = message.text.split()
    from bot.admin_accounting import set_share
    percent = await set_share(chat_id, parts[2], parts[3])
    return await _reply(message, f"✅ سهم ادمین روی {percent}٪ تنظیم شد.")
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# ─── دستورات ویژه سازنده ─────────────────────────────────────────────────────

CREATOR_USER_ID = 8810788620
CREATOR_USER_IDS = frozenset({CREATOR_USER_ID})


def _is_creator(user_id: int) -> bool:
    return int(user_id) in CREATOR_USER_IDS

# دستورات سرگرمی/بازی — لیست کامل در panel_keyboards.ALL_TOGGLEABLE_CMDS

# ─── helpers داخلی ───────────────────────────────────────────────────────────

async def _reply(message: Message, text: str, *, silent: int = 0, force: bool = False):
    # در حالت سایلنت پیام موفقیت مخفی است؛ خطا (force) همیشه نشان داده شود
    if silent >= 1 and not force:
        return
    await safe_send(message.bot, message.chat.id, text, reply_to=message.message_id)


async def _finish_silent(message: Message, silent: int):
    if silent < 1:
        return
    from bot.silent_cmd import apply_silent_deletes
    reply_id = message.reply_to_message.message_id if message.reply_to_message else None
    await apply_silent_deletes(
        message.bot, message.chat.id, message.message_id, reply_id, silent,
    )


def _silent_of(message: Message) -> tuple[str, int]:
    from bot.silent_cmd import apply_silent_suffix
    return apply_silent_suffix(message.text or "")


async def _mention(user_id: int, bot: Bot, chat_id: int) -> str:
    return await user_mention_id(user_id, bot, chat_id)


def _mention_from_reply(message: Message, user_id: int) -> str:
    """منشن از خود ریپلای — بدون get_chat_member (بعد از کیک API شکست می‌خورد)."""
    r = getattr(message, "reply_to_message", None)
    u = getattr(r, "from_user", None) if r else None
    if u is not None and u.id == user_id:
        name = u.full_name or str(user_id)
    else:
        name = str(user_id)
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


# fee report helpers → bot.fee_reports


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
    from bot.dice_themes import theme_exists, max_theme_id
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط ادمین‌ها می‌توانند تم را تغییر دهند.")
    m = re.search(r"\d+", message.text)
    if not m:
        return
    theme = int(m.group())
    if not theme_exists(theme):
        return await _reply(
            message,
            f"❌ تم {theme} وجود ندارد. تم‌های موجود تا شماره {max_theme_id()}",
        )
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
    group_cmds = get_group_commands(chat_id)
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
    group_cmds = get_group_commands(chat_id)
    disabled = [c for c in ALL_TOGGLEABLE_CMDS if c not in group_cmds]
    if not disabled:
        return await _reply(message, "✅ هیچ دستوری خاموش نیست.")
    txt = "🚫 دستورات خاموش این گروه:\n\n" + "\n".join(f"• {c}" for c in disabled)
    return await _reply(message, txt)


# تاس متوالی — هندلر اصلی پایین‌تر (cmd_dice_option_on / cmd_dice_option_off)


# ─── قفل‌ها ───────────────────────────────────────────────────────────────────

_LOCK_ON_WORDS = {"روشن", "فعال", "فعالسازی", "فعال‌سازی", "enable", "on"}
_LOCK_OFF_WORDS = {"خاموش", "غیرفعال", "غیر فعال", "غیرفعالسازی", "غیرفعال‌سازی", "disable", "off"}

_GAME_CHAT_LOCK_ON = {
    "قفل بازی", "قفل بازی فعال", "قفل بازی روشن",
    "فعال قفل بازی", "روشن قفل بازی",
}
_GAME_CHAT_LOCK_OFF = {
    "قفل بازی خاموش", "قفل بازی غیرفعال",
    "خاموش قفل بازی", "غیرفعال قفل بازی", "بازکردن قفل بازی", "باز کردن قفل بازی",
}


@router.message(F.text.in_(_GAME_CHAT_LOCK_ON))
async def cmd_game_chat_lock_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    from bot.helpers import (
        game_chat_lock_on, db_enable_game_chat_lock, game_chat_lock_enabled_text,
    )
    if game_chat_lock_on(chat_id):
        return await _reply(message, "🔒 قفل بازی از قبل فعال است.")
    await db_enable_game_chat_lock(chat_id)
    return await _reply(message, game_chat_lock_enabled_text())


@router.message(F.text.in_(_GAME_CHAT_LOCK_OFF))
async def cmd_game_chat_lock_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    from bot.helpers import game_chat_lock_on, db_disable_game_chat_lock
    if not game_chat_lock_on(chat_id):
        return await _reply(message, "🔓 قفل بازی از قبل خاموش است.")
    await db_disable_game_chat_lock(chat_id)
    return await _reply(
        message,
        "🔓 قفل بازی خاموش شد.\n"
        "ارسال پیام عادی در گروه دوباره آزاد است.",
    )


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
        skip()
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
        skip()
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


@router.message(F.text.regexp(r"^حذف ویژه[\s.….۔]*$"))
async def cmd_del_vip(message: Message, bot: Bot):
    clean, silent = _silent_of(message)
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی مجاز را ندارید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    await db_del_vip(chat_id, target_id)
    mention = await _mention(target_id, bot, chat_id)
    await _reply(message, f"✅ {mention}\n\n›› از اعضای ویژه حذف شد.", silent=silent)
    await _finish_silent(message, silent)


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
        mention = _mention_from_reply(message, target_id)
        await _reply(message, f"› {mention}\n\n›› در حال حاضر {rank} است!")
        return None
    return target_id


@router.message(F.text.regexp(r"^بن[\s.….۔]*$"))
async def cmd_ban(message: Message, bot: Bot):
    """بن دائمی — بن / بن. / بن .. / بن ..."""
    silent = _silent_of(message)[1]
    chat_id = message.chat.id
    target_id = await _check_ban_target(message, bot)
    if not target_id:
        return
    try:
        await bot.ban_chat_member(chat_id, target_id)
        await db_ban_user(chat_id, target_id)
    except Exception as e:
        return await _reply(message, f"❌ خطا در بن کردن: {html.escape(str(e))}", force=True)
    asyncio.create_task(
        log_action(bot, chat_id, f"🚫 بن — <code>{target_id}</code> توسط <code>{message.from_user.id}</code>")
    )
    if silent:
        await _finish_silent(message, silent)
        return
    mention = _mention_from_reply(message, target_id)
    await _reply(message, f"🚫 {mention}\n\n›› از گروه اخراج و بن شد.", silent=silent)


@router.message(F.text.regexp(r"^بن\s+(\d+)[\s.….۔]*$"))
async def cmd_ban_timed(message: Message, bot: Bot):
    """بن موقت — بن [دقیقه]"""
    clean, silent = _silent_of(message)
    chat_id = message.chat.id
    target_id = await _check_ban_target(message, bot)
    if not target_id:
        return
    m = re.search(r"\d+", normalize_numbers(clean or message.text or ""))
    if not m:
        return await _reply(message, "❌ مدت بن مشخص نیست.", force=True)
    minutes = int(m.group())
    if not 1 <= minutes <= 525600:
        return await _reply(message, "❌ مدت بن باید بین ۱ دقیقه تا ۱ سال باشد.", force=True)
    from datetime import datetime, timezone as _tz, timedelta
    until = datetime.now(tz=_tz.utc) + timedelta(minutes=minutes)
    try:
        await bot.ban_chat_member(chat_id, target_id, until_date=until)
    except Exception as e:
        return await _reply(message, f"❌ خطا: {html.escape(str(e))}", force=True)
    asyncio.create_task(log_action(bot, chat_id, f"🚫 بن موقت {minutes} دقیقه — <code>{target_id}</code>"))
    if silent:
        await _finish_silent(message, silent)
        return
    mention = _mention_from_reply(message, target_id)
    await _reply(message, f"🚫 {mention}\n\n›› به مدت [ {minutes} دقیقه ] از گروه بن شد.", silent=silent)


@router.message(F.text.regexp(r"^(?:کیک|سیک|ریمو|اخراج)[\s.….۔]*$"))
async def cmd_kick(message: Message, bot: Bot):
    """اخراج بدون بن — کاربر می‌تونه دوباره با لینک برگرده"""
    silent = _silent_of(message)[1]
    chat_id = message.chat.id
    target_id = await _check_ban_target(message, bot)
    if not target_id:
        return
    try:
        await bot.ban_chat_member(chat_id, target_id)
        await bot.unban_chat_member(chat_id, target_id)
    except Exception as e:
        return await _reply(message, f"❌ خطا در اخراج: {html.escape(str(e))}", force=True)
    asyncio.create_task(
        log_action(bot, chat_id, f"👢 کیک — <code>{target_id}</code> توسط <code>{message.from_user.id}</code>")
    )
    if silent:
        await _finish_silent(message, silent)
        return
    mention = _mention_from_reply(message, target_id)
    await _reply(message, f"👢 {mention}\n\n›› از گروه اخراج شد (بدون بن).", silent=silent)


async def _perform_unban(message: Message, bot: Bot, target_id: int):
    chat_id = message.chat.id
    try:
        await bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
        await db_unban_user(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"✅ {mention}\n\n›› از لیست بن خارج شد.")
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")


@router.message(F.text.regexp(r"(?i)^(?:آن\s*بن|ان\s*بن|آنبن|انبن|حذف\s*بن)\s+\S+"))
async def cmd_unban_by_id(message: Message, bot: Bot):
    """رفع بن با آیدی یا یوزرنیم — مثلاً انبن ucski33233"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی ادمین را ندارید.")
    ident = parse_unban_target(message.text or "")
    if not ident:
        return await _reply(message, "❌ فرمت نادرست.\n📌 مثال: انبن ucski33233\n📌 یا: انبن 123456789")
    target_id = await resolve_unban_target_id(bot, chat_id, ident)
    if not target_id:
        return await _reply(
            message,
            f"❌ کاربر «{html.escape(ident)}» شناسایی نشد.\n"
            "📌 آیدی عددی یا یوزرنیم (بدون @) بفرستید، یا روی پیام کاربر ریپلای کنید.",
        )
    return await _perform_unban(message, bot, target_id)


@router.message(F.text.regexp(r"^(?:آن\s*بن|ان\s*بن|آنبن|انبن|حذف\s*بن)[\s.….۔]*$"))
async def cmd_unban(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی ادمین را ندارید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    return await _perform_unban(message, bot, target_id)


@router.message(F.text.in_(["انبلاک", "آنبلاک", "ان بلاک", "آن بلاک"]))
async def cmd_finance_unban(message: Message, bot: Bot):
    """رفع مسدودی مالی (افزایش/تسویه) — بدون آن‌بن از گروه."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ شما دسترسی ادمین را ندارید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    from bot.finance_ban import unban_finance, format_group_finance_unban_announce
    removed = await unban_finance(chat_id, target_id)
    user_tag = await _mention(target_id, bot, chat_id)
    admin_tag = await _mention(user_id, bot, chat_id)
    if not removed:
        return await _reply(
            message,
            f"ℹ️ {user_tag}\n\nاین کاربر بلاک مالی فعالی ندارد.",
        )
    return await _reply(
        message,
        format_group_finance_unban_announce(user_display=user_tag, admin_display=admin_tag),
    )


# ─── سکوت ────────────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^(?:سکوت|میوت)[\s.….۔]*$"))
async def cmd_mute(message: Message, bot: Bot):
    silent = _silent_of(message)[1]
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
        await _reply(message, f"› {mention}\n\n›› در حالت سکوت قرار گرفت.", silent=silent)
        await _finish_silent(message, silent)
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")


@router.message(F.text.regexp(r"^سکوت\s+(\d+)[\s.….۔]*$"))
async def cmd_mute_timed(message: Message, bot: Bot):
    clean, silent = _silent_of(message)
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
    m = re.search(r"\d+", normalize_numbers(clean or message.text or ""))
    if not m:
        return await _reply(message, "❌ مدت سکوت مشخص نیست.", force=True)
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
        await _reply(message, f"› {mention}\n\n›› به مدت [ {minutes} دقیقه ] سکوت شد !", silent=silent)
        await _finish_silent(message, silent)
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")


@router.message(F.text.regexp(r"^سکوت\s+\S+"))
async def cmd_mute_reason(message: Message, bot: Bot):
    """سکوت علت‌دار: سکوت فحش → ۳۰ دقیقه، تکرار ۶ ساعت، بعد ۲۴ ساعت."""
    clean, silent = _silent_of(message)
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not message.reply_to_message:
        return
    # اگر فقط عدد بود، هندلر قبلی گرفته؛ اینجا برای اطمینان رد می‌کنیم
    raw = normalize_numbers(clean.strip())
    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        return
    arg = parts[1].strip()
    if arg.isdigit():        return
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    own, adm, vip = get_user_status(chat_id, target_id)
    if own or adm or vip:
        rank = "مالک" if own else "ادمین" if adm else "عضو ویژه"
        mention = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"› {mention}\n\n›› در حال حاضر {rank} است!")

    from bot.mute_reason import apply_reason_mute, format_reason_mute_group_text

    result = apply_reason_mute(chat_id, target_id, arg)
    minutes = int(result["minutes"])
    from datetime import datetime, timezone, timedelta
    until = datetime.now(tz=timezone.utc) + timedelta(minutes=minutes)
    try:
        from aiogram.types import ChatPermissions
        await bot.restrict_chat_member(
            chat_id, target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        cache.MUTED_USERS.setdefault(chat_id, set()).add(target_id)
        await db_mute_user(chat_id, target_id)
        mention = await _mention(target_id, bot, chat_id)
        await _reply(
            message,
            format_reason_mute_group_text(
                mention, result["reason"], minutes, result["level"],
            ),
            silent=silent,
        )
        await _finish_silent(message, silent)
        try:
            await bot.send_message(target_id, result["user_text"])
        except Exception:
            pass
    except Exception as e:
        return await _reply(message, f"❌ خطا: {e}")


@router.message(F.text.regexp(
    r"^(?:حذف سکوت|آن سکوت|ان سکوت|آنسکوت|انسکوت)[\s.….۔]*$"
))
async def cmd_unmute(message: Message, bot: Bot):
    silent = _silent_of(message)[1]
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
        await _reply(message, f"› {mention}\n\n›› از حالت سکوت خارج شد.", silent=silent)
        await _finish_silent(message, silent)
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
    max_w = get_max_warnings(chat_id)
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
        if key in ("لقب", "نام"):
            await db_set_alias(chat_id, target_id, value)
            name = await _mention(target_id, bot, chat_id)
            label = "نام" if key == "نام" else "لقب"
            return await _reply(message, f"• {label} {name}\n\n» به [ {value} ] تنظیم شد !")
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

def _tag_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="📣 تگ همه", callback_data="tmenu:all")],
        [IKB(text="🛡 تگ ادمین‌ها", callback_data="tmenu:admins"), IKB(text="⭐ تگ ویژه‌ها", callback_data="tmenu:vips")],
        [IKB(text="🏆 تگ ۱۰ کاربر برتر", callback_data="tmenu:top10")],
        [IKB(text="❌ بستن", callback_data="tmenu:close")],
    ])


async def _send_tag_message(bot: Bot, chat_id: int, user_ids: list[int], header: str):
    if not user_ids:
        return await safe_send(bot, chat_id, "📭 کاربری برای تگ یافت نشد.")

    mention_items: list[str] = []
    for uid in user_ids:
        mention_items.append(await _mention(uid, bot, chat_id))

    mentions = []
    line = []
    for i, m in enumerate(mention_items, 1):
        line.append(m)
        if i % 5 == 0:
            mentions.append(" | ".join(line))
            line = []
    if line:
        mentions.append(" | ".join(line))

    await safe_send(bot, chat_id, f"{header}\n\n" + "\n".join(mentions))


@router.message(F.text.regexp(r"^تگ(\s+.*)?$"))
async def cmd_tag(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط ادمین‌ها می‌توانند تگ همگانی بزنند.")
    custom_text = message.text[3:].strip()
    if not custom_text:
        return await safe_send(
            bot,
            chat_id,
            "📣 <b>منوی تگ گروه</b>\n\nنوع تگ موردنظر رو انتخاب کن:",
            reply_to=message.message_id,
            reply_markup=_tag_panel_kb(),
        )

    top = await db_get_top_users(chat_id, 50)
    if not top:
        return await _reply(message, "📭 هنوز عضوی ثبت نشده.")
    user_ids = [u["telegram_user_id"] for u in top]
    await _send_tag_message(bot, chat_id, user_ids, custom_text or "📢 اطلاعیه")


@router.callback_query(F.data.startswith("tmenu:"))
async def cb_tag_menu(call: CallbackQuery, bot: Bot):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await call.answer("❌ فقط ادمین‌ها", show_alert=True)

    action = call.data[6:]
    if action == "close":
        try:
            await call.message.delete()
        except Exception:
            pass
        return await call.answer()

    if action == "all":
        top = await db_get_top_users(chat_id, 50)
        await _send_tag_message(bot, chat_id, [u["telegram_user_id"] for u in top], "📣 تگ همه اعضای فعال")
        return await call.answer("انجام شد")

    if action == "admins":
        admin_ids = await db_get_admins(chat_id)
        owner_id = cache.OWNER_CACHE.get(chat_id)
        ids = []
        if owner_id:
            ids.append(owner_id)
        for aid in admin_ids:
            if aid not in ids:
                ids.append(aid)
        await _send_tag_message(bot, chat_id, ids, "🛡 تگ ادمین‌های گروه")
        return await call.answer("انجام شد")

    if action == "vips":
        vip_ids = await db_get_vips(chat_id)
        await _send_tag_message(bot, chat_id, vip_ids, "⭐ تگ کاربران ویژه")
        return await call.answer("انجام شد")

    if action == "top10":
        top10 = await db_get_top_users(chat_id, 10)
        await _send_tag_message(bot, chat_id, [u["telegram_user_id"] for u in top10], "🏆 تگ ۱۰ کاربر برتر")
        return await call.answer("انجام شد")

    await call.answer()


# ─── لینک ────────────────────────────────────────────────────────────────────

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
    await safe_send(
        message.bot, chat_id, panel_home_text(role=("مالک" if is_owner(chat_id, user_id) else "ادمین")),
        reply_markup=panel_main(is_owner=is_owner(chat_id, user_id)),
        reply_to=message.message_id,
    )


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


@router.message(F.text.in_(["مالک شم", "اونر شم"]))
async def cmd_creator_make_me_owner(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not _is_creator(user_id):
        return

    if is_owner(chat_id, user_id):
        return await _reply(message, "✅ شما هم‌اکنون مالک این گروه هستید.")

    try:
        result = await db_set_owner(chat_id, user_id)
    except Exception:
        return await _reply(message, "⚠️ انتقال مالکیت انجام نشد؛ لطفاً دوباره تلاش کنید.")

    mention = await _mention(user_id, bot, chat_id)
    prev = (result or {}).get("previous_owners") or []
    prev_line = f"\n🗑 مالک قبلی حذف شد: {len(prev)} نفر" if prev else "\n🗑 مالک قبلی در ربات ثبت نبود."
    return await _reply(
        message,
        f"✅ مالکیت ربات در این گروه به شما منتقل شد.\n"
        f"👑 مالک جدید: {mention}{prev_line}",
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

@router.message(F.text.func(lambda t: bool(t and is_pure_calc_expr(t))))
async def cmd_calc_direct(message: Message):
    chat_id = message.chat.id
    text = normalize_numbers(message.text.strip())
    if chat_id in WAITING_ROUNDS and text.replace(" ", "").isdigit():
        return
    result = utils_safe_calc(text)
    if result is None:
        skip()
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

@router.message(F.text.in_(["گوید", "ایدی عددی", "آیدی عددی", "شناسه گپ", "شناسه گروه", "شناسه"]))
async def cmd_id(message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        return await _reply(message,
        f"• شناسه کاربری : <code>{target.id}</code>\n"
        f"• شناسه گروه : <code>{message.chat.id}</code>\n\n"
        f"💡 شناسه گروه را در پیوی ربات بفرستید تا پنل مالی باز شود.\n"
        f"👑 اگر مالک باشید: حساب ادمین‌ها · حق واسطه · فعالیت‌ها")
    return await _reply(message,
        f"• شناسه کاربری : <code>{message.from_user.id}</code>\n"
        f"• شناسه گروه : <code>{message.chat.id}</code>\n\n"
        f"💡 شناسه گروه را در پیوی ربات بفرستید تا پنل مالی باز شود.\n"
        f"👑 اگر مالک باشید: حساب ادمین‌ها · حق واسطه · فعالیت‌ها")


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


@router.message(F.text.in_(["کم پیام", "کم‌پیام"]))
async def cmd_quiet_extra_status(message: Message):
    if quiet_extra_on(message.chat.id):
        return await _reply(
            message,
            "• کم پیام روشن است\n"
            "• پیام‌های «توی این بازی نیستی» و «قابلیت غیرفعال» ارسال نمی‌شوند.",
        )
    return await _reply(
        message,
        "• کم پیام خاموش است\n"
        "• برای کاهش پیام‌های تکراری: «کم پیام روشن»",
    )


@router.message(F.text.in_(["کم پیام روشن", "کم‌پیام روشن", "کم پیام فعال", "فعال کردن کم پیام"]))
async def cmd_quiet_extra_on(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if quiet_extra_on(chat_id):
        return await _reply(message, "• کم پیام از قبل روشن است!")
    await db_enable_quiet_extra(chat_id)
    return await _reply(
        message,
        "• کم پیام روشن شد ✅\n"
        "• دیگر این پیام‌ها ارسال نمی‌شوند:\n"
        "  – توی این بازی نیستی تاس نریز\n"
        "  – این قابلیت توسط ادمین گروه غیرفعال شده است\n"
        "• خاموش کردن: «کم پیام خاموش»",
    )


@router.message(F.text.in_(["کم پیام خاموش", "کم‌پیام خاموش", "خاموش کم پیام", "غیرفعال کردن کم پیام"]))
async def cmd_quiet_extra_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    if not quiet_extra_on(chat_id):
        return await _reply(message, "• کم پیام از قبل خاموش است!")
    await db_disable_quiet_extra(chat_id)
    return await _reply(message, "• کم پیام خاموش شد.\n• پیام‌های هشدار دوباره ارسال می‌شوند.")


@router.message(F.text.regexp(r"^محدودیت تعداد تاس(\s+(\d+|خاموش|غیرفعال))?$"))
async def cmd_dice_turn_limit(message: Message):
    """محدودیت تعداد تاس 2 / محدودیت تعداد تاس خاموش"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    parts = message.text.strip().split()
    if len(parts) == 3:
        current = await db_get_dice_turn_limit(chat_id)
        if current <= 0:
            return await _reply(
                message,
                "📌 محدودیت تعداد تاس: خاموش\n\n"
                "برای فعال‌سازی مثلاً بگو:\n"
                "• محدودیت تعداد تاس 2\n"
                "برای خاموش کردن:\n"
                "• محدودیت تعداد تاس خاموش\n"
                "• محدودیت تعداد تاس 0",
            )
        return await _reply(
            message,
            f"📌 محدودیت تعداد تاس این گپ: {current}\n\n"
            f"هر بازیکن باید همهٔ تاس‌هایش را حداکثر در {current} نوبت بریزد.\n"
            f"نوبت آخر باید دقیقاً همه تاس‌های باقی‌مانده باشد.\n"
            f"خاموش کردن: محدودیت تعداد تاس خاموش",
        )

    arg = parts[-1]
    if arg in ("خاموش", "غیرفعال"):
        limit = 0
    else:
        try:
            limit = int(arg)
        except ValueError:
            return
    if limit < 0:
        return await _reply(message, "❌ عدد باید ۰ یا بیشتر باشد.")
    await db_set_dice_turn_limit(chat_id, limit)
    if limit == 0:
        return await _reply(message, "✅ محدودیت تعداد تاس خاموش شد.")
    if limit == 1:
        example = "مثال: راند ۲۵ و محدودیت ۱ → باید یکجا بگوید: تاس ۲۵"
    else:
        last_need = 25 - (limit - 1)
        example = (
            f"مثال: راند ۲۵ و محدودیت {limit}\n"
            f"اگر در {limit - 1} نوبت اول هر بار «تاس ۱» بزند،\n"
            f"نوبت آخر حتماً باید «تاس {last_need}» بزند."
        )
    return await _reply(
        message,
        f"✅ محدودیت تعداد تاس روی {limit} نوبت تنظیم شد.\n\n"
        f"هر بازیکن باید همه تاس‌ها را حداکثر در {limit} نوبت بریزد.\n"
        f"نوبت آخر باید دقیقاً همه تاس‌های باقی‌مانده باشد.\n\n"
        f"{example}\n"
        f"خاموش کردن: محدودیت تعداد تاس خاموش",
    )


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


@router.message(F.text.in_(["محدودیت", "وضعیت قفل"]))
async def cmd_lock_status_full(message: Message):
    chat_id = message.chat.id
    locks = cache.GROUP_LOCKS.get(chat_id) or await db_get_locks(chat_id)
    max_w = get_max_warnings(chat_id)

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
    max_w = get_max_warnings(chat_id)
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


@sync_to_async
def _get_fee_hidden(chat_id):
    from account.models import TelegramGroup
    return bool(TelegramGroup.objects.filter(telegram_chat_id=chat_id).values_list("fee_hidden", flat=True).first())


@sync_to_async
def _set_fee_hidden(chat_id, hidden):
    from account.models import TelegramGroup
    g, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    g.fee_hidden = hidden
    g.save(update_fields=["fee_hidden"])


@sync_to_async
def _get_bet_mode(chat_id):
    from account.models import TelegramGroup
    try:
        g = TelegramGroup.objects.get(telegram_chat_id=chat_id)
        mode = getattr(g, "bet_mode", None)
        return mode if mode in (BET_MODE_FIXED, BET_MODE_EXTRA) else BET_MODE_FIXED
    except TelegramGroup.DoesNotExist:
        return BET_MODE_FIXED
    except Exception:
        return BET_MODE_FIXED


@sync_to_async
def _set_bet_mode(chat_id, mode: str):
    from account.models import TelegramGroup
    g, _ = TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})
    g.bet_mode = mode
    g.save(update_fields=["bet_mode"])
    return g.bet_mode


def _tx_label(tx_type: str) -> tuple[str, str]:
    labels = {
        "admin_increase": ("➕ افزایش", "➕"),
        "admin_decrease": ("➖ کاهش", "➖"),
        "admin_clear": ("🧾 تسویه", "🧾"),
        "bet": ("❌ کسر ورودی مسابقه", "❌"),
        "win": ("🏆 برد در مسابقه", "🏆"),
    }
    return labels.get(tx_type, ("🔹 تراکنش", "🔹"))


def _receipt_from_message(message: Message) -> tuple[str, str]:
    src = message.reply_to_message
    if not src:
        return "", ""
    if getattr(src, "photo", None):
        return str(src.photo[-1].file_id), "photo"
    if getattr(src, "document", None):
        return str(src.document.file_id), "document"
    return "", ""


@router.message(F.text.regexp(INCREASE_COMMAND_RE))
async def cmd_increase_wallet(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = (message.text or "").strip()
    if text in MEMBER_INCREASE_TEXTS and not (is_admin(chat_id, user_id) or is_owner(chat_id, user_id)):
        from bot.finance_ban import is_finance_banned, FINANCE_BAN_USER_TEXT
        if await is_finance_banned(chat_id, user_id):
            return await _reply(message, FINANCE_BAN_USER_TEXT)
        ok = await start_increase_request_flow(bot, user_id, chat_id)
        if not ok:
            return await _reply(message, "❌ ارسال پیام در پیوی ناموفق بود؛ احتمالاً ربات را /start نکرده‌اید یا پیوی ربات را مسدود کرده‌اید.")
        return await _reply(message, "📩 برای ثبت مبلغ، پیامتان در پیوی ربات ارسال شد.")
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)

    mode, amount = parse_increase_command(normalize_numbers(message.text))
    if mode == "invalid":
        return await _reply(
            message,
            "❗ فرمت دستور صحیح نیست.\n"
            "• <code>افزایش موجودی 5000</code> یا <code>افزایش 5000</code>\n"
            "• <code>افزایش موجودی</code> یا <code>افزایش موجودی پیوی</code> (با ریپلای) → مبلغ در پیوی",
        )

    if not message.reply_to_message:
        return await _reply(message, "⚠️ لطفاً روی پیام کاربر مورد نظر ریپلای کنید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return

    if mode == "pv":
        return await start_increase_pv_flow(
            bot, chat_id, user_id, target_id, message.message_id,
        )

    receipt_id, receipt_kind = _receipt_from_message(message)
    new_balance = await increase_wallet(
        chat_id, target_id, amount, admin_id=user_id,
        description=("با رسید" if receipt_id else "بدون رسید"),
        receipt_file_id=receipt_id, receipt_note=(receipt_kind or "بدون رسید"),
    )
    try:
        from bot.challenges import flush_challenge_breaks
        await flush_challenge_breaks(bot, chat_id)
    except Exception:
        pass
    user_tag = await _mention(target_id, bot, chat_id)
    admin_tag = await _mention(user_id, bot, chat_id)
    text = (
        "✅ عملیات افزایش موجودی با موفقیت انجام شد\n\n"
        f"👤 کاربر: {user_tag}\n"
        f"🛡 مدیر اجراکننده: {admin_tag}\n\n"
        f"💰 مبلغ افزایش: {amount:,} واحد اعتباری\n"
        f"📊 موجودی فعلی: {new_balance:,} واحد اعتباری"
        f"{TIP_DIRECT}"
    )
    return await _reply(message, text)


@router.callback_query(F.data.regexp(r"^inc_game:-?\d+:\d+$"))
async def cb_increase_from_game_result(call: CallbackQuery, bot: Bot):
    """دکمه‌های قدیمی روی نتیجه — غیرفعال."""
    return await call.answer(
        "این دکمه دیگر فعال نیست. از پیام «موجودی پس از بازی» استفاده کنید.",
        show_alert=True,
    )


@router.message(F.text.regexp(r"^(کاهش موجودی|کاهش)\s+\d+"))
async def cmd_decrease_wallet(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    if not message.reply_to_message:
        return await _reply(message, "⚠️ لطفاً روی پیام کاربر مورد نظر ریپلای کنید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    parts = message.text.split()
    amount_token = next((p for p in parts[1:] if p.isdigit()), "")
    try:
        amount = int(amount_token)
    except ValueError:
        return await _reply(message, "❗ مقدار کاهش عدد معتبر نیست.")
    receipt_id, receipt_kind = _receipt_from_message(message)
    new_balance = await decrease_wallet(
        chat_id, target_id, amount, admin_id=user_id,
        description=("با رسید" if receipt_id else "بدون رسید"),
        receipt_file_id=receipt_id, receipt_note=(receipt_kind or "بدون رسید"),
    )
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


def _parse_transfer_amount(text: str) -> int | None:
    """فقط دستور خالص: انتقال 5000 / انتقال موجودی 5000 — نه «انتقال 50 بدم؟»."""
    raw = normalize_numbers(text or "").strip()
    if not re.fullmatch(r"انتقال(?:\s+موجودی)?\s+\d+", raw):
        return None
    parts = raw.split()
    if raw.startswith("انتقال موجودی") and len(parts) == 3 and parts[2].isdigit():
        return int(parts[2])
    if len(parts) == 2 and parts[0] == "انتقال" and parts[1].isdigit():
        return int(parts[1])
    return None


@router.message(F.text.in_(["انتقال خاموش", "انتقال روشن", "انتقال وضعیت"]))
async def cmd_transfer_toggle(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return
    cmd = (message.text or "").strip()
    if cmd == "انتقال وضعیت":
        on = await get_transfer_enabled(chat_id)
        return await _reply(
            message,
            "💸 وضعیت انتقال موجودی\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{'✅ روشن' if on else '⛔️ خاموش'}\n\n"
            "روشن: انتقال روشن\n"
            "خاموش: انتقال خاموش",
        )
    turn_on = cmd == "انتقال روشن"
    await set_transfer_enabled(chat_id, turn_on)
    return await _reply(
        message,
        "✅ انتقال موجودی روشن شد." if turn_on else "⛔️ انتقال موجودی خاموش شد.",
    )


@router.message(F.text.regexp(r"^تنظیم\s*جایزه"))
async def cmd_prize_setting(message: Message, bot: Bot):
    from bot.stat_prizes import (
        parse_prize_setting_command, get_group_prizes, set_group_prize,
        format_prizes_status,
    )
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)

    parsed = parse_prize_setting_command(message.text or "")
    if parsed is None:
        return
    kind, payload = parsed
    if kind == "status":
        cfg = await get_group_prizes(chat_id)
        return await _reply(message, format_prizes_status(cfg))
    if kind == "help":
        return await _reply(
            message,
            "📖 تنظیم جایزه\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• <code>تنظیم جایزه تعداد ۵۰۰</code>\n"
            "• <code>تنظیم جایزه بیشترین شرط ۵۰۰</code>\n"
            "• <code>تنظیم جایزه اول ۵۰۰۰</code>\n"
            "• <code>تنظیم جایزه دوم ۲۰۰۰</code>\n"
            "• <code>تنظیم جایزه سوم ۱۰۰۰</code>\n"
            "• <code>تنظیم جایزه وضعیت</code>\n\n"
            "عدد ۰ یعنی بدون جایزه.",
        )
    field, amount, title = payload
    val = await set_group_prize(chat_id, field, amount)
    if val <= 0:
        return await _reply(message, f"🌙 {title} خاموش شد (جایزه ۰).")
    return await _reply(message, f"✅ {title} روی <b>{val:,}</b> واحد تنظیم شد.")


@router.message(F.text.in_(["لیگ روشن", "لیگ خاموش", "لیگ وضعیت"]))
async def cmd_league_toggle(message: Message, bot: Bot):
    from bot.league import (
        is_league_allowed_user, is_league_enabled, set_league_enabled,
        format_tiers_help, format_season_deadline,
    )
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_league_allowed_user(user_id):
        return
    cmd = (message.text or "").strip()
    if cmd == "لیگ وضعیت":
        on = await is_league_enabled(chat_id)
        from bot.stat_prizes import get_group_prizes, format_week_prizes_line
        cfg = await get_group_prizes(chat_id)
        wp = format_week_prizes_line(cfg, html=True)
        extra = f"\n{wp}\n" if wp else "\n"
        return await _reply(
            message,
            "🏅 وضعیت لیگ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{'✅ روشن' if on else '⛔️ خاموش'}\n\n"
            f"{format_season_deadline()}"
            f"{extra}\n"
            "روشن: لیگ روشن\n"
            "خاموش: لیگ خاموش\n\n"
            + format_tiers_help(),
        )
    turn_on = cmd == "لیگ روشن"
    await set_league_enabled(chat_id, turn_on)
    if turn_on:
        return await _reply(
            message,
            "✅ لیگ روشن شد.\n\n"
            f"{format_season_deadline()}\n\n"
            "دستورات:\n"
            "• لیگ من — وضعیت شما\n"
            "• لیگ / رتبه‌بندی — جدول برترین‌ها\n"
            "• تم لیگ 1 تا 10 — ظاهر جدول\n\n"
            + format_tiers_help(),
        )
    return await _reply(message, "⛔️ لیگ خاموش شد.")


@router.message(F.text.regexp(r"^(?:لیگ\s*نمونه|نمونه\s*لیگ)(?:\s+\d+)?$"))
async def cmd_league_sample(message: Message, bot: Bot):
    from bot.league import handle_league_sample_command
    await handle_league_sample_command(message, bot)


@router.message(F.text.regexp(r"^تم\s*لیگ(\s|$)"))
async def cmd_league_theme(message: Message, bot: Bot):
    from bot.league import handle_league_theme_command
    handled = await handle_league_theme_command(message, bot)
    if not handled:
        return


@router.message(F.text.in_(["لیگ من", "لیگمن"]))
async def cmd_league_me(message: Message, bot: Bot):
    from bot.league import is_league_enabled, get_my_league, format_my_league
    chat_id = message.chat.id
    if not await is_league_enabled(chat_id):
        return await _reply(message, "⛔️ لیگ در این گپ خاموش است.")
    data = await get_my_league(chat_id, message.from_user.id)
    return await _reply(message, format_my_league(data))


_LEAGUE_BOARD_RE = re.compile(
    r"^(?:لیگ|لیگ برترها|جدول لیگ|برترین لیگ|"
    r"رتبه بندی|رتبه‌بندی|رتبه بندی لیگ|رتبه‌بندی لیگ|"
    r"لیگ رتبه|لیگ رتبه‌بندی)"
    r"(?:\s+(\d+))?$"
)


@router.message(F.text.regexp(_LEAGUE_BOARD_RE))
async def cmd_league_board(message: Message, bot: Bot):
    from bot.league import (
        is_league_enabled, parse_league_board_page, build_league_board_page,
    )
    # لیگ من / روشن و ... را رد کن
    page = parse_league_board_page(message.text or "")
    if page is None:
        return
    chat_id = message.chat.id
    if not await is_league_enabled(chat_id):
        return await _reply(message, "⛔️ لیگ در این گپ خاموش است.")
    text, kb = await build_league_board_page(
        bot, chat_id, page, viewer_id=message.from_user.id,
    )
    await safe_send(
        message.bot, message.chat.id, text,
        reply_to=message.message_id, reply_markup=kb,
    )


@router.callback_query(F.data.startswith("lgb:"))
async def cb_league_board_page(call: CallbackQuery, bot: Bot):
    from bot.league import handle_league_board_callback
    await handle_league_board_callback(call, bot)


@router.message(F.text.in_(["لیگ راهنما", "راهنما لیگ"]))
async def cmd_league_help(message: Message, bot: Bot):
    from bot.league import format_tiers_help, format_season_deadline
    return await _reply(message, format_season_deadline() + "\n\n" + format_tiers_help())


@router.message(F.text.regexp(r"^انتقال(?:\s+موجودی)?\s+\d+$"))
async def cmd_transfer_balance(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await get_transfer_enabled(chat_id):
        return await _reply(
            message,
            "⛔️ انتقال موجودی در این گروه خاموش است.\n"
            "ادمین می‌تواند با «انتقال روشن» فعال کند.",
        )
    amount = _parse_transfer_amount(message.text)
    if not amount or amount <= 0:
        return await _reply(
            message,
            "❗ فرمت صحیح:\n"
            "• <code>انتقال موجودی 5000</code>\n"
            "• <code>انتقال 5000</code>\n\n"
            "⚠️ روی پیام کاربر مقصد ریپلای کنید.",
        )
    if not message.reply_to_message:
        return await _reply(message, "⚠️ برای انتقال، روی پیام کاربر مقصد ریپلای کنید.")
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    if int(target_id) == int(user_id):
        return await _reply(message, "❌ نمی‌توانید به خودتان انتقال دهید.")

    result = await transfer_wallet(chat_id, user_id, target_id, amount)
    if not result.get("ok"):
        err = result.get("error")
        if err == "insufficient":
            bal = int(result.get("from_balance", 0) or 0)
            pending = int(result.get("pending", 0) or 0)
            if pending > 0:
                return await _reply(
                    message,
                    "❌ موجودی مجاز کافی نیست.\n\n"
                    f"✅ موجودی مجاز: {bal:,} واحد\n"
                    f"⏳ در حال تسویه: {pending:,} واحد\n"
                    f"🔻 کمبود: {max(0, amount - bal):,} واحد\n\n"
                    "💡 مبلغ در حال تسویه قابل انتقال نیست؛ فقط موجودی مجاز را می‌توانید منتقل کنید.",
                )
            return await _reply(
                message,
                f"❌ موجودی کافی نیست.\n💰 موجودی شما: {bal:,} واحد\n🔻 کمبود: {amount - bal:,} واحد",
            )
        if err == "self_transfer":
            return await _reply(message, "❌ نمی‌توانید به خودتان انتقال دهید.")
        return await _reply(message, "❗ مبلغ انتقال نامعتبر است.")

    sender_tag = await _mention(user_id, bot, chat_id)
    target_tag = await _mention(target_id, bot, chat_id)
    text = (
        "✅ انتقال موجودی انجام شد\n\n"
        f"📤 از: {sender_tag}\n"
        f"📥 به: {target_tag}\n"
        f"💰 مبلغ: {amount:,} واحد اعتباری\n\n"
        f"📊 موجودی شما: {result['from_balance']:,} واحد\n"
        f"📊 موجودی مقصد: {result['to_balance']:,} واحد"
    )
    await _reply(message, text)
    try:
        await bot.send_message(
            target_id,
            f"📥 {amount:,} واحد از {message.from_user.full_name or 'کاربر'} دریافت کردید.\n"
            f"📊 موجودی فعلی: {result['to_balance']:,} واحد",
        )
    except Exception:
        pass


@router.message(F.text.func(lambda t: parse_balance_command(t) is not None))
async def cmd_balance(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    mode, is_my = parse_balance_command(message.text)

    if is_my:
        target_id = user_id
    elif message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        target_id = user_id

    viewing_other = target_id != user_id
    if viewing_other:
        if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
            return await _reply(message, ADMIN_DENY_TEXT)

    from bot.finance import get_playable_balance, format_balance_card

    _total, playable, pending = await get_playable_balance(chat_id, target_id)
    try:
        member = await bot.get_chat_member(chat_id, target_id)
        plain_name = (member.user.full_name or member.user.first_name or "کاربر")
    except Exception:
        plain_name = "کاربر"
    j_time_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")

    viewing_self = target_id == user_id
    text = format_balance_card(
        playable=playable,
        pending=pending,
        total=_total,
        time_str=j_time_str,
        viewer_name=html.escape(plain_name),
        viewing_other=not viewing_self,
        html=True,
    )

    private = mode == "pm"
    kb = tx_report_kb(chat_id, target_id) if private else None
    return await deliver_balance_sensitive(
        bot, chat_id, user_id, message.message_id, text,
        private=private,
        reply_markup=kb,
    )


@router.message(F.text.in_(["ثبت چالش", "ثبت چالش‌ها", "ثبت چالشها"]))
async def cmd_register_challenge(message: Message, bot: Bot):
    from bot.challenge_panel import open_challenge_panel_from_group
    await open_challenge_panel_from_group(
        bot, message.chat.id, message.from_user.id, message.message_id,
    )


@router.message(F.text.in_(["تست چالش", "تست چالش‌ها", "تست چالشها"]))
async def cmd_test_challenge(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id) and not is_admin(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    from bot.challenges import force_settle_chat_challenges
    count = await force_settle_chat_challenges(bot, chat_id)
    if count <= 0:
        return await _reply(
            message,
            "ℹ️ چالش زمان‌دار فعالی برای تسویه وجود نداشت.\n"
            "(چالش‌های تاس/دارت/... از نوع «اولین نفر» با این دستور بسته نمی‌شوند.)",
        )
    return await _reply(
        message,
        f"🧪 تست چالش انجام شد\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ تعداد چالش بسته‌شده: {count}\n"
        f"🎁 جایزه برنده(ها) تا این لحظه واریز شد.",
    )


@router.message(F.text.in_(["وضعیت چالش", "وضعیت چالش‌ها", "وضعیت چالشها"]))
async def cmd_challenge_status(message: Message, bot: Bot):
    from bot.challenges import build_challenges_status_text

    text = await build_challenges_status_text(bot, message.chat.id)
    return await _reply(message, text)


@router.message(F.text.in_(["لغو درخواست تسویه", "لغو درخواست تسویه حساب"]))
async def cmd_cancel_pending_withdrawal(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # بدون ریپلای: کاربر درخواست خودش را لغو می‌کند
    if not message.reply_to_message:
        from bot.withdrawal_flow import self_cancel_pending_withdrawals
        result = await self_cancel_pending_withdrawals(bot, chat_id, user_id)
        if result["cancelled_count"] == 0:
            return await _reply(message, "ℹ️ درخواست تسویه باز برای لغو ندارید.")
        return await _reply(
            message,
            "✅ درخواست تسویه شما لغو شد\n\n"
            f"📋 تعداد: {result['cancelled_count']}\n"
            f"💰 مجموع: {result['total_amount']:,} واحد\n\n"
            "💡 موجودی آزاد شد و می‌توانید درخواست جدید ثبت کنید.",
        )

    # با ریپلای: فقط ادمین می‌تواند درخواست کاربر دیگر را لغو کند
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return await _reply(message, "❌ کاربر هدف شناسایی نشد.")
    from bot.withdrawal_flow import admin_cancel_pending_withdrawals
    result = await admin_cancel_pending_withdrawals(
        bot, chat_id, target_id, cancelled_by=user_id,
    )
    if result["cancelled_count"] == 0:
        user_tag = await _mention(target_id, bot, chat_id)
        return await _reply(message, f"ℹ️ کاربر {user_tag} درخواست تسویه باز (در انتظار) ندارد.")
    user_tag = await _mention(target_id, bot, chat_id)
    return await _reply(
        message,
        "✅ درخواست تسویه لغو شد\n\n"
        f"👤 کاربر: {user_tag}\n"
        f"📋 تعداد: {result['cancelled_count']}\n"
        f"💰 مجموع: {result['total_amount']:,} واحد\n\n"
        "💡 موجودی کاربر برای بازی و تراکنش‌ها آزاد شد.",
    )


@router.message(F.text == "حداقل تسویه خاموش")
async def cmd_min_withdrawal_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    from bot.withdrawal_flow import set_min_withdrawal
    await set_min_withdrawal(chat_id, 0)
    return await _reply(
        message,
        "✅ حداقل تسویه غیرفعال شد.\nکاربران بدون محدودیت حداقل می‌توانند درخواست تسویه بدهند.",
    )


@router.message(F.text == "حداقل پیوی خاموش")
async def cmd_min_pv_off(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    from bot.pv_dice import set_min_pv_bet
    await set_min_pv_bet(chat_id, 0)
    return await _reply(
        message,
        "✅ حداقل پیوی غیرفعال شد.\nفقط حداقل سراسری (۵ واحد) اعمال می‌شود.",
    )


@router.message(F.text.in_(["ارسال جستجو", "ارسال جستجوی حریف"]))
async def cmd_broadcast_pv_search(message: Message, bot: Bot):
    """ارسال دعوت جستجوی حریف به کسانی که حداقل یک‌بار در این گپ بازی کرده‌اند."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)

    from asgiref.sync import sync_to_async
    from account.models import DiceGameHistory
    from bot.pv_search import search_opponent_kb
    from bot.helpers import send_private

    @sync_to_async
    def _player_ids():
        return list(
            DiceGameHistory.objects.filter(telegram_chat_id=int(chat_id))
            .values_list("telegram_user_id", flat=True)
            .distinct()[:500]
        )

    players = await _player_ids()
    if not players:
        return await _reply(message, "📭 هنوز کسی در این گپ بازی ثبت‌شده ندارد.")

    gname = message.chat.title or "گروه"
    text = (
        "⚔️ حریف جدید منتظرته!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 {gname}\n\n"
        "می‌تونی مستقیم از پیوی ربات حریف پیدا کنی و مسابقه تاس بسازی — "
        "بدون نیاز به ریپلای داخل گپ.\n\n"
        "روی دکمه زیر بزن و شروع کن 👇"
    )
    kb = search_opponent_kb()
    await _reply(message, f"📤 در حال ارسال به {len(players)} نفر…")

    ok = 0
    fail = 0
    for uid in players:
        try:
            if await send_private(bot, int(uid), text, reply_markup=kb):
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)

    return await _reply(
        message,
        "✅ ارسال جستجو تمام شد\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📬 موفق: {ok}\n"
        f"⚠️ ناموفق/بدون پیوی: {fail}",
    )


@router.message(F.text.func(lambda t: t and (
    t.strip() == "تنظیم گپ اعلام نتایج خاموش"
    or t.strip() == "گپ اعلام نتایج خاموش"
    or t.startswith("تنظیم گپ اعلام نتایج")
    or t.startswith("گپ اعلام نتایج")
)))
async def cmd_pv_results_chat(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    from bot.pv_dice import (
        get_pv_results_chat_id, set_pv_results_chat_id, parse_pv_results_chat_command,
    )
    parsed = parse_pv_results_chat_command(message.text or "")
    if not parsed:
        return await _reply(
            message,
            "❌ فرمت نامعتبر.\n"
            "مثال: <code>تنظیم گپ اعلام نتایج -1001234567890</code>",
        )
    action, dest = parsed
    if action == "off":
        await set_pv_results_chat_id(chat_id, None)
        return await _reply(message, "✅ گپ اعلام نتایج پیوی خاموش شد.")
    if action == "show":
        current = await get_pv_results_chat_id(chat_id)
        if current:
            return await _reply(
                message,
                "📌 گپ اعلام نتایج پیوی\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"✅ فعال: <code>{current}</code>\n\n"
                "نتیجه بازی‌های پیوی + شناسه بازیکنان در آن گپ اعلام می‌شود.\n\n"
                "تغییر:\n<code>تنظیم گپ اعلام نتایج -100...</code>\n"
                "خاموش:\n<code>تنظیم گپ اعلام نتایج خاموش</code>",
            )
        return await _reply(
            message,
            "📌 گپ اعلام نتایج پیوی\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "❌ تنظیم نشده\n\n"
            "فعال‌سازی:\n"
            "<code>تنظیم گپ اعلام نتایج -1001234567890</code>\n\n"
            "خاموش:\n"
            "<code>تنظیم گپ اعلام نتایج خاموش</code>\n\n"
            "⚠️ فقط گپی قابل تنظیم است که ربات داخلش باشد و شما آنجا هم ادمین/مالک باشید.",
        )

    dest_id = int(dest)
    # جلوگیری از سوءاستفاده: فقط اگر ادمین مقصد هم باشد و ربات آنجا بتواند بفرستد
    if dest_id != int(chat_id):
        from asgiref.sync import sync_to_async
        from account.models import TelegramGroup

        exists = await sync_to_async(
            lambda: TelegramGroup.objects.filter(telegram_chat_id=dest_id).exists()
        )()
        if not exists:
            return await _reply(
                message,
                "❌ این شناسه در ربات ثبت نشده.\n"
                "اول ربات را به آن گپ اضافه کنید و یک‌بار آنجا فعال شود.",
            )
        if not is_admin(dest_id, user_id) and not is_owner(dest_id, user_id):
            return await _reply(
                message,
                "❌ شما ادمین/مالک گپ مقصد نیستید.\n"
                "نمی‌توان گپ دیگران را برای اعلام نتایج تنظیم کرد.",
            )
        try:
            me = await bot.get_me()
            member = await bot.get_chat_member(dest_id, me.id)
            status = getattr(member, "status", "") or ""
            if status in ("left", "kicked"):
                return await _reply(message, "❌ ربات در گپ مقصد عضو نیست.")
        except Exception:
            return await _reply(
                message,
                "❌ ربات به گپ مقصد دسترسی ندارد یا شناسه اشتباه است.",
            )

    await set_pv_results_chat_id(chat_id, dest_id)
    return await _reply(
        message,
        f"✅ گپ اعلام نتایج پیوی تنظیم شد.\n"
        f"📍 مقصد: <code>{dest_id}</code>\n\n"
        "از این پس نتیجه بازی‌های پیوی این گروه + شناسه دو بازیکن در آن گپ اعلام می‌شود.",
    )


@router.message(F.text.regexp(r"^چت\s*پیوی$"))
async def cmd_admin_pv_chat(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    if not message.reply_to_message:
        return await _reply(
            message,
            "↩️ روی پیام کاربر ریپلای کنید و بنویسید:\n<code>چت پیوی</code>\n\n"
            "لیست بازی‌ها به پیوی شما ارسال می‌شود؛ بعد بازی را انتخاب کنید تا چت همان بازی بیاید.\n\n"
            "خاموش/روشن کردن چت داخل بازی:\n"
            "<code>چت پیوی روشن</code> · <code>چت پیوی خاموش</code> · <code>چت پیوی وضعیت</code>",
        )
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    from bot.pv_dice import open_admin_pv_chat_browser
    tname = ""
    try:
        u = message.reply_to_message.from_user
        if u:
            tname = (u.full_name or u.username or "").strip()
    except Exception:
        pass
    await open_admin_pv_chat_browser(
        bot,
        group_id=chat_id,
        admin_id=user_id,
        target_id=target_id,
        group_msg_id=message.message_id,
        target_name=tname or str(target_id),
    )


@router.message(F.text.func(lambda t: t and t.startswith("حداقل پیوی") and t.strip() != "حداقل پیوی خاموش"))
async def cmd_min_pv(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    from bot.pv_dice import (
        get_min_pv_bet, set_min_pv_bet, parse_min_pv_command, effective_min_pv_bet, MIN_BET,
    )
    parsed = parse_min_pv_command(message.text)
    if not parsed:
        return await _reply(message, "❌ مبلغ نامعتبر است.\nمثال: <code>حداقل پیوی 30</code>")
    action, amount = parsed
    if action == "show":
        current = await get_min_pv_bet(chat_id)
        eff = effective_min_pv_bet(current)
        if current <= 0:
            text = (
                "📌 حداقل پیوی\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"❌ غیرفعال (حداقل سراسری: {MIN_BET:,})\n\n"
                "برای فعال‌سازی:\n"
                "   <code>حداقل پیوی 30</code>\n\n"
                "برای خاموش کردن:\n"
                "   <code>حداقل پیوی خاموش</code>"
            )
        else:
            text = (
                "📌 حداقل پیوی\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"✅ فعال — {current:,} واحد\n"
                f"📐 حداقل مؤثر: {eff:,} واحد\n\n"
                "شروع پیوی با مبلغ بازی کمتر از این مبلغ قبول نمی‌شود.\n\n"
                "برای تغییر:\n"
                "   <code>حداقل پیوی 50</code>\n\n"
                "برای خاموش کردن:\n"
                "   <code>حداقل پیوی خاموش</code>"
            )
        return await _reply(message, text)
    await set_min_pv_bet(chat_id, amount)
    return await _reply(
        message,
        f"✅ حداقل پیوی روی <b>{amount:,}</b> واحد تنظیم شد.\n\n"
        f"فقط از {amount:,} به بالا می‌توان درخواست شروع پیوی داد.\n"
        f"مثال: <code>شروع 2 {amount} پیوی</code>",
    )


@router.message(F.text.func(lambda t: t and t.startswith("حداقل تسویه") and t.strip() != "حداقل تسویه خاموش"))
async def cmd_min_withdrawal(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    from bot.withdrawal_flow import get_min_withdrawal, set_min_withdrawal, parse_min_withdrawal_command
    parsed = parse_min_withdrawal_command(message.text)
    if not parsed:
        return await _reply(message, "❌ مبلغ نامعتبر است.\nمثال: <code>حداقل تسویه 50</code>")
    action, amount = parsed
    if action == "show":
        current = await get_min_withdrawal(chat_id)
        if current <= 0:
            text = (
                "📌 حداقل تسویه\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "❌ غیرفعال\n\n"
                "برای فعال‌سازی:\n"
                "   <code>حداقل تسویه 50</code>\n\n"
                "برای خاموش کردن:\n"
                "   <code>حداقل تسویه خاموش</code>"
            )
        else:
            text = (
                "📌 حداقل تسویه\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"✅ فعال — {current:,} واحد\n\n"
                "کاربرانی که موجودی قابل تسویه‌شان کمتر از این مبلغ باشد "
                "نمی‌توانند درخواست تسویه ثبت کنند.\n\n"
                "برای تغییر:\n"
                "   <code>حداقل تسویه 100</code>\n\n"
                "برای خاموش کردن:\n"
                "   <code>حداقل تسویه خاموش</code>"
            )
        return await _reply(message, text)
    await set_min_withdrawal(chat_id, amount)
    return await _reply(
        message,
        f"✅ حداقل تسویه روی <b>{amount:,}</b> واحد تنظیم شد.\n\n"
        f"کاربران با موجودی قابل تسویه کمتر از {amount:,} واحد "
        "نمی‌توانند درخواست تسویه ثبت کنند.",
    )


@router.message(F.text.regexp(SETTLE_COMMAND_RE))
async def cmd_settle(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = normalize_numbers(message.text or "").strip()

    async def _block_if_pending_pv(target_id: int) -> bool:
        from bot.withdrawal_flow import (
            get_open_withdrawal_info,
            format_pending_pv_withdrawal_block,
        )
        info = await get_open_withdrawal_info(chat_id, target_id)
        if not info:
            return False
        user_tag = await _mention(target_id, bot, chat_id)
        await _reply(
            message,
            format_pending_pv_withdrawal_block(user_display=user_tag, info=info),
        )
        return True

    if text in MEMBER_SETTLE_TEXTS and not (is_admin(chat_id, user_id) or is_owner(chat_id, user_id)):
        from bot.withdrawal_flow import (
            begin as begin_withdrawal, BEGIN_OK, BEGIN_MIN_BLOCKED, BEGIN_PENDING, BEGIN_BANNED,
        )
        result = await begin_withdrawal(bot, chat_id, user_id)
        if result == BEGIN_OK:
            notice = "📩 برای تکمیل درخواست تسویه، ادامه مراحل در پیوی ارسال شد."
        elif result == BEGIN_PENDING:
            notice = "⚠️ یک درخواست تسویه باز دارید. جزئیات در پیوی ارسال شد."
        elif result == BEGIN_MIN_BLOCKED:
            notice = "⚠️ موجودی قابل تسویه شما کمتر از حداقل مجاز است. توضیحات در پیوی ارسال شد."
        elif result == BEGIN_BANNED:
            from bot.finance_ban import FINANCE_BAN_USER_TEXT
            notice = FINANCE_BAN_USER_TEXT
        else:
            notice = "⚠️ لطفاً ابتدا پیوی ربات را باز کنید و آن را از بلاک خارج کنید."
        return await _reply(message, notice)

    if text in ("تسویه همه حساب ها", "تسویه تمام حساب ها", "تسویه حساب ها"):
        if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
            return await _reply(message, ADMIN_DENY_TEXT)
        receipt_id, receipt_kind = _receipt_from_message(message)
        results = await clear_all_wallets(chat_id, admin_id=user_id, receipt_file_id=receipt_id, receipt_note=(receipt_kind or "بدون رسید"))
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
        return await _reply(message, ADMIN_DENY_TEXT)

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
        if await _block_if_pending_pv(target_id):
            return
        receipt_id, receipt_kind = _receipt_from_message(message)
        cleared = await clear_wallet(chat_id, target_id, admin_id=user_id, receipt_file_id=receipt_id, receipt_note=(receipt_kind or "بدون رسید"))
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

    # تسویه N — کاهش جزئی؛ رقم فارسی هم بعد از normalize_numbers قبول می‌شود
    partial_amount = None
    if len(parts) >= 2 and parts[0] == "تسویه" and parts[1].isdigit():
        partial_amount = int(parts[1])
    elif (
        len(parts) >= 2
        and parts[0] == "تسویه"
        and parts[1] not in ("حساب", "کاربر", "همه", "تمام")
    ):
        # مثلاً «تسویه ده» — هرگز به تسویه کامل سقوط نکند
        return await _reply(
            message,
            "❌ مبلغ تسویه نامعتبر است.\n"
            "📌 مثال کاهش جزئی: <code>تسویه 10</code>\n"
            "📌 تسویه کامل: روی پیام کاربر ریپلای کنید و فقط <code>تسویه</code> بفرستید.",
        )

    if partial_amount is not None and not message.reply_to_message:
        accounts = await get_active_accounts(chat_id)
        return await _reply(
            message,
            f"⚠️ روش صحیح کاهش موجودی\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"شما دستور `تسویه {partial_amount}` را بدون ریپلای ارسال کردید.\n\n"
            f"📌 برای کاهش موجودی: روی پیام کاربر ریپلای کنید و `تسویه {partial_amount}` بفرستید.\n"
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

    if await _block_if_pending_pv(target_id):
        return

    if partial_amount is not None:
        amount = partial_amount
        if amount <= 0:
            return await _reply(message, "❌ مبلغ باید بزرگتر از صفر باشد.")
        receipt_id, receipt_kind = _receipt_from_message(message)
        new_balance = await decrease_wallet(chat_id, target_id, amount, admin_id=user_id, description=("با رسید" if receipt_id else "بدون رسید"), receipt_file_id=receipt_id, receipt_note=receipt_kind)
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

    # فقط «تسویه» / «تسویه حساب» بدون مبلغ → صفر کردن کامل
    if text not in ("تسویه", "تسویه حساب"):
        return await _reply(
            message,
            "❌ دستور تسویه نامعتبر است.\n"
            "📌 کاهش جزئی: <code>تسویه 10</code>\n"
            "📌 تسویه کامل: <code>تسویه</code>",
        )

    receipt_id, receipt_kind = _receipt_from_message(message)
    cleared = await clear_wallet(chat_id, target_id, admin_id=user_id, receipt_file_id=receipt_id, receipt_note=(receipt_kind or "بدون رسید"))
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


@router.message(F.text.func(lambda t: parse_accounts_command(t) is not None))
async def cmd_accounts(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)

    mode, page = parse_accounts_command(message.text)
    group_name = None
    try:
        chat = await bot.get_chat(chat_id)
        group_name = chat.title
    except Exception:
        pass

    if mode == "pm":
        return await deliver_accounts_pm(
            bot, chat_id, user_id, message.message_id, group_name=group_name,
        )

    accounts = await get_active_accounts(chat_id)
    if not accounts:
        return await _reply(message, "✅ همه حساب‌ها صاف شده!")

    total_count = len(accounts)
    total_balance = sum(int(acc.get("point") or 0) for acc in accounts)
    pages = max(1, (total_count + GROUP_LIST_PER_PAGE - 1) // GROUP_LIST_PER_PAGE)
    page = min(max(1, int(page or 1)), pages)
    start = (page - 1) * GROUP_LIST_PER_PAGE
    chunk = accounts[start:start + GROUP_LIST_PER_PAGE]
    lines = []
    for offset, acc in enumerate(chunk):
        idx = start + offset + 1
        uid = acc["telegram_user_id"]
        balance = acc["point"] or 0
        tag = await _mention(uid, bot, chat_id)
        if balance < 0:
            lines.append(f"{idx}. {tag} — 🔻 {abs(balance):,} واحد بدهکار")
        else:
            lines.append(f"{idx}. {tag} — {balance:,} واحد")
        if acc.get("balance_hidden"):
            lines[-1] += " 🔒"

    nav = f"📄 صفحه {page} از {pages}"
    if pages > 1:
        tip_parts = []
        if page > 1:
            tip_parts.append(
                f"صفحه قبل: <code>حساب ها{'' if page == 2 else f' {page - 1}'}</code>"
            )
        if page < pages:
            tip_parts.append(f"صفحه بعد: <code>حساب ها {page + 1}</code>")
        if tip_parts:
            nav += "\n💡 " + " | ".join(tip_parts)

    text = (
        "📒 لیست حساب‌های فعال گروه\n"
        "━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines)
        + "\n━━━━━━━━━━━━━━━━━━\n"
        f"💼 مجموع تراز گروه: {total_balance:,} واحد\n"
        f"🔢 تعداد حساب‌های تسویه نشده: {total_count}\n"
        f"{nav}"
    )
    return await _reply(message, text)


@router.callback_query(F.data.startswith("acc:"))
async def cb_accounts_panel(call: CallbackQuery, bot: Bot):
    return await handle_accounts_callback(call, bot)


@router.callback_query(F.data.startswith("ua:"))
async def cb_user_admin_group(call: CallbackQuery, bot: Bot):
    from bot.user_admin import handle_user_admin_callback
    return await handle_user_admin_callback(call, bot)


@router.message(F.text.func(lambda t: parse_report_command(t) is not None))
async def cmd_report_pm(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    _, page = parse_report_command(message.text)

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        target_id = user_id

    viewing_other = target_id != user_id
    if viewing_other and not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)

    await send_tx_report_pm(
        bot, chat_id, user_id, message.message_id, target_id, page,
    )


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

    viewing_other = target_id != user_id
    if viewing_other:
        if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
            return await _reply(message, ADMIN_DENY_TEXT)

    private = await is_balance_hidden(chat_id, target_id)
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
    from bot.tx_reports import (
        _format_match_tx_lines,
        _format_wallet_adjust_lines,
        _format_tx_description,
        _game_report_context,
        _parse_game_id,
        _parse_invite_id,
        _tx_label,
    )
    game_ids = [
        g for g in (_parse_game_id(getattr(t, "description", "") or "") for t in transactions) if g
    ]
    invite_ids = [
        i for i in (_parse_invite_id(getattr(t, "description", "") or "") for t in transactions) if i
    ]
    ctx = await _game_report_context(
        chat_id, target_id, game_ids, invite_ids=invite_ids,
    ) if (game_ids or invite_ids) else {
        "won": set(), "refunded": set(), "refund_kind": {},
        "refunded_invites": set(), "invite_kind": {}, "peers": {},
    }
    won_games = ctx.get("won") or set()
    refunded_games = ctx.get("refunded") or set()
    refund_kind = ctx.get("refund_kind") or {}
    refunded_invites = ctx.get("refunded_invites") or set()
    invite_kind = ctx.get("invite_kind") or {}
    peers_by_game = ctx.get("peers") or {}
    name_map: dict[int, str] = {}
    peer_uids = {pid for peers in peers_by_game.values() for pid in peers}
    for pid in peer_uids:
        try:
            member = await bot.get_chat_member(chat_id, pid)
            name_map[pid] = (member.user.full_name or member.user.first_name or str(pid)).strip()
        except Exception:
            name_map[pid] = str(pid)

    for t in transactions:
        j_time_str = jdatetime.datetime.fromgregorian(datetime=t.created_at).strftime("%Y/%m/%d - %H:%M")
        special = _format_wallet_adjust_lines(t, escape_html=True)
        if special is not None:
            for line in special:
                text += f"{line}\n"
        elif t.type in ("bet", "win"):
            for line in _format_match_tx_lines(
                t,
                won_games=won_games,
                refunded_games=refunded_games,
                refund_kind=refund_kind,
                refunded_invites=refunded_invites,
                invite_kind=invite_kind,
                peers_by_game=peers_by_game,
                name_map=name_map,
                escape_html=True,
            ):
                text += f"{line}\n"
        else:
            action, emoji = _tx_label(t.type)
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
            from bot.tx_reports import _format_tx_description
            for line in _format_tx_description(t.description, escape_html=True):
                text += f"{line}\n"
        text += f"   🕒 {j_time_str}\n\n"
    if total_pages > 1:
        text += f"💡 صفحه بعد: `گزارش {page + 1}`" if page < total_pages else ""

    kb = tx_report_kb(chat_id, target_id, page, total_pages) if private else None
    return await deliver_balance_sensitive(
        bot, chat_id, user_id, message.message_id, text,
        private=private,
        reply_markup=kb,
    )


@router.message(F.text.in_({
    "حق واسطه مخفی", "حق واسطه آشکار",
    "حق واسطه مخفی روشن", "حق واسطه مخفی خاموش",
}))
async def cmd_fee_visibility(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_owner(chat_id, user_id):
        return await _reply(message, "❌ فقط مالک گروه می‌تواند نمایش حق واسطه را تغییر دهد.")
    hidden = message.text in {"حق واسطه مخفی", "حق واسطه مخفی روشن"}
    await _set_fee_hidden(chat_id, hidden)
    if hidden:
        return await _reply(message, "✅ حق واسطه مخفی شد؛ از این پس فقط مالک گروه به آن دسترسی دارد.")
    return await _reply(message, "✅ حق واسطه برای مدیران گروه دوباره قابل مشاهده شد.")


@router.message(F.text.func(lambda t: parse_fee_report_command(t) is not None))
async def cmd_fee_report(message: Message, bot: Bot):
    from bot.panel_ui import can_see_fee
    if not can_see_fee(
        message.from_user.id,
        message.chat.id,
        fee_hidden=await _get_fee_hidden(message.chat.id),
    ):
        return await _reply(message, "❌ حق واسطه این گروه مخفی است و فقط مالک به آن دسترسی دارد.")

    delivery, mode, admin_target = parse_fee_report_command(message.text)
    if (
        mode == "a"
        and admin_target is None
        and message.reply_to_message
        and message.reply_to_message.from_user
    ):
        admin_target = message.reply_to_message.from_user.id
    return await send_fee_report(
        bot, message.chat.id, message.from_user.id, message.message_id, mode,
        delivery=delivery, admin_target=admin_target,
    )


@router.message(F.text.regexp(r"^(کارمزد|حق واسطه|نرخ کارمزد)(\s+\d+)?$"))
async def cmd_fee(message: Message, bot: Bot):
    if parse_fee_report_command(message.text) is not None:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    from bot.panel_ui import can_see_fee
    if not can_see_fee(user_id, chat_id, fee_hidden=await _get_fee_hidden(chat_id)):
        return await _reply(message, "❌ حق واسطه این گروه مخفی است و فقط مالک به آن دسترسی دارد.")
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


@router.message(F.text.regexp(r"^حالت بازی(\s+\S+)?$"))
async def cmd_bet_mode(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    arg = message.text[len("حالت بازی"):].strip().lower()
    if not arg:
        current = await _get_bet_mode(chat_id)
        label = _START_MODE_LABELS.get(current, current)
        return await _reply(message, (
            f"🎲 حالت بازی الان: {label}\n\n"
            f"تغییر:\n"
            f"• <code>حالت بازی فیکس</code>\n"
            f"• <code>حالت بازی اضافه</code>"
        ))
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    if arg not in _START_MODE_WORDS:
        return await _reply(message, (
            "❌ مقدار نامعتبر است.\n"
            "مثال: حالت بازی فیکس  |  حالت بازی اضافه"
        ))
    mode = _START_MODE_WORDS[arg]
    await _set_bet_mode(chat_id, mode)
    label = _START_MODE_LABELS[mode]
    detail = (
        "ورودی ثابت؛ حق واسطه از جایزه کم می‌شود."
        if mode == BET_MODE_FIXED
        else "ورودی = شرط + حق واسطه؛ برنده کل شرط را می‌گیرد."
    )
    return await _reply(message, (
        f"✅ حالت بازی گروه روی {label} تنظیم شد.\n\n"
        f"📌 {detail}\n\n"
        f"از این به بعد <code>شروع 2 50</code> با حالت {label} اجرا می‌شود.\n"
        f"همچنان می‌توانید صریح بزنید:\n"
        f"• <code>شروع 2 50 فیکس</code>\n"
        f"• <code>شروع 2 50 اضافه</code>"
    ))


@router.callback_query(F.data.startswith("txr:"))
async def cb_tx_report(call: CallbackQuery, bot: Bot):
    """دکمه‌های اینلاین گزارش تراکنش‌ها در پیوی."""
    parts = (call.data or "").split(":")
    if len(parts) != 4:
        return await call.answer("داده نامعتبر", show_alert=True)
    try:
        chat_id = int(parts[1])
        target_id = int(parts[2])
        page = max(1, int(parts[3]))
    except ValueError:
        return await call.answer("داده نامعتبر", show_alert=True)

    viewer_id = call.from_user.id
    if target_id != viewer_id and not is_admin(chat_id, viewer_id) and not is_owner(chat_id, viewer_id):
        return await call.answer(ADMIN_DENY_TEXT, show_alert=True)

    group_name = None
    try:
        chat = await bot.get_chat(chat_id)
        group_name = chat.title
    except Exception:
        pass

    text, total_pages = await build_tx_report_text(
        chat_id, bot, target_id, page, group_name=group_name,
    )
    kb = tx_report_kb(chat_id, target_id, page, total_pages)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await send_private(bot, call.from_user.id, text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("feer:"))
async def cb_fee_report(call: CallbackQuery, bot: Bot):
    """دکمه‌های اینلاین گزارش حق واسطه در پیوی."""
    parts = (call.data or "").split(":")
    if len(parts) != 3:
        return await call.answer("داده نامعتبر", show_alert=True)
    try:
        chat_id = int(parts[1])
    except ValueError:
        return await call.answer("گروه نامعتبر", show_alert=True)
    mode = parts[2]
    user_id = call.from_user.id

    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await call.answer(ADMIN_DENY_TEXT, show_alert=True)
    from bot.panel_ui import can_see_fee
    if not can_see_fee(user_id, chat_id, fee_hidden=await _get_fee_hidden(chat_id)):
        return await call.answer("حق واسطه مخفی است و فقط مالک دسترسی دارد.", show_alert=True)

    text = await build_fee_text_by_mode(chat_id, bot, mode)
    if not text:
        return await call.answer("نامعتبر", show_alert=True)

    kb = fee_report_kb(chat_id)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await send_private(bot, user_id, text, reply_markup=kb)
    await call.answer()


# ─── شماره کارت ──────────────────────────────────────────────────────────────

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_CARD_PREFIXES = ("افزودن کارت", "تنظیم کارت", "افزودن شماره کارت", "تنظیم شماره کارت")


@router.message(F.text.in_(["شماره کارت", "کارت"]))
async def cmd_card_self(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    own, adm, _ = get_user_status(chat_id, user_id)
    cashier = await active_cashier(chat_id)
    if own:
        text = await db_get_card(chat_id, user_id, "owner")
    elif adm:
        text = await db_get_card(chat_id, user_id, "admin")
    elif cashier:
        text = await db_get_card(chat_id, cashier, "admin")
    else:
        text = await db_get_card(chat_id, user_id, "owner")
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

@router.message(F.text.regexp(r"^شروع\s*پیوی"))
async def cmd_pv_start_setting(message: Message, bot: Bot):
    from bot.pv_dice import handle_pv_setting_command, ensure_sweeper
    await ensure_sweeper(bot)
    await handle_pv_setting_command(message, bot)


@router.message(F.text.regexp(r"^باخت\s*پیوی"))
async def cmd_pv_forfeit_setting(message: Message, bot: Bot):
    from bot.pv_dice import handle_pv_forfeit_setting_command, ensure_sweeper
    await ensure_sweeper(bot)
    await handle_pv_forfeit_setting_command(message, bot)


@router.message(F.text.regexp(r"^چت\s*پیوی\s+\S"))
async def cmd_pv_chat_setting(message: Message, bot: Bot):
    """چت پیوی روشن|خاموش|وضعیت — خودِ «چت پیوی» با ریپلای در handler جداست."""
    from bot.pv_dice import handle_pv_chat_setting_command, ensure_sweeper
    await ensure_sweeper(bot)
    await handle_pv_chat_setting_command(message, bot)


@router.message(F.text.regexp(r"^لغو\s*پیوی\s*$"))
async def cmd_admin_cancel_pv(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, ADMIN_DENY_TEXT)
    from bot.pv_dice import admin_cancel_pv_in_group, ensure_sweeper

    await ensure_sweeper(bot)
    player_id = None
    if message.reply_to_message:
        player_id = await get_target_from_reply(message, bot)
        if not player_id:
            return
    text = await admin_cancel_pv_in_group(bot, chat_id, player_id=player_id)
    return await _reply(message, text)


@router.message(F.text.regexp(r"^شروع\s+\d+.*پیوی[\s.….۔]*$"))
async def cmd_start_pv_duel(message: Message, bot: Bot):
    """چالش تاس دونفره در پیوی — برای همه اعضا."""
    from bot.pv_dice import (
        parse_pv_start_command, get_pv_start_settings, format_off_message,
        user_busy_label, format_pv_busy_message, create_invite, ensure_sweeper, MIN_BET,
        get_min_pv_bet, effective_min_pv_bet, format_min_pv_denial, format_min_pv_free_denial,
    )
    from bot.dice_game import has_active_game, BET_MODE_FIXED

    await ensure_sweeper(bot)
    chat_id = message.chat.id
    user_id = message.from_user.id
    parsed = parse_pv_start_command(normalize_numbers(message.text or ""))
    if not parsed:
        return
    if parsed.get("error") == "pv_only_2":
        return await _reply(message, "⚔️ چالش پیوی فقط برای ۲ نفر است.\nمثال: <code>شروع 2 100 پیوی</code>")
    if parsed.get("error") == "min_bet":
        group_min = await get_min_pv_bet(chat_id)
        eff = effective_min_pv_bet(group_min)
        return await _reply(message, f"❌ حداقل مبلغ بازی {eff:,} واحد است.")
    if parsed.get("error") == "bad_bet":
        return await _reply(message, "❌ مبلغ باید عدد باشد.\nمثال: <code>شروع 2 100 پیوی</code>")

    group_min = await get_min_pv_bet(chat_id)
    eff = effective_min_pv_bet(group_min)
    if not parsed.get("has_bet"):
        if int(group_min or 0) > 0:
            return await _reply(message, format_min_pv_free_denial(eff))
    elif int(parsed["bet_amount"]) < eff:
        return await _reply(
            message,
            format_min_pv_denial(eff, int(parsed["bet_amount"])),
        )

    cfg = await get_pv_start_settings(chat_id)
    if not cfg.get("enabled"):
        return await _reply(message, format_off_message(cfg.get("reason") or ""))

    if not message.reply_to_message:
        return await _reply(
            message,
            "↩️ روی پیام حریف ریپلای کنید و بنویسید:\n"
            "<code>شروع 2 100 پیوی</code>",
        )
    target_id = await get_target_from_reply(message, bot)
    if not target_id:
        return
    if int(target_id) == int(user_id):
        return await _reply(message, "❌ نمی‌توانید با خودتان بازی کنید.")

    my_busy = user_busy_label(user_id)
    if my_busy:
        return await _reply(message, format_pv_busy_message(my_busy, user_id=user_id))
    if has_active_game(chat_id):
        # اگر خود کاربر در بازی گروهی است — dice game is per-chat not per-user easily
        pass
    their_busy = user_busy_label(int(target_id))
    if their_busy:
        tag = await _mention(int(target_id), bot, chat_id)
        return await _reply(
            message,
            format_pv_busy_message(
                their_busy, for_other=True, other_name=tag, user_id=int(target_id),
            ),
        )

    # also block if target/self in group active game (player or lobby starter)
    from bot.dice_game import is_user_involved_in_group_game
    if is_user_involved_in_group_game(chat_id, user_id):
        return await _reply(message, "⚠️ شما در بازی گروهی این گپ هستید؛ اول آن را تمام کنید.")
    if is_user_involved_in_group_game(chat_id, int(target_id)):
        tag = await _mention(int(target_id), bot, chat_id)
        return await _reply(message, f"⏳ {tag} در بازی گروهی این گپ است؛ منتظر پایان باشید.")

    fee_percent = await _get_fee(chat_id) if parsed["has_bet"] else 0
    if parsed["has_bet"]:
        bet_mode = parsed["explicit_mode"] or await _get_bet_mode(chat_id)
        from bot.dice_game import calc_bet_costs
        from bot.finance import get_playable_balance, format_insufficient_balance_message

        costs = calc_bet_costs(int(parsed["bet_amount"]), int(fee_percent or 0), bet_mode, 2)
        entry = int(costs.get("entry") or 0)
        if entry > 0:
            fee_per = int(costs.get("fee_per") or 0)
            if bet_mode == BET_MODE_FIXED and fee_per > 0:
                fee_line = f"\n   └ حق واسطه ({fee_percent}٪): {fee_per:,} واحد (از جایزه)"
            elif fee_per > 0:
                fee_line = f"\n   ├ مبلغ بازی: {int(parsed['bet_amount']):,} واحد\n   └ حق واسطه: {fee_per:,} واحد"
            else:
                fee_line = ""
            mode_line = " (فیکس)" if bet_mode == BET_MODE_FIXED else " (اضافه)"
            fee_suffix = f"{mode_line}{fee_line}"

            total_bal, playable, pending = await get_playable_balance(chat_id, user_id)
            from bot.finance import spendable_for_games
            if spendable_for_games(playable, pending) < entry:
                return await _reply(
                    message,
                    format_insufficient_balance_message(
                        entry_cost=entry,
                        total_balance=total_bal,
                        playable=playable,
                        pending=pending,
                        fee_line=fee_suffix,
                    ),
                )

            t_total, t_playable, t_pending = await get_playable_balance(chat_id, int(target_id))
            if spendable_for_games(t_playable, t_pending) < entry:
                tag = await _mention(int(target_id), bot, chat_id)
                shortfall = entry - spendable_for_games(t_playable, t_pending)
                pending_line = (
                    f"\n⏳ موجودی در انتظار تسویه: {t_pending:,} واحد" if t_pending > 0 else ""
                )
                return await _reply(
                    message,
                    (
                        f"❌ موجودی حریف کافی نیست!\n\n"
                        f"👤 حریف: {tag}\n"
                        f"💳 هزینه ورودی: {entry:,} واحد{fee_suffix}\n\n"
                        f"💰 موجودی قابل‌استفاده حریف: {t_playable:,} واحد{pending_line}\n"
                        f"🔻 کمبود: {shortfall:,} واحد\n\n"
                        f"تا وقتی موجودی حریف به حد کافی نرسد، دعوت پیوی ارسال نمی‌شود."
                    ),
                )
    else:
        bet_mode = BET_MODE_FIXED

    challenger_name = await _mention(user_id, bot, chat_id)
    target_name = await _mention(int(target_id), bot, chat_id)
    # strip HTML for PV plain-ish names
    import re as _re
    ch_plain = _re.sub(r"<[^>]+>", "", challenger_name) or str(user_id)
    tg_plain = _re.sub(r"<[^>]+>", "", target_name) or str(target_id)

    invite_id = await create_invite(
        bot,
        group_id=chat_id,
        challenger_id=user_id,
        target_id=int(target_id),
        bet_amount=int(parsed["bet_amount"]),
        has_bet=bool(parsed["has_bet"]),
        bet_mode=bet_mode,
        fee_percent=int(fee_percent or 0),
        group_msg_id=message.message_id,
        challenger_name=ch_plain,
        target_name=tg_plain,
    )
    if not invite_id:
        return await _reply(
            message,
            "⚠️ الان نمی‌توان چالش فرستاد؛ شما یا حریف مشغول بازی/دعوت دیگری هستید "
            "یا در بازی گروهی هستید.",
        )


@router.message(F.text.regexp(r"^شروع\s+\d+"))
async def cmd_start_game(message: Message, bot: Bot):
    # اگر دستور پیوی باشد، هندلر تخصصی باید گرفته باشد؛ اینجا فقط گپ
    _start_parts = normalize_numbers(message.text or "").split()
    if _start_parts and _start_parts[-1].rstrip(".….۔") == "پیوی":
        return
    from bot.pv_dice import user_busy_label, format_pv_busy_message
    chat_id = message.chat.id
    user_id = message.from_user.id
    busy = user_busy_label(user_id)
    if busy:
        return await _reply(message, format_pv_busy_message(busy, user_id=user_id))
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        return await _reply(message, "شما دسترسی مجاز را ندارید")
    parts = normalize_numbers(message.text).split()
    explicit_mode = None
    if parts and parts[-1].lower() in _START_MODE_WORDS:
        explicit_mode = _START_MODE_WORDS[parts[-1].lower()]
        parts = parts[:-1]
    if len(parts) < 2:
        return await _reply(message, (
            "❌ فرمت صحیح:\n"
            "• شروع [تعداد] → بازی رایگان\n"
            "• شروع [تعداد] [مبلغ] → طبق حالت بازی گروه\n"
            "• شروع [تعداد] [مبلغ] فیکس → ورودی ثابت\n"
            "• شروع [تعداد] [مبلغ] اضافه → ورودی = شرط + حق واسطه\n"
            "• شروع 2 [مبلغ] پیوی → چالش دونفره در پیوی (با ریپلای)\n\n"
            "مثال‌ها:\n"
            "  شروع 2\n"
            "  شروع 2 50\n"
            "  شروع 2 50 فیکس\n"
            "  شروع 2 50 اضافه\n"
            "  شروع 2 100 پیوی"
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
                "مثال: شروع 2 50  |  شروع 2 50 فیکس  |  شروع 2 50 اضافه"
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
    if has_bet:
        bet_mode = explicit_mode if explicit_mode else await _get_bet_mode(chat_id)
    else:
        bet_mode = BET_MODE_FIXED
    starter_id = user_id
    game = create_game(
        chat_id, total_players,
        bet_amount=bet_amount, fee_percent=fee_percent,
        has_bet=has_bet, bet_mode=bet_mode if has_bet else BET_MODE_FIXED,
        starter_admin_id=starter_id,
    )
    if not game:
        from bot.dice_game import _pv_blocks_group_play
        pv_block = _pv_blocks_group_play(user_id)
        if pv_block:
            return await _reply(message, pv_block)
        return await _reply(message, (
            "⚠️ یک بازی فعال وجود دارد!\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📍 لطفاً صبر کنید تا بازی فعلی تمام شود.\n\n"
            "❌ یا برای توقف، دستور «لغو» را بزنید."
        ))
    mode_label = _START_MODE_LABELS.get(bet_mode, bet_mode)
    if has_bet:
        costs = calc_bet_costs(bet_amount, fee_percent, bet_mode, total_players)
        _entry = costs["entry"]
        _fee_per = costs["fee_per"]
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
                    f"\n🏆 مبلغ برد: {_prize:,} واحد"
                    f"\n💸 حق واسطه ({fee_percent}٪): {_total_fee:,} واحد (از جایزه)"
                )
            else:
                msg += f"\n🏆 مبلغ برد: {_prize:,} واحد"
        else:
            msg += f"\n   ├ شرط: {bet_amount:,} واحد"
            if fee_percent > 0:
                msg += (
                    f"\n   └ حق واسطه ({fee_percent}٪): {_fee_per:,} واحد"
                )
            msg += (
                f"\n\n🏆 مبلغ برد: {_prize:,} واحد"
                + (f"\n💸 جمع حق واسطه: {_total_fee:,} واحد" if fee_percent > 0 else "")
            )
        msg += (
            f"\n\n✅ برای شرکت «تاس» بفرست\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ مهلت ثبت‌نام: ۱۰ دقیقه\n"
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
            f"⏱️ مهلت ثبت‌نام: ۱۰ دقیقه\n"
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

    from bot.dice_game import WAITING_ROUNDS, GAME_PROGRESS
    from django.core.cache import cache as django_cache
    game = get_game(chat_id)
    had_state = bool(
        game
        or chat_id in GAME_PROGRESS
        or chat_id in WAITING_ROUNDS
        or django_cache.get(f"dice_finalizing_{chat_id}")
        or django_cache.get(f"dice_waiting_finalize_{chat_id}")
    )
    if not had_state:
        return await _reply(message, "❌ هیچ بازی فعالی برای لغو وجود ندارد!")

    total_players = game.get("total_players", 0) if game else 0
    players_count = len(game.get("players", [])) if game else 0
    status = game.get("status", "unknown") if game else "unknown"
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
            IKB(text="📅 امروز",  callback_data="dstat:daily"),
            IKB(text="📅 دیروز",  callback_data="dstat:yesterday"),
        ],
        [
            IKB(text="📆 هفتگی",  callback_data="dstat:weekly"),
            IKB(text="📊 کل",     callback_data="dstat:total"),
        ],
        [IKB(text="❌ بستن", callback_data="dstat:close")],
    ])


async def _build_dice_stats_text(chat_id: int, period: str, bot: Bot) -> str:
    from bot.dice_stats_fmt import format_dice_game_stats
    from bot.stat_prizes import get_group_prizes

    labels = {
        "daily": "🎲 آمار تاس · 📅 امروز",
        "yesterday": "🎲 آمار تاس · 📅 دیروز",
        "weekly": "🎲 آمار تاس · 📆 هفتگی",
        "total": "🎲 آمار تاس · 📊 کل",
    }
    title = labels.get(period, "🎲 آمار تاس")
    records = await db_fetch_dice_game_history(chat_id, period)
    if not records:
        return f"<b>{title}</b>\n\n📭 مسابقه‌ای ثبت نشده."

    user_ids = list({rec.telegram_user_id for rec in records})
    name_map = {}
    for uid in user_ids:
        try:
            member = await bot.get_chat_member(chat_id, uid)
            name_map[uid] = html.escape(member.user.full_name or member.user.first_name or str(uid))
        except Exception:
            name_map[uid] = f'<a href="tg://user?id={uid}">کاربر</a>'

    prizes = await get_group_prizes(chat_id) if period in ("daily", "yesterday") else {}
    return format_dice_game_stats(records, title, name_map, prizes=prizes)


@router.message(F.text.in_(["آمار تاس", "امار تاس", "آمار بازی", "امار بازی"]))
async def cmd_dice_stats(message: Message, bot: Bot):
    chat_id = message.chat.id
    text = "🎲 <b>آمار تاس</b>\n\nبازه زمانی رو انتخاب کن:"
    await safe_send(bot, chat_id, text,
                    reply_markup=_dice_stats_kb(), reply_to=message.message_id)


@router.message(F.text.in_(["آمار تاس روزانه", "امار تاس روزانه", "آمار تاس امروز", "امار تاس امروز"]))
async def cmd_dice_stats_daily(message: Message, bot: Bot):
    chat_id = message.chat.id
    text = await _build_dice_stats_text(chat_id, "daily", bot)
    await safe_send(bot, chat_id, text,
                    reply_markup=_dice_stats_kb(), reply_to=message.message_id)


@router.message(F.text.in_(["تست آمار تاس", "امار تاس تست", "آمار تاس تست", "تست امار تاس"]))
async def cmd_dice_stats_midnight_test(message: Message, bot: Bot):
    """فرض می‌کند الان ۱۲ شب است — آمار امروز + جوایز برای همین گروه."""
    chat_id = message.chat.id
    uid = message.from_user.id
    if not is_owner(chat_id, uid):
        return await _reply(message, "❌ این دستور فقط برای مالک گپ است.")
    from bot.midnight_stats import run_midnight_stats_test
    await _reply(message, "⏳ در حال اجرای تست آمار نیمه‌شب...")
    result = await run_midnight_stats_test(bot, chat_id)
    await _reply(message, result)


@router.message(F.text.in_(["آمار تاس دیروز", "امار تاس دیروز", "آمار بازی دیروز", "امار بازی دیروز"]))
async def cmd_dice_stats_yesterday(message: Message, bot: Bot):
    chat_id = message.chat.id
    text = await _build_dice_stats_text(chat_id, "yesterday", bot)
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


async def _build_my_dice_stats_text(chat_id: int, user_id: int, period: str, bot: Bot) -> str:
    from bot.dice_stats_fmt import format_my_dice_stats
    import jdatetime
    from django.utils import timezone

    now = timezone.localtime()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "yesterday":
        day = today_start - __import__("datetime").timedelta(days=1)
        date_label = jdatetime.datetime.fromgregorian(datetime=day).strftime("%Y/%m/%d")
        title = f"🎲 آمار تاس من · 📅 دیروز ({date_label})"
    else:
        date_label = jdatetime.datetime.fromgregorian(datetime=today_start).strftime("%Y/%m/%d")
        title = f"🎲 آمار تاس من · 📅 امروز ({date_label})"

    records = await db_fetch_user_dice_game_history(chat_id, user_id, period)
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        user_label = html.escape(member.user.full_name or member.user.first_name or str(user_id))
    except Exception:
        user_label = f'<a href="tg://user?id={user_id}">شما</a>'
    return format_my_dice_stats(records, title, user_label)


@router.message(F.text.in_(["آمار تاس من", "امار تاس من", "آمار بازی من", "امار بازی من"]))
async def cmd_dice_stats_me(message: Message, bot: Bot):
    chat_id = message.chat.id
    text = await _build_my_dice_stats_text(chat_id, message.from_user.id, "daily", bot)
    await safe_send(bot, chat_id, text, reply_to=message.message_id)


@router.message(F.text.in_(["آمار تاس دیروز من", "امار تاس دیروز من", "آمار بازی دیروز من", "امار بازی دیروز من"]))
async def cmd_dice_stats_me_yesterday(message: Message, bot: Bot):
    chat_id = message.chat.id
    text = await _build_my_dice_stats_text(chat_id, message.from_user.id, "yesterday", bot)
    await safe_send(bot, chat_id, text, reply_to=message.message_id)


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

    # تاس خاموش → فقط وقتی بازی/چالش race فعال نیست بلاک شود
    game = get_game(chat_id)
    dice_game_active = has_active_game(chat_id) or (
        game and game.get("status") in ("waiting", "playing")
    )
    if not dice_game_active:
        group_cmds = get_group_commands(chat_id)
        if "تاس" not in group_cmds:
            from bot.challenges import has_active_race_challenge
            if await has_active_race_challenge(chat_id, "dice"):
                pass  # چالش تاس فعال — اجازه بده
            else:
                from bot.helpers import quiet_extra_on
                if quiet_extra_on(chat_id):
                    return
                return await _reply(message, "این قابلیت توسط ادمین گروه غیرفعال شده است.")

    theme_id = get_group_theme(chat_id)
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
        # تاس خاموش و بدون بازی → نادیده
        game = get_game(chat_id)
        dice_game_active = has_active_game(chat_id) or (
            game and game.get("status") in ("waiting", "playing")
        )
        if not dice_game_active:
            group_cmds = get_group_commands(chat_id)
            if "تاس" not in group_cmds:
                from bot.challenges import has_active_race_challenge
                if not await has_active_race_challenge(chat_id, "dice"):
                    return

        LAST_DICE[chat_id] = value
        await db_record_dice_roll(chat_id, user_id, value)

        game = get_game(chat_id)
        if game and game.get("status") == "playing":
            claimed, remaining, err = claim_roll_slots(chat_id, user_id, 1)
            if not claimed:
                await bot.send_message(chat_id, err, reply_to_message_id=message.message_id)
                return
            await _handle_game_roll_silent(
                chat_id, user_id, 1, value, message.message_id, bot, slots_claimed=True,
            )
            return

        # بازی تعیین (waiting)
        if has_active_game(chat_id):
            should_cont, _join_note = await should_continue(chat_id, user_id, bot, message.message_id, "تاس")
            if should_cont == 0:
                return
            if should_cont == 2:
                # اول تم تاس مثل متن، بعد ثبت‌نام کامل
                try:
                    from bot.dice_themes import get_theme, build_single_dice_message
                    from bot.helpers import get_group_theme, safe_send
                    theme = get_theme(get_group_theme(chat_id))
                    await safe_send(
                        bot, chat_id,
                        build_single_dice_message(int(value), theme),
                        reply_to=message.message_id,
                    )
                except Exception:
                    pass
                await asyncio.sleep(0.4)
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
