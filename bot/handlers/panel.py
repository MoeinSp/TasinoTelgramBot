"""
هندلر پنل — ناوبری و اجرای دستورات
"""
import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton as Btn

from bot import cache
from bot.cache_manager import has_privilege, is_owner
from bot.constants import CREATOR_USER_ID
from bot.panel_keyboards import (
    get_static_panel, panel_main, is_live_page,
    locks_panel_text, locks_panel_kb,
    settings_panel_text, settings_panel_kb,
    game_panel_text, game_panel_kb,
    games_panel_text, games_panel_kb,
    fun_panel_text, fun_panel_kb,
    manage_panel_text, manage_panel_kb,
    finance_panel_text, finance_panel_kb,
    panel_header, FUN_CMD_SET,
)
from bot.group_help import PAGE_MAIN

router = Router()
_log = logging.getLogger(__name__)
_GROUP_JOIN_STATE: dict[int, int] = {}

# صفحه‌ای که بعد از toggle باید رفرش شود
_TOGGLE_PAGE = {
    "welcome": "settings", "captcha": "settings", "flood": "settings",
    "antiraid": "settings", "bot": "settings",
    "speaker": "game", "tg_emoji": "game", "dice_option": "game",
    "group_lock": "locks",
}


def _is_pv(call: CallbackQuery) -> bool:
    return call.message.chat.type == "private"


def _panel_chat_id(call: CallbackQuery) -> int | None:
    """در گروه = chat فعلی؛ در پیوی = گروه انتخاب‌شده."""
    if _is_pv(call):
        return cache.PV_PANEL_GROUP.get(call.from_user.id)
    return call.message.chat.id


def _can_manage_panel(call: CallbackQuery, chat_id: int) -> bool:
    user_id = call.from_user.id
    if user_id == CREATOR_USER_ID:
        return True
    if _is_pv(call):
        return is_owner(chat_id, user_id)
    return has_privilege(chat_id, user_id)


