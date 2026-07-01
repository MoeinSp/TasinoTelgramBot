"""
هندلر پنل — ناوبری و اجرای دستورات
"""
import logging
import secrets

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from bot import cache
from bot.cache_manager import is_admin, is_owner, has_privilege
from bot.panel_keyboards import get_panel, panel_main
from bot.group_help import PAGE_MAIN

router = Router()
_log = logging.getLogger(__name__)


# ─── ناوبری ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("p:"))
async def cb_panel(call: CallbackQuery):
    code = call.data[2:]

    if code == "close":
        try:
            await call.message.delete()
        except Exception:
            pass
        return

    if code == "noop":
        await call.answer()
        return

    if code in ("0", ""):
        text, kb = PAGE_MAIN, panel_main()
    else:
        text, kb = get_panel(code)
        if text is None:
            await call.answer("❌ بخش یافت نشد", show_alert=True)
            return

    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        _log.error("panel edit: %s", e)
    await call.answer()


# ─── لینک‌ساز ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("lnk:"))
async def cb_link(call: CallbackQuery, bot: Bot):
    action  = call.data[4:]
    chat_id = call.message.chat.id
    user_id = call.from_user.id

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
            text = f"👤 لینک پروفایل شما:\nt.me/{user.username}"
        else:
            text = f"👤 لینک پروفایل شما (بدون یوزرنیم):\ntg://user?id={user.id}"

    elif action == "bot":
        me = await bot.get_me()
        text = f"🤖 لینک ربات:\nt.me/{me.username}"

    else:
        # همه لینک‌های گروه
        _CFG = {
            "invite":   (dict(),                                                  "🔗", "لینک دعوت عادی"),
            "once":     (dict(member_limit=1),                                    "🔒", "لینک یک‌بار‌مصرف"),
            "h24":      (dict(expire_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)),  "⏰", "لینک موقت ۲۴ ساعته"),
            "d7":       (dict(expire_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)),    "📅", "لینک موقت ۷ روزه"),
            "approval": (dict(creates_join_request=True),                         "✅", "لینک با تایید ادمین"),
            "limit10":  (dict(member_limit=10),                                   "👥", "لینک محدود ۱۰ نفر"),
        }
        cfg = _CFG.get(action)
        if cfg:
            kwargs, icon, label = cfg
            try:
                result = await bot.create_chat_invite_link(chat_id, **kwargs)
                text = f"{icon} {label}:\n{result.invite_link}"
            except Exception as e:
                text = f"❌ خطا در ساخت لینک:\n{e}"

    if text:
        await bot.send_message(
            chat_id, text,
            reply_to_message_id=call.message.message_id,
            parse_mode="HTML",
        )
    await call.answer()


# ─── دستورات اجرایی ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cmd:"))
async def cb_cmd(call: CallbackQuery, bot: Bot):
    action   = call.data[4:]
    chat_id  = call.message.chat.id
    user_id  = call.from_user.id
    is_priv  = call.message.chat.type == "private"

    # در پیوی همه مجاز، در گروه فقط ادمین/مالک
    if not is_priv and not has_privilege(chat_id, user_id):
        await call.answer("❌ فقط ادمین‌ها", show_alert=True)
        return

    text = await _execute(action, chat_id, user_id, bot)
    if text:
        await bot.send_message(chat_id, text, reply_to_message_id=call.message.message_id, parse_mode="HTML")
    await call.answer()


