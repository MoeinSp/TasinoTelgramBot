"""پنل اینلاین چالش — مالک و ادمین (پیوی تلگرام)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup

from bot.cache_manager import can_manage_group, is_owner
from bot.challenges import (
    TYPE_LABELS,
    cancel_challenge,
    create_challenge,
    format_challenge_announce,
    is_race_type,
    list_active_challenges,
    parse_publish_clock_input,
    race_rule_text,
    type_label,
)
from bot.pv_finance_panel import get_finance_group, set_finance_group

_drafts: dict[int, dict] = {}
_wait: dict[int, str] = {}


def clear_challenge_session(user_id) -> None:
    uid = int(user_id)
    _drafts.pop(uid, None)
    _wait.pop(uid, None)


def is_waiting_challenge_input(user_id) -> bool:
    return int(user_id) in _wait


def _empty_draft() -> dict:
    return {
        "type": None,
        "prize": 0,
        "hours": 24,
        "publish_in": 0,
        "publish_clock": "",
        "min_games": 0,
        "min_wallet": 0,
    }


def _draft(uid: int) -> dict:
    d = _drafts.get(uid)
    if not d:
        d = _empty_draft()
        _drafts[uid] = d
    d.setdefault("publish_clock", "")
    d.setdefault("publish_in", 0)
    return d


def _publish_label(d: dict) -> str:
    clock = (d.get("publish_clock") or "").strip()
    if clock:
        return f"ساعت {clock}"
    m = int(d.get("publish_in") or 0)
    if m <= 0:
        return "الان"
    if m < 60:
        return f"{m} دقیقه دیگر"
    h = m // 60
    rem = m % 60
    if rem:
        return f"{h} ساعت و {rem} دقیقه دیگر"
    return f"{h} ساعت دیگر"


def _draft_text(d: dict) -> str:
    t = type_label(d["type"]) if d.get("type") else "— انتخاب نشده —"
    lines = [
        "🏆 ساخت چالش جدید",
        "━━━━━━━━━━━━━━━━━━",
        f"📌 نوع: {t}",
        f"🎁 جایزه: {int(d.get('prize') or 0):,} واحد",
        f"🕐 زمان شروع: {_publish_label(d)}",
    ]
    if is_race_type(d.get("type") or ""):
        rule = race_rule_text(d["type"])
        if rule:
            lines.append(f"🏁 شرط برد: {rule}")
    else:
        lines.append(f"⏱ مدت: {int(d.get('hours') or 24)} ساعت")
    lines.extend([
        f"🎮 حداقل مسابقه تاس امروز: {int(d.get('min_games') or 0) or 'بدون محدودیت'}",
        f"💳 حداقل موجودی: {int(d.get('min_wallet') or 0) or 'بدون محدودیت'}",
        "━━━━━━━━━━━━━━━━━━",
        "از دکمه‌ها تنظیم کنید، سپس «✅ انتشار» را بزنید.",
    ])
    return "\n".join(lines)


def _kb_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="➕ چالش جدید", callback_data="ch:new")],
        [IKB(text="📋 چالش‌های فعال", callback_data="ch:list")],
        [IKB(text="↩️ بازگشت به پنل مالی", callback_data="ch:back")],
    ])


def _kb_types() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="🎲 تاس", callback_data="ch:t:dice"), IKB(text="🎯 دارت", callback_data="ch:t:dart")],
        [IKB(text="🍀 شانس", callback_data="ch:t:luck"), IKB(text="⚽ فوتبال", callback_data="ch:t:football")],
        [IKB(text="🏀 بسکتبال", callback_data="ch:t:basketball")],
        [IKB(text="💰 بیشترین شرط", callback_data="ch:t:max_bet")],
        [IKB(text="🎲 بیشترین تعداد", callback_data="ch:t:max_count")],
        [IKB(text="📈 بیشترین افزایش", callback_data="ch:t:max_increase")],
        [IKB(text="📊 مجموع افزایش", callback_data="ch:t:sum_increase")],
        [IKB(text="↩️ بازگشت", callback_data="ch:home")],
    ])


def _kb_draft(d: dict | None = None) -> InlineKeyboardMarkup:
    d = d or {}
    rows = [
        [IKB(text="🎁 تنظیم جایزه", callback_data="ch:prize"), IKB(text="🕐 زمان شروع", callback_data="ch:pubtime")],
    ]
    if not is_race_type(d.get("type") or ""):
        rows.append([IKB(text="⏱ مدت زمان", callback_data="ch:dur")])
    rows.extend([
        [IKB(text="🔒 محدودیت‌ها", callback_data="ch:rq")],
        [IKB(text="✅ انتشار چالش", callback_data="ch:pub")],
        [IKB(text="↩️ عوض کردن نوع", callback_data="ch:new"), IKB(text="🏠 منوی چالش", callback_data="ch:home")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _kb_duration() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="۱ ساعت", callback_data="ch:h:1"), IKB(text="۳ ساعت", callback_data="ch:h:3"), IKB(text="۶ ساعت", callback_data="ch:h:6")],
        [IKB(text="۱۲ ساعت", callback_data="ch:h:12"), IKB(text="۲۴ ساعت", callback_data="ch:h:24"), IKB(text="۴۸ ساعت", callback_data="ch:h:48")],
        [IKB(text="↩️ بازگشت", callback_data="ch:edit")],
    ])


def _kb_publish_time() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="الان", callback_data="ch:p:0"), IKB(text="۵ دقیقه", callback_data="ch:p:5"), IKB(text="۱۵ دقیقه", callback_data="ch:p:15")],
        [IKB(text="۳۰ دقیقه", callback_data="ch:p:30"), IKB(text="۱ ساعت", callback_data="ch:p:60")],
        [IKB(text="🕒 ساعت دلخواه (مثلاً 13:30)", callback_data="ch:pclock")],
        [IKB(text="↩️ بازگشت", callback_data="ch:edit")],
    ])


def _kb_restrictions(d: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text=f"🎲 تاس امروز: {int(d.get('min_games') or 0) or 'خاموش'}", callback_data="ch:rg")],
        [IKB(text=f"💳 موجودی: {int(d.get('min_wallet') or 0) or 'خاموش'}", callback_data="ch:rw")],
        [IKB(text="🧹 حذف محدودیت تاس", callback_data="ch:rg0"), IKB(text="🧹 حذف محدودیت موجودی", callback_data="ch:rw0")],
        [IKB(text="↩️ بازگشت", callback_data="ch:edit")],
    ])


async def open_challenge_home(bot, user_id: int, group_id: int) -> None:
    clear_challenge_session(user_id)
    set_finance_group(user_id, group_id)
    active = await list_active_challenges(group_id)
    text = (
        "🏆 <b>پنل چالش</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"گروه: <code>{group_id}</code>\n"
        f"چالش فعال: <b>{len(active)}</b>\n\n"
        "جایزه به‌نام ادمین ثبت‌کننده حساب می‌شود.\n"
        "زمان شروع برای همه انواع قابل تنظیم است."
    )
    await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=_kb_home())


async def open_challenge_panel_from_group(bot, group_chat_id: int, user_id: int, group_msg_id: int) -> bool:
    """از دستور گروه «ثبت چالش» — پنل را به پیوی می‌فرستد."""
    from bot.helpers import deliver_private_or_warn, safe_send

    if not can_manage_group(group_chat_id, user_id):
        await safe_send(
            bot, group_chat_id,
            "❌ فقط مالک و ادمین‌های ربات می‌توانند چالش ثبت کنند.",
            reply_to=group_msg_id,
        )
        return False

    set_finance_group(user_id, group_chat_id)
    clear_challenge_session(user_id)
    active = await list_active_challenges(group_chat_id)
    text = (
        "🏆 پنل ثبت چالش\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📍 گروه: <code>{group_chat_id}</code>\n"
        f"📌 چالش فعال: {len(active)}\n\n"
        "ℹ️ جایزه چالش به‌نام شما (ثبت‌کننده) در حساب ادمین ثبت می‌شود.\n\n"
        "از دکمه‌ها چالش بسازید:"
    )
    return await deliver_private_or_warn(
        bot, group_chat_id, user_id, group_msg_id, text, reply_markup=_kb_home(),
    )


async def handle_challenge_text(message, bot) -> bool:
    uid = message.from_user.id
    kind = _wait.get(uid)
    if not kind:
        return False
    raw = (message.text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if raw in ("لغو", "انصراف", "cancel"):
        _wait.pop(uid, None)
        await message.answer("❌ لغو شد.", reply_markup=_kb_draft(_draft(uid)))
        return True

    d = _draft(uid)
    if kind == "clock":
        clock = parse_publish_clock_input(raw)
        if not clock:
            await message.answer(
                "⚠️ ساعت نامعتبر است.\n"
                "مثال‌ها: <code>13:30</code> یا <code>9:05</code>\n"
                "برای لغو: لغو",
                parse_mode="HTML",
            )
            return True
        d["publish_clock"] = clock
        d["publish_in"] = 0
        _wait.pop(uid, None)
        await message.answer(_draft_text(d), reply_markup=_kb_draft(d))
        return True

    if not raw.isdigit() or int(raw) < 0:
        await message.answer("⚠️ فقط عدد معتبر بفرستید. برای لغو: لغو")
        return True
    val = int(raw)
    if kind == "prize":
        if val <= 0:
            await message.answer("⚠️ جایزه باید بیشتر از صفر باشد.")
            return True
        d["prize"] = val
    elif kind == "games":
        d["min_games"] = val
    elif kind == "wallet":
        d["min_wallet"] = val
    _wait.pop(uid, None)
    await message.answer(_draft_text(d), reply_markup=_kb_draft(d))
    return True


async def handle_challenge_callback(call, bot) -> bool:
    data = call.data or ""
    if not data.startswith("ch:"):
        return False
    uid = call.from_user.id
    group_id = get_finance_group(uid)
    if not group_id:
        await call.answer("ابتدا گروه را از پنل مالی انتخاب کنید یا در گروه «ثبت چالش» بزنید.", show_alert=True)
        return True
    if not can_manage_group(group_id, uid):
        await call.answer("فقط مالک و ادمین گروه.", show_alert=True)
        return True

    from bot.pv_finance_panel import open_finance_panel

    if data == "ch:back":
        clear_challenge_session(uid)
        await call.answer()
        await open_finance_panel(bot, uid, group_id)
        return True
    if data == "ch:home":
        await call.answer()
        await open_challenge_home(bot, uid, group_id)
        return True
    if data == "ch:new":
        _drafts[uid] = _empty_draft()
        await call.answer()
        await call.message.answer("📌 نوع چالش را انتخاب کنید:", reply_markup=_kb_types())
        return True
    if data == "ch:list":
        active = await list_active_challenges(group_id)
        await call.answer()
        if not active:
            await call.message.answer("📭 چالش فعالی وجود ندارد.", reply_markup=_kb_home())
            return True
        lines = ["📋 چالش‌های فعال", "━━━━━━━━━━━━━━━━━━"]
        rows = []
        owner = is_owner(group_id, uid)
        for ch in active:
            extra = race_rule_text(ch.challenge_type) if is_race_type(ch.challenge_type) else "تا پایان مدت"
            lines.append(f"#{ch.id} {type_label(ch.challenge_type)}\n🎁 {int(ch.prize_amount):,} | {extra}")
            if owner or int(ch.created_by) == int(uid):
                rows.append([IKB(text=f"❌ لغو #{ch.id}", callback_data=f"ch:x:{ch.id}")])
        rows.append([IKB(text="↩️ بازگشت", callback_data="ch:home")])
        await call.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return True
    if data.startswith("ch:x:"):
        ok = await cancel_challenge(
            int(data.split(":")[-1]), uid, as_owner=is_owner(group_id, uid),
        )
        await call.answer("لغو شد" if ok else "ناموفق", show_alert=True)
        await call.message.answer("✅ چالش لغو شد." if ok else "⚠️ چالش پیدا نشد یا اجازه لغو ندارید.", reply_markup=_kb_home())
        return True
    if data.startswith("ch:t:"):
        ctype = data.split(":", 2)[-1]
        if ctype not in TYPE_LABELS:
            await call.answer("نامعتبر", show_alert=True)
            return True
        d = _draft(uid)
        d["type"] = ctype
        await call.answer()
        await call.message.answer(_draft_text(d), reply_markup=_kb_draft(d))
        return True
    if data == "ch:edit":
        d = _draft(uid)
        await call.answer()
        await call.message.answer(_draft_text(d), reply_markup=_kb_draft(d))
        return True
    if data == "ch:prize":
        _wait[uid] = "prize"
        await call.answer()
        await call.message.answer("🎁 مبلغ جایزه را به‌عدد بفرستید.\nبرای لغو: لغو")
        return True
    if data == "ch:dur":
        d = _draft(uid)
        if is_race_type(d.get("type") or ""):
            await call.answer("این چالش مدت ندارد", show_alert=True)
            return True
        await call.answer()
        await call.message.answer("⏱ مدت چالش را انتخاب کنید:", reply_markup=_kb_duration())
        return True
    if data == "ch:pubtime":
        await call.answer()
        await call.message.answer("🕐 زمان شروع را انتخاب کنید:", reply_markup=_kb_publish_time())
        return True
    if data == "ch:pclock":
        _wait[uid] = "clock"
        await call.answer()
        await call.message.answer(
            "🕒 ساعت شروع را بفرستید.\n"
            "مثال: <code>13:30</code>\n"
            "اگر آن ساعت امروز گذشته باشد، برای فردا تنظیم می‌شود.\n"
            "برای لغو: لغو",
            parse_mode="HTML",
        )
        return True
    if data.startswith("ch:h:"):
        _draft(uid)["hours"] = int(data.split(":")[-1])
        d = _draft(uid)
        await call.answer()
        await call.message.answer(_draft_text(d), reply_markup=_kb_draft(d))
        return True
    if data.startswith("ch:p:"):
        d = _draft(uid)
        d["publish_in"] = int(data.split(":")[-1])
        d["publish_clock"] = ""
        await call.answer()
        await call.message.answer(_draft_text(d), reply_markup=_kb_draft(d))
        return True
    if data == "ch:rq":
        await call.answer()
        await call.message.answer("🔒 محدودیت‌ها:", reply_markup=_kb_restrictions(_draft(uid)))
        return True
    if data == "ch:rg":
        _wait[uid] = "games"
        await call.answer()
        await call.message.answer("🎲 حداقل تعداد مسابقه تاس امروز را بفرستید (همان آمار تاس امروز).\nبرای لغو: لغو")
        return True
    if data == "ch:rw":
        _wait[uid] = "wallet"
        await call.answer()
        await call.message.answer("💳 حداقل موجودی کیف پول را بفرستید.\nبرای لغو: لغو")
        return True
    if data == "ch:rg0":
        d = _draft(uid)
        d["min_games"] = 0
        await call.answer()
        await call.message.answer(_draft_text(d), reply_markup=_kb_draft(d))
        return True
    if data == "ch:rw0":
        d = _draft(uid)
        d["min_wallet"] = 0
        await call.answer()
        await call.message.answer(_draft_text(d), reply_markup=_kb_draft(d))
        return True
    if data == "ch:pub":
        d = _draft(uid)
        if not d.get("type"):
            await call.answer("نوع را انتخاب کنید", show_alert=True)
            return True
        if int(d.get("prize") or 0) <= 0:
            await call.answer("جایزه را تنظیم کنید", show_alert=True)
            return True
        ch = await create_challenge(
            group_id, uid, d["type"], int(d["prize"]), int(d.get("hours") or 24),
            min_games_today=int(d.get("min_games") or 0),
            min_wallet=int(d.get("min_wallet") or 0),
            publish_delay_minutes=int(d.get("publish_in") or 0),
            publish_clock=(d.get("publish_clock") or None),
        )
        clear_challenge_session(uid)
        announce = format_challenge_announce(ch)
        try:
            await bot.send_message(group_id, announce, parse_mode="HTML")
        except Exception:
            await call.message.answer("⚠️ چالش ساخته شد ولی ارسال به گروه ناموفق بود.")
            await call.answer()
            return True
        # برای چالش زمان‌بندی‌شده: countdown ۱۰ثانیه + پیام شروع دقیق
        if ch.announce_message_id is None:
            from bot.challenges import schedule_challenge_lifecycle
            schedule_challenge_lifecycle(bot, ch.id)
        await call.answer("منتشر شد ✅")
        await call.message.answer(
            f"✅ چالش #{ch.id} منتشر شد و در گروه اعلام گردید.",
            reply_markup=_kb_home(),
        )
        return True
    await call.answer()
    return True