def _with_pv_nav(kb: InlineKeyboardMarkup, is_pv: bool) -> InlineKeyboardMarkup:
    if not is_pv or kb is None:
        return kb
    rows = [list(r) for r in kb.inline_keyboard]
    # جلوگیری از تکرار دکمه لیست گروه‌ها
    if any(
        getattr(btn, "callback_data", None) == "gs:list"
        for row in rows for btn in row
    ):
        return kb
    rows.append([Btn(text="🔙 لیست گروه‌ها", callback_data="gs:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _fetch_locks(chat_id: int) -> dict:
    locks = cache.GROUP_LOCKS.get(chat_id, {})
    if not locks:
        from bot.helpers import db_get_locks
        locks = await db_get_locks(chat_id)
    return locks


async def _group_snapshot(chat_id: int) -> dict:
    from bot.helpers import db_get_group_fee, db_get_group_theme, db_get_group_commands
    enabled = await db_get_group_commands(chat_id)
    return {
        "bot": chat_id not in cache.OFF_GROUP,
        "welcome": chat_id not in cache.WELCOME_DISABLED,
        "captcha": chat_id in cache.CAPTCHA_ENABLED,
        "flood": chat_id in cache.ANTI_FLOOD_ENABLED,
        "antiraid": chat_id in cache.ANTIRAID_ENABLED,
        "speaker": chat_id in cache.SPEAKER_ON,
        "tg_emoji": chat_id in cache.TELEGRAM_EMOJI_ON,
        "dice_option": chat_id in cache.DICE_OPTION,
        "group_lock": chat_id in cache.GROUP_LOCK,
        "night": cache.NIGHT_MODE.get(chat_id),
        "theme": await db_get_group_theme(chat_id),
        "fee": await db_get_group_fee(chat_id),
        "enabled_commands": set(enabled),
    }


async def _render_live_panel(code: str, chat_id: int):
    snap = await _group_snapshot(chat_id)
    if code in ("locks", "1", "1.1"):
        locks = await _fetch_locks(chat_id)
        return locks_panel_text(locks, snap["group_lock"]), locks_panel_kb(locks, snap["group_lock"])
    if code == "settings":
        return settings_panel_text(snap), settings_panel_kb(snap)
    if code == "game":
        return game_panel_text(snap), game_panel_kb(snap)
    if code == "games":
        enabled = snap["enabled_commands"]
        return games_panel_text(enabled), games_panel_kb(enabled)
    if code == "fun":
        enabled = snap["enabled_commands"]
        return fun_panel_text(enabled), fun_panel_kb(enabled)
    if code == "manage":
        return manage_panel_text(), manage_panel_kb()
    if code == "finance":
        return finance_panel_text(), finance_panel_kb()
    if code == "group_join":
        from bot.group_forced_join import get_group_target
        cfg = await get_group_target(chat_id)
        status = f"🟢 {cfg['title']}\n{cfg['link']}" if cfg else "⚫ تنظیم نشده"
        text = f"🔗 <b>جوین اجباری گروه</b>\n\n{status}\n\nهر گروه حداکثر یک لینک دارد؛ جوین سازنده جداگانه اعمال می‌شود."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [Btn(text="➕ تنظیم/جایگزینی لینک", callback_data="gfj:set")],
            [Btn(text="🗑 حذف لینک", callback_data="gfj:clear")],
            [Btn(text="🔙 بازگشت", callback_data="p:manage")],
        ])
        return text, kb
    return None, None


# ─── ناوبری ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("p:"))
async def cb_panel(call: CallbackQuery):
    user_id = call.from_user.id
    is_pv = _is_pv(call)
    chat_id = _panel_chat_id(call)

    if is_pv and not chat_id:
        await call.answer("ابتدا از «تنظیمات گروه» یک گروه انتخاب کنید.", show_alert=True)
        return

    if not chat_id or not _can_manage_panel(call, chat_id):
        await call.answer("❌ شما دسترسی ندارید.", show_alert=True)
        return

    code = call.data[2:]

    if code == "close":
        if is_pv:
            cache.PV_PANEL_GROUP.pop(user_id, None)
        try:
            await call.message.delete()
        except Exception:
            pass
        return

    if code == "noop":
        await call.answer()
        return

    if code in ("0", ""):
        text, kb = PAGE_MAIN, panel_main(pv=is_pv)
        if is_pv:
            title = cache.PV_PANEL_GROUP.get(user_id)
            # نام گروه را اگر در کش پیام قبلی بود نگه نمی‌داریم؛ از DB می‌گیریم
            from asgiref.sync import sync_to_async
            @sync_to_async
            def _gname(cid):
                from account.models import TelegramGroup
                g = TelegramGroup.objects.filter(telegram_chat_id=cid).first()
                return (g.name if g and g.name else None) or str(cid)
            gname = await _gname(chat_id)
            text = (
                f"⚙️ <b>پنل تنظیمات</b>\n"
                f"🏷 گروه: <b>{gname}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{PAGE_MAIN}"
            )
    elif is_live_page(code) or code == "group_join":
        text, kb = await _render_live_panel(code, chat_id)
        if text is None:
            await call.answer("❌ بخش یافت نشد", show_alert=True)
            return
        kb = _with_pv_nav(kb, is_pv)
    else:
        text, kb = get_static_panel(code, pv=is_pv)
        if text is None:
            await call.answer("❌ بخش یافت نشد", show_alert=True)
            return
        kb = _with_pv_nav(kb, is_pv)

    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        _log.error("panel edit: %s", e)
    await call.answer()


@router.callback_query(F.data.startswith("gfj:"))
async def cb_group_forced_join(call: CallbackQuery, bot: Bot):
    action = call.data[4:]
    if action.startswith("check:"):
        from bot.group_forced_join import missing_targets, required_text, keyboard, send_temporary
        group_id = int(action.split(":", 1)[1])
        targets, missing = await missing_targets(bot, group_id, call.from_user.id)
        if missing:
            await call.answer("هنوز همه عضویت‌ها کامل نشده است.", show_alert=True)
            try:
                await call.message.edit_text(required_text(call.from_user.full_name, missing), reply_markup=keyboard(group_id, missing), parse_mode="HTML")
            except Exception:
                pass
        else:
            await call.answer("عضویت تأیید شد ✅")
            await send_temporary(call.message, f"✅ عضویت {call.from_user.full_name} در همه لینک‌ها تأیید شد.")
            try:
                await call.message.delete()
            except Exception:
                pass
        return

    chat_id = _panel_chat_id(call)
    if not chat_id or (call.from_user.id != CREATOR_USER_ID and not is_owner(chat_id, call.from_user.id)):
        return await call.answer("فقط مالک گروه می‌تواند جوین اجباری را تغییر دهد.", show_alert=True)
    if action == "set":
        _GROUP_JOIN_STATE[call.from_user.id] = chat_id
        await call.message.answer("لینک عمومی کانال یا @username را بفرستید. ربات باید در کانال مقصد ادمین باشد.")
        return await call.answer("منتظر لینک...")
    if action == "clear":
        from bot.group_forced_join import clear_group_target
        await clear_group_target(chat_id)
        await call.message.answer("🗑 جوین اجباری این گروه حذف شد.")
        return await call.answer("حذف شد")


@router.message(F.text, F.func(lambda m: bool(m.from_user) and m.from_user.id in _GROUP_JOIN_STATE))
async def set_group_forced_join_from_panel(message, bot: Bot):
    chat_id = _GROUP_JOIN_STATE.pop(message.from_user.id)
    from bot.group_forced_join import resolve_target, save_group_target
    try:
        target = await resolve_target(bot, message.text)
        await save_group_target(chat_id, target.channel_id, target.title, target.link)
        await message.answer(f"✅ جوین اجباری گروه تنظیم شد:\n{target.title}\n{target.link}")
    except Exception as exc:
        await message.answer(f"❌ تنظیم نشد: {exc}")


# ─── لینک‌ساز ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("lnk:"))
async def cb_link(call: CallbackQuery, bot: Bot):
    action = call.data[4:]
    chat_id = _panel_chat_id(call)
    is_pv = _is_pv(call)

    if is_pv and not chat_id:
        await call.answer("ابتدا گروه را انتخاب کنید.", show_alert=True)
        return
    if not chat_id:
        chat_id = call.message.chat.id

    if action in ("close", "noop"):
        try:
            if action == "close":
                await call.message.delete()
        except Exception:
            pass
        await call.answer()
        return

    import datetime
    text = None

    if action == "me":
        user = call.from_user
        if user.username:
            text = f"👤 لینک پروفایل:\nt.me/{user.username}"
        else:
            text = f"👤 لینک پروفایل:\ntg://user?id={user.id}"
    elif action == "bot":
        me = await bot.get_me()
        text = f"🤖 لینک ربات:\nt.me/{me.username}"
    else:
        _CFG = {
            "invite": (dict(), "🔗", "لینک دعوت"),
            "once": (dict(member_limit=1), "🔒", "یک‌بارمصرف"),
            "h24": (dict(expire_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)), "⏰", "۲۴ ساعته"),
            "d7": (dict(expire_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)), "📅", "۷ روزه"),
            "approval": (dict(creates_join_request=True), "✅", "با تایید ادمین"),
            "limit10": (dict(member_limit=10), "👥", "محدود ۱۰ نفر"),
        }
        cfg = _CFG.get(action)
        if cfg:
            kwargs, icon, label = cfg
            try:
                result = await bot.create_chat_invite_link(chat_id, **kwargs)
                text = f"{icon} {label}:\n{result.invite_link}"
            except Exception as e:
                text = f"❌ خطا:\n{e}"

    if text:
        dest = call.message.chat.id if is_pv else chat_id
        reply_to = None if is_pv else call.message.message_id
        await bot.send_message(dest, text, reply_to_message_id=reply_to, parse_mode="HTML")
    await call.answer()