async def _execute(action: str, chat_id: int, user_id: int, bot: Bot) -> str:
    from bot import cache
    from bot.helpers import (
        db_get_admins, db_get_vips, db_clear_vips,
        db_get_locks, db_enable_group_lock, db_disable_group_lock,
        db_enable_speaker, db_disable_speaker,
        db_get_learned_responses, db_get_word_filters,
        db_get_top_users, db_get_member,
        db_enable_group_off, db_disable_group_off,
        db_get_alias,
    )

    # ── قفل‌ها ──
    if action == "locks_status":
        locks = cache.GROUP_LOCKS.get(chat_id, {})
        if not locks:
            locks = await db_get_locks(chat_id)
        names = {
            "link": "لینک", "forward": "فوروارد", "username": "یوزرنیم",
            "gif": "گیف", "photo": "عکس", "media": "مدیا",
            "bad_words": "کلمات", "edit_message": "ادیت", "fun_text": "سرگرمی",
        }
        lines = []
        for k, label in names.items():
            state = "🔒 فعال" if locks.get(k) else "🔓 غیرفعال"
            lines.append(f"  {label}: {state}")
        return "📋 وضعیت قفل‌ها:\n\n" + "\n".join(lines)

    if action == "group_lock":
        cache.GROUP_LOCK[chat_id] = True
        await db_enable_group_lock(chat_id)
        return "🔐 گروه قفل شد — فقط ادمین‌ها پیام می‌دهند."

    if action == "group_unlock":
        cache.GROUP_LOCK.pop(chat_id, None)
        await db_disable_group_lock(chat_id)
        return "🔓 قفل کل گروه برداشته شد."

    # ── ادمین‌ها ──
    if action == "admin_list":
        admins = await db_get_admins(chat_id)
        if not admins:
            return "👮 هیچ ادمینی ثبت نشده."
        lines = [f"  • <a href='tg://user?id={uid}'>{uid}</a>" for uid in admins]
        return "👮 لیست ادمین‌ها:\n\n" + "\n".join(lines)

    if action == "sync_admins":
        try:
            members = await bot.get_chat_administrators(chat_id)
            from bot.helpers import db_add_admin
            from bot.cache_manager import ADMINS
            synced = []
            for m in members:
                if not m.user.is_bot:
                    await db_add_admin(chat_id, m.user.id)
                    if chat_id not in ADMINS:
                        ADMINS[chat_id] = set()
                    ADMINS[chat_id].add(m.user.id)
                    synced.append(str(m.user.id))
            return f"🔄 {len(synced)} ادمین همگام‌سازی شد."
        except Exception as e:
            return f"❌ خطا: {e}"

    # ── اعضای ویژه ──
    if action == "vip_list":
        vips = await db_get_vips(chat_id)
        if not vips:
            return "⭐ لیست ویژه خالی است."
        lines = [f"  • <a href='tg://user?id={uid}'>{uid}</a>" for uid in vips]
        return "⭐ اعضای ویژه:\n\n" + "\n".join(lines)

    if action == "vip_clear":
        await db_clear_vips(chat_id)
        from bot.cache_manager import VIPS
        VIPS.pop(chat_id, None)
        return "🗑 لیست ویژه پاکسازی شد."

    # ── بن ──
    if action == "ban_list":
        bans = cache.BAN_LIST.get(chat_id, set())
        if not bans:
            return "🚫 لیست بن خالی است."
        lines = [f"  • <a href='tg://user?id={uid}'>{uid}</a>" for uid in bans]
        return "🚫 لیست بن:\n\n" + "\n".join(lines)

    if action == "ban_clear":
        cache.BAN_LIST.pop(chat_id, None)
        return "🗑 لیست بن پاکسازی شد."

    # ── سکوت ──
    if action == "mute_list":
        muted = cache.MUTED_USERS.get(chat_id, set())
        if not muted:
            return "🤫 کسی ساکت نشده."
        lines = [f"  • <a href='tg://user?id={uid}'>{uid}</a>" for uid in muted]
        return "🤫 لیست سکوت:\n\n" + "\n".join(lines)

    if action == "mute_clear":
        cache.MUTED_USERS.pop(chat_id, None)
        return "🗑 لیست سکوت پاکسازی شد."

    # ── تگ ──
    if action == "tag_all":
        return "📣 برای تگ همه بنویس:  تگ"

    # ── اخطار ──
    if action == "my_warnings":
        member = await db_get_member(chat_id, user_id)
        if member:
            return f"⚠️ اخطارهای شما: {member.warnings}"
        return "⚠️ اطلاعاتی یافت نشد."

    # ── تاس ──
    if action == "dice_hint":
        return "🎲 برای پرتاب تاس بنویس:  تاس"

    if action == "dice":
        return "🎲 برای پرتاب تاس بنویس:  تاس"

    if action == "dice_stats":
        return "📊 برای آمار تاس بنویس:  آمار تاس"

    # ── سایر بازی‌ها ──
    _game_map = {
        "basketball": "🏀 بسکتبال",
        "penalty":    "⚽ پنالتی",
        "bowling":    "🎳 بولینگ",
        "dart":       "🎯 دارت",
        "slots":      "🎰 اسلات",
        "coin":       "🪙 سکه",
        "luck":       "🍀 شانس",
        "rps":        "✂️ سنگ کاغذ قیچی",
    }
    if action in _game_map:
        label = _game_map[action]
        cmd = label.split(" ", 1)[1]
        return f"{label}\n\nبرای بازی بنویس:  {cmd}"

    # ── برترین کاربران ──
    if action == "top_users":
        users = await db_get_top_users(chat_id, limit=10)
        if not users:
            return "📊 هنوز آماری ثبت نشده."
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, u in enumerate(users):
            medal = medals[i] if i < 3 else f"  {i+1}."
            name = u.alias or str(u.telegram_user_id)
            lines.append(f"{medal} {name} — {u.message_count} پیام")
        return "🏆 برترین کاربران:\n\n" + "\n".join(lines)

    # ── سخنگو ──
    if action == "speaker_on":
        cache.SPEAKER_ON.add(chat_id)
        await db_enable_speaker(chat_id)
        return "🔊 سخنگو روشن شد."

    if action == "speaker_off":
        cache.SPEAKER_ON.discard(chat_id)
        await db_disable_speaker(chat_id)
        return "🔇 سخنگو خاموش شد."

    # ── یادگیری ──
    if action == "learn_list":
        learns = cache.LEARNED_RESPONSES.get(chat_id)
        if not learns:
            learns_db = await db_get_learned_responses(chat_id)
            learns = learns_db
        if not learns:
            return "📚 هیچ پاسخی یاد نگرفته."
        lines = [f"  • {k} ← {v}" for k, v in list(learns.items())[:20]]
        return "📚 لیست یادگیری:\n\n" + "\n".join(lines)

    # ── وضعیت گروه ──
    if action == "group_status":
        off = chat_id in cache.OFF_GROUP
        locked = chat_id in cache.GROUP_LOCK
        speaker = chat_id in cache.SPEAKER_ON
        return (
            "📊 وضعیت گروه:\n\n"
            f"  ربات: {'❌ خاموش' if off else '✅ فعال'}\n"
            f"  قفل گروه: {'🔒 بسته' if locked else '🔓 باز'}\n"
            f"  سخنگو: {'🔊 روشن' if speaker else '🔇 خاموش'}\n"
        )

    # ── ربات روشن/خاموش ──
    if action == "bot_on":
        cache.OFF_GROUP.discard(chat_id)
        await db_disable_group_off(chat_id)
        return "✅ ربات روشن شد."

    if action == "bot_off":
        cache.OFF_GROUP.add(chat_id)
        await db_enable_group_off(chat_id)
        return "💤 ربات خاموش شد."

    # ── مالی ──
    if action == "my_balance":
        member = await db_get_member(chat_id, user_id)
        balance = member.point if member else 0
        return f"👛 موجودی شما: {balance:,} تومان"

    if action == "accounts":
        return "📊 برای لیست حساب‌ها بنویس:  حساب ها"

    if action == "report":
        return "📑 برای گزارش تراکنش بنویس:  گزارش"

    if action == "settle_me":
        return "🤝 برای تسویه بنویس:  تسویه"

    if action == "card_show":
        return "💳 برای دیدن شماره کارت بنویس:  شماره کارت"

    if action == "fee_show":
        from bot.helpers import db_get_group_fee
        try:
            fee = await db_get_group_fee(chat_id)
            return f"💹 کارمزد فعلی: {fee}٪"
        except Exception:
            return "💹 برای دیدن کارمزد بنویس:  کارمزد"

    if action == "dice_theme":
        from bot.helpers import db_get_group_theme
        theme = await db_get_group_theme(chat_id)
        return f"🎨 تم تاس فعلی: {theme}"

    if action == "owner_info":
        owner_id = cache.OWNER_CACHE.get(chat_id)
        if not owner_id:
            return "👑 مالکی برای این گروه ثبت نشده."
        return (
            f"👑 مالک فعلی گروه:\n"
            f"<a href='tg://user?id={owner_id}'>{owner_id}</a>\n\n"
            f"برای انتقال مالکیت، روی پیام کاربر مورد نظر ریپلای کن و بنویس:\n"
            f"انتقال مالکیت"
        )

    # ── خوشامدگویی ──
    if action == "welcome_status":
        from bot import cache as _c
        enabled = chat_id not in _c.WELCOME_DISABLED
        s = _c.WELCOME_SETTINGS.get(chat_id, {})
        from bot.constants import DEFAULT_WELCOME_TEXT as _dwt
        text = s.get("text") or (_dwt + " (پیش‌فرض)")
        has_gif = bool(s.get("gif_file_id"))
        return (
            f"🎉 وضعیت خوشامدگویی:\n\n"
            f"  وضعیت: {'✅ روشن' if enabled else '❌ خاموش'}\n"
            f"  متن: {text[:60]}{'...' if len(text) > 60 else ''}\n"
            f"  گیف: {'✅ تنظیم شده' if has_gif else '❌ ندارد'}"
        )

    if action == "welcome_on":
        from bot import cache as _c
        from bot.helpers import db_set_welcome as _sw
        _c.WELCOME_DISABLED.discard(chat_id)
        await _sw(chat_id, enabled=True)
        return "✅ خوشامدگویی روشن شد.\n\nبرای تنظیم متن: متن خوشامد [پیام]\nبرای گیف: گیف خوشامد (ریپلای روی گیف)"

    if action == "welcome_off":
        from bot import cache as _c
        from bot.helpers import db_set_welcome as _sw
        _c.WELCOME_DISABLED.add(chat_id)
        await _sw(chat_id, enabled=False)
        return "❌ خوشامدگویی خاموش شد."

    if action == "welcome_gif_del":
        from bot import cache as _c
        from bot.helpers import db_set_welcome as _sw
        _c.WELCOME_SETTINGS.setdefault(chat_id, {})["gif_file_id"] = ""
        await _sw(chat_id, gif_file_id="")
        return "✅ گیف خوشامد حذف شد."

    # ── آنتی فلود ──
    if action == "flood_status":
        from bot import cache as _c
        enabled = chat_id in _c.ANTI_FLOOD_ENABLED
        cfg = _c.ANTI_FLOOD_SETTINGS.get(chat_id, {"limit": 5, "window": 10})
        return (
            f"🚫 وضعیت آنتی فلود:\n\n"
            f"  وضعیت: {'✅ روشن' if enabled else '❌ خاموش'}\n"
            f"  حد: {cfg['limit']} پیام در {cfg['window']} ثانیه\n"
            f"  مجازات: سکوت ۵ دقیقه‌ای"
        )

    if action == "flood_on":
        from bot import cache as _c
        from bot.helpers import db_set_anti_flood as _sf
        _c.ANTI_FLOOD_ENABLED.add(chat_id)
        await _sf(chat_id, enabled=True)
        cfg = _c.ANTI_FLOOD_SETTINGS.get(chat_id, {"limit": 5, "window": 10})
        return f"✅ آنتی فلود روشن شد.\n\nحد: {cfg['limit']} پیام در {cfg['window']} ثانیه"

    if action == "flood_off":
        from bot import cache as _c
        from bot.helpers import db_set_anti_flood as _sf
        _c.ANTI_FLOOD_ENABLED.discard(chat_id)
        await _sf(chat_id, enabled=False)
        return "❌ آنتی فلود خاموش شد."

    # ── فیلتر کلمه ──
    if action == "filter_list":
        filters = cache.WORD_FILTERS.get(chat_id, [])
        if not filters:
            filters = await db_get_word_filters(chat_id)
        if not filters:
            return "🔤 هیچ کلمه فیلتری ثبت نشده.\n\nبرای اضافه کردن بنویس:  کلمه فیلتر [کلمه]"
        words = [f"  • {w}" for w in list(filters)[:20]]
        return "🔤 کلمات فیلتر شده:\n\n" + "\n".join(words)

    # ── لقب/مشخصات ──
    if action == "my_alias":
        alias = await db_get_alias(chat_id, user_id)
        if alias:
            return f"🏷 لقب شما در این گروه: <b>{alias}</b>"
        return "🏷 شما هنوز لقبی ندارید.\n\nبرای ثبت لقب بنویس:  لقب [نام دلخواه]"

    return f"⚙️ دستور «{action}» اجرا شد."