# ─── دستورات ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cmd:"))
async def cb_cmd(call: CallbackQuery, bot: Bot):
    action = call.data[4:]
    user_id = call.from_user.id
    is_pv = _is_pv(call)
    chat_id = _panel_chat_id(call)

    if is_pv and not chat_id:
        await call.answer("ابتدا از «تنظیمات گروه» یک گروه انتخاب کنید.", show_alert=True)
        return

    if not chat_id or not _can_manage_panel(call, chat_id):
        await call.answer("❌ فقط ادمین‌ها", show_alert=True)
        return

    # toggle قفل تکی
    if action.startswith("lock_toggle_"):
        toast = await _toggle_lock(action[12:], chat_id)
        text, kb = await _render_live_panel("locks", chat_id)
        kb = _with_pv_nav(kb, is_pv)
        try:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            _log.error("locks refresh: %s", e)
        await call.answer(toast)
        return

    # toggle دستور بازی/سرگرمی
    if action.startswith("tglc:"):
        cmd_name = action[5:]
        from bot.panel_keyboards import ALL_TOGGLEABLE_CMDS
        if cmd_name not in ALL_TOGGLEABLE_CMDS:
            await call.answer("❌ نامعتبر", show_alert=True)
            return
        from bot.helpers import db_toggle_group_command
        on = await db_toggle_group_command(chat_id, cmd_name)
        page = "fun" if cmd_name in FUN_CMD_SET else "games"
        text, kb = await _render_live_panel(page, chat_id)
        kb = _with_pv_nav(kb, is_pv)
        try:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            _log.error("cmd toggle refresh: %s", e)
        await call.answer(f"{'🟢' if on else '⚫'} {cmd_name}")
        return

    # toggle ویژگی‌ها (خوشامد، کپچا، ...)
    if action.startswith("tgl_"):
        key = action[4:]
        toast = await _toggle_feature(key, chat_id, bot)
        page = _TOGGLE_PAGE.get(key, "settings")
        text, kb = await _render_live_panel(page, chat_id)
        kb = _with_pv_nav(kb, is_pv)
        try:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            _log.error("toggle refresh: %s", e)
        await call.answer(toast or "✅")
        return

    text = await _execute(action, chat_id, user_id, bot)
    if text:
        # در پیوی نتیجه را در همان چت نشان بده؛ در گروه به خود گروه
        dest = call.message.chat.id if is_pv else chat_id
        reply_to = call.message.message_id if not is_pv else None
        await bot.send_message(dest, text, reply_to_message_id=reply_to, parse_mode="HTML")
    await call.answer()


async def _toggle_lock(lock_key: str, chat_id: int) -> str:
    from bot.helpers import LOCK_NAMES, db_update_lock
    if lock_key not in LOCK_NAMES:
        return "❌ نامعتبر"
    locks = await _fetch_locks(chat_id)
    new_state = not bool(locks.get(lock_key))
    await db_update_lock(chat_id, lock_key, new_state)
    icon = "🔒" if new_state else "🔓"
    return f"{icon} {LOCK_NAMES[lock_key]}"


async def _toggle_feature(key: str, chat_id: int, bot: Bot) -> str:
    from bot.helpers import (
        db_set_welcome, db_set_captcha, db_set_anti_flood, db_set_antiraid,
        db_enable_speaker, db_disable_speaker,
        db_enable_group_off, db_disable_group_off,
        db_set_telegram_emoji, db_enable_group_lock, db_disable_group_lock,
    )

    labels = {
        "welcome": "خوشامد", "captcha": "کپچا", "flood": "آنتی‌فلود",
        "antiraid": "ضد رید", "bot": "ربات", "speaker": "سخنگو",
        "tg_emoji": "ایموجی تلگرام", "group_lock": "قفل کل گروه",
        "dice_option": "تاس متوالی",
    }
    label = labels.get(key, key)

    if key == "welcome":
        on = chat_id not in cache.WELCOME_DISABLED
        if on:
            cache.WELCOME_DISABLED.add(chat_id)
            await db_set_welcome(chat_id, enabled=False)
        else:
            cache.WELCOME_DISABLED.discard(chat_id)
            await db_set_welcome(chat_id, enabled=True)
        on = not on

    elif key == "captcha":
        on = chat_id in cache.CAPTCHA_ENABLED
        if on:
            cache.CAPTCHA_ENABLED.discard(chat_id)
            await db_set_captcha(chat_id, enabled=False)
            for (cid, uid), pending in list(cache.PENDING_CAPTCHA.items()):
                if cid != chat_id:
                    continue
                cache.PENDING_CAPTCHA.pop((cid, uid), None)
                pending["task"].cancel()
                try:
                    await bot.delete_message(cid, pending["message_id"])
                except Exception:
                    pass
        else:
            cache.CAPTCHA_ENABLED.add(chat_id)
            await db_set_captcha(chat_id, enabled=True)
        on = not on

    elif key == "flood":
        on = chat_id in cache.ANTI_FLOOD_ENABLED
        if on:
            cache.ANTI_FLOOD_ENABLED.discard(chat_id)
            await db_set_anti_flood(chat_id, enabled=False)
        else:
            cache.ANTI_FLOOD_ENABLED.add(chat_id)
            await db_set_anti_flood(chat_id, enabled=True)
        on = not on

    elif key == "antiraid":
        on = chat_id in cache.ANTIRAID_ENABLED
        if on:
            cache.ANTIRAID_ENABLED.discard(chat_id)
            await db_set_antiraid(chat_id, False)
        else:
            cache.ANTIRAID_ENABLED.add(chat_id)
            await db_set_antiraid(chat_id, True)
        on = not on

    elif key == "bot":
        on = chat_id not in cache.OFF_GROUP
        if on:
            cache.OFF_GROUP.add(chat_id)
            await db_enable_group_off(chat_id)
        else:
            cache.OFF_GROUP.discard(chat_id)
            await db_disable_group_off(chat_id)
        on = not on

    elif key == "speaker":
        on = chat_id in cache.SPEAKER_ON
        if on:
            cache.SPEAKER_ON.discard(chat_id)
            await db_disable_speaker(chat_id)
        else:
            cache.SPEAKER_ON.add(chat_id)
            await db_enable_speaker(chat_id)
        on = not on

    elif key == "tg_emoji":
        on = chat_id in cache.TELEGRAM_EMOJI_ON
        if on:
            cache.TELEGRAM_EMOJI_ON.discard(chat_id)
            await db_set_telegram_emoji(chat_id, False)
        else:
            cache.TELEGRAM_EMOJI_ON.add(chat_id)
            await db_set_telegram_emoji(chat_id, True)
        on = not on

    elif key == "group_lock":
        on = chat_id in cache.GROUP_LOCK
        if on:
            await db_disable_group_lock(chat_id)
        else:
            await db_enable_group_lock(chat_id)
        on = not on

    elif key == "dice_option":
        from bot.helpers import db_enable_dice_option, db_disable_dice_option
        on = chat_id in cache.DICE_OPTION
        if on:
            await db_disable_dice_option(chat_id)
        else:
            await db_enable_dice_option(chat_id)
        on = not on

    else:
        return "❌"

    return f"{'🟢' if on else '⚫'} {label}"


async def _execute(action: str, chat_id: int, user_id: int, bot: Bot) -> str:
    from bot.helpers import (
        db_get_admins, db_get_vips, db_clear_vips,
        db_get_learned_responses, db_get_word_filters,
        db_get_top_users, db_get_member, db_get_alias,
        db_get_group_fee, db_get_group_theme, db_set_telegram_emoji,
        sync_telegram_roles, sync_bot_admins_from_telegram, user_mention_id,
    )

    if action == "admin_list":
        admins = await db_get_admins(chat_id)
        if not admins:
            return "👮 هیچ ادمینی ثبت نشده."
        lines = [f"  • <a href='tg://user?id={uid}'>{uid}</a>" for uid in admins]
        return "👮 لیست ادمین‌ها:\n\n" + "\n".join(lines)

    if action == "sync_admins":
        result = await sync_telegram_roles(chat_id, bot)
        if not result.get("ok"):
            return f"❌ خطا: {result.get('error')}"
        count = await sync_bot_admins_from_telegram(chat_id, bot, result.get("creator_id"))
        return f"🔄 همگام‌سازی انجام شد — مالک + {count} ادمین"

    if action == "owner_info":
        result = await sync_telegram_roles(chat_id, bot)
        if not result.get("ok"):
            return f"❌ خطا: {result.get('error')}"
        owner_id = result.get("creator_id")
        if not owner_id:
            return "👑 مالک گروه یافت نشد."
        owner_mention = await user_mention_id(owner_id, bot, chat_id)
        return (
            "👑 مالک گروه:\n"
            f"{owner_mention}\n\n"
            f"انتقال: از تنظیمات تلگرام"
        )

    if action == "vip_list":
        vips = await db_get_vips(chat_id)
        if not vips:
            return "⭐ لیست ویژه خالی است."
        lines = [f"  • <a href='tg://user?id={uid}'>{uid}</a>" for uid in vips]
        return "⭐ اعضای ویژه:\n\n" + "\n".join(lines)

    if action == "vip_clear":
        await db_clear_vips(chat_id)
        return "🗑 لیست ویژه پاک شد."

    if action == "ban_list":
        from bot.handlers.main_group import _get_banned_from_db, _count_banned
        total = await _count_banned(chat_id)
        if total == 0:
            return "🚫 لیست بن خالی است."
        bans = await _get_banned_from_db(chat_id)
        lines = [f"  • <a href='tg://user?id={uid}'>{uid}</a>" for uid in bans]
        text = "🚫 لیست بن:\n\n" + "\n".join(lines)
        if total > len(bans):
            text += f"\n\n📌 +{total - len(bans)} نفر دیگر"
        return text

    if action == "mute_list":
        muted = cache.MUTED_USERS.get(chat_id, set())
        if not muted:
            return "🤫 کسی ساکت نشده."
        lines = [f"  • <a href='tg://user?id={uid}'>{uid}</a>" for uid in muted]
        return "🤫 لیست سکوت:\n\n" + "\n".join(lines)

    if action == "tag_all":
        return "📣 برای تگ همه بنویس:  تگ"

    if action == "my_warnings":
        member = await db_get_member(chat_id, user_id)
        return f"⚠️ اخطارهای شما: {member.warnings if member else 0}"

    if action == "dice_stats":
        return "📊 برای آمار تاس بنویس:  آمار تاس"

    _game_map = {
        "basketball": "🏀 بسکتبال", "penalty": "⚽ پنالتی", "bowling": "🎳 بولینگ",
        "dart": "🎯 دارت", "slots": "🎰 اسلات", "coin": "🪙 سکه",
        "luck": "🍀 شانس", "rps": "✂️ سنگ کاغذ قیچی",
    }
    if action in _game_map:
        label = _game_map[action]
        cmd = label.split(" ", 1)[1]
        return f"{label}\n\nبرای بازی بنویس:  {cmd}"

    if action == "top_users":
        users = await db_get_top_users(chat_id, limit=10)
        if not users:
            return "📊 هنوز آماری ثبت نشده."
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, u in enumerate(users):
            medal = medals[i] if i < 3 else f"{i+1}."
            name = u.alias or str(u.telegram_user_id)
            lines.append(f"{medal} {name} — {u.message_count} پیام")
        return "🏆 برترین کاربران:\n\n" + "\n".join(lines)

    if action == "learn_list":
        learns = cache.LEARNED_RESPONSES.get(chat_id) or await db_get_learned_responses(chat_id)
        if not learns:
            return "📚 هیچ پاسخی یاد نگرفته."
        lines = [f"  • {k} ← {v}" for k, v in list(learns.items())[:20]]
        return "📚 یادگیری:\n\n" + "\n".join(lines)

    if action == "group_status":
        snap = await _group_snapshot(chat_id)
        cfg = cache.ANTI_FLOOD_SETTINGS.get(chat_id, {"limit": 5, "window": 10})
        timeout = cache.CAPTCHA_TIMEOUT.get(chat_id, 180)
        night = snap.get("night")
        return (
            "📊 <b>جزئیات گروه</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 ربات: {'🟢 فعال' if snap['bot'] else '⚫ خاموش'}\n"
            f"🔐 قفل کل: {'🔒 بسته' if snap['group_lock'] else '🔓 باز'}\n"
            f"🎉 خوشامد: {'🟢' if snap['welcome'] else '⚫'}\n"
            f"🔐 کپچا: {'🟢' if snap['captcha'] else '⚫'}"
            + (f" ({timeout}s)" if snap['captcha'] else "") + "\n"
            f"🚫 فلود: {'🟢' if snap['flood'] else '⚫'}"
            + (f" — {cfg['limit']}/{cfg['window']}s" if snap['flood'] else "") + "\n"
            f"🚨 ضد رید: {'🟢' if snap['antiraid'] else '⚫'}\n"
            f"🔊 سخنگو: {'🟢' if snap['speaker'] else '⚫'}\n"
            f"🎮 ایموجی: {'🟢' if snap['tg_emoji'] else '⚫'}\n"
            f"🎲 تاس متوالی: {'🟢' if snap['dice_option'] else '⚫'}\n"
            f"🌙 شب: {f'{night[0]}:00–{night[1]}:00' if night else '⚫ خاموش'}\n"
            f"🎨 تم تاس: {snap['theme']}\n"
            f"💹 حق واسطه: {snap['fee']}٪"
        )

    if action == "my_balance":
        member = await db_get_member(chat_id, user_id)
        return f"👛 موجودی شما: {(member.point if member else 0):,} تومان"

    if action == "accounts":
        return "📊 برای لیست حساب‌ها بنویس:  حساب ها"

    if action == "report":
        return "📑 برای گزارش بنویس:  گزارش"

    if action == "settle_me":
        return "🤝 برای تسویه بنویس:  تسویه"

    if action == "card_show":
        return "💳 برای کارت بنویس:  شماره کارت"

    if action == "fee_show":
        fee = await db_get_group_fee(chat_id)
        return f"💹 حق واسطه: {fee}٪\n\nتغییر: <code>حق واسطه 10</code>"

    if action == "dice_theme":
        theme = await db_get_group_theme(chat_id)
        from bot.dice_themes import max_theme_id
        return (
            f"🎨 تم تاس: {theme}\n\n"
            f"تغییر: <code>تاس تم 4</code>\n"
            f"تم‌های موجود تا شماره {max_theme_id()}"
        )

    if action == "filter_list":
        filters = cache.WORD_FILTERS.get(chat_id) or await db_get_word_filters(chat_id)
        if not filters:
            return "🔤 فیلتری ثبت نشده.\n\nافزودن: <code>کلمه فیلتر [کلمه]</code>"
        words = [f"  • {w}" for w in list(filters)[:20]]
        return "🔤 فیلترها:\n\n" + "\n".join(words)

    if action == "my_alias":
        alias = await db_get_alias(chat_id, user_id)
        if alias:
            return f"🏷 لقب شما: <b>{alias}</b>"
        return "🏷 لقبی ندارید.\n\nثبت: <code>لقب [نام]</code>"

    return f"⚙️ «{action}» اجرا شد."
