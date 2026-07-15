"""User initiated withdrawal flow for Telegram."""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup
from asgiref.sync import sync_to_async

from bot.finance import get_playable_balance
from bot.helpers import send_private

_flow: dict[int, dict] = {}
_receipt_wait: dict[int, int] = {}
_admin_message_wait: dict[int, int] = {}
_admin_deliveries: dict[int, list[tuple[int, int]]] = {}

BEGIN_OK = "ok"
BEGIN_NO_PV = "no_pv"
BEGIN_MIN_BLOCKED = "min_blocked"
BEGIN_PENDING = "pending_open"
BEGIN_BANNED = "banned"


def remember_wd_delivery(request_id: int, chat_id: int, message_id: int) -> None:
    rid = int(request_id)
    item = (int(chat_id), int(message_id))
    bucket = _admin_deliveries.setdefault(rid, [])
    if item not in bucket:
        bucket.append(item)


def get_wd_deliveries(request_id: int) -> list[tuple[int, int]]:
    return list(_admin_deliveries.get(int(request_id), []))


async def broadcast_wd_admin_update(bot, request_id: int, text: str, kb) -> int:
    updated = 0
    for chat_id, message_id in get_wd_deliveries(request_id):
        try:
            await bot.edit_message_text(
                text, chat_id=chat_id, message_id=message_id, reply_markup=kb, parse_mode="HTML",
            )
            updated += 1
        except Exception:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=message_id, reply_markup=kb,
                )
                updated += 1
            except Exception:
                pass
    return updated


def set_receipt_wait(admin_id: int, request_id: int) -> None:
    _receipt_wait[int(admin_id)] = int(request_id)


def has_receipt_wait(admin_id: int) -> bool:
    return int(admin_id) in _receipt_wait


def pop_receipt_wait(admin_id: int) -> int | None:
    return _receipt_wait.pop(int(admin_id), None)


def set_admin_message_wait(admin_id: int, request_id: int) -> None:
    _admin_message_wait[int(admin_id)] = int(request_id)


def pop_admin_message_wait(admin_id: int) -> int | None:
    return _admin_message_wait.pop(int(admin_id), None)


def is_waiting_admin_message(admin_id: int) -> bool:
    return int(admin_id) in _admin_message_wait


_STATUS_FA = {
    "pending": "⏳ در انتظار تأیید",
    "receipt": "📎 در انتظار رسید",
    "done": "✅ انجام‌شده",
    "cancelled": "❌ لغو شده",
}

_WD_WARN = (
    "⚠️ قبل از پرداخت حتماً دکمه «🔄 بروزرسانی» را بزنید "
    "تا مطمئن شوید مبلغ، کارت یا وضعیت درخواست تغییر نکرده باشد."
)


def format_open_withdrawal_user_block(info: dict) -> str:
    """پیام وقتی کاربر با درخواست تسویه باز می‌خواهد دوباره درخواست بدهد."""
    amount = int(info.get("total_amount") or info.get("amount") or 0)
    status = info.get("status") or "pending"
    status_fa = _STATUS_FA.get(status, status)
    return (
        "⚠️ درخواست تسویه باز دارید\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📌 وضعیت: {status_fa}\n"
        f"💰 مبلغ در انتظار: {amount:,} واحد\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "تا مشخص شدن این درخواست، امکان ثبت درخواست جدید وجود ندارد.\n\n"
        "🔹 از ادمین بخواهید همین درخواست را تأیید کند\n"
        "🔹 یا با دستور «لغو درخواست تسویه» آن را لغو کنید تا بتوانید دوباره درخواست بدهید"
    )


def format_withdrawal_admin_text(
    *,
    user_name: str,
    amount: int,
    card: str,
    card_name: str,
    status: str = "pending",
    refreshed: bool = False,
    balance: int | None = None,
    settle_kind: str | None = None,
) -> str:
    status_line = _STATUS_FA.get(status, status)
    head = "🔄 درخواست تسویه (بروزرسانی‌شده)" if refreshed else "📥 درخواست تسویه"
    kind = (settle_kind or "").strip().lower()
    if kind not in ("full", "custom"):
        # سازگاری با درخواست‌های قدیمی: اگر موجودی معلوم باشد مقایسه کن
        if balance is not None and int(amount) >= int(balance) > 0:
            kind = "full"
        else:
            kind = "custom"
    kind_fa = "کامل" if kind == "full" else "دلخواه"
    return (
        f"{head}\n"
        f"📌 وضعیت: {status_line}\n"
        f"👤 کاربر: {user_name}\n"
        f"📌 نوع تسویه: {kind_fa}\n"
        f"💸 مبلغ تسویه: {amount:,}\n"
        f"💳 کارت: <code>{card}</code>\n"
        f"👤 نام کارت: {card_name}\n\n"
        f"{_WD_WARN}"
    )


def withdrawal_admin_keyboard(request_id: int, *, status: str = "pending") -> InlineKeyboardMarkup:
    rid = int(request_id)
    if status != "pending":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                IKB(text="💬 پیام", callback_data=f"wd:message:{rid}"),
                IKB(text="🔄 بروزرسانی", callback_data=f"wd:refresh:{rid}"),
            ],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            IKB(text="✅ تأیید", callback_data=f"wd:approve:{rid}"),
            IKB(text="❌ رد", callback_data=f"wd:reject:{rid}"),
        ],
        [
            IKB(text="📎 رسید (اختیاری)", callback_data=f"wd:receipt:{rid}"),
            IKB(text="💬 پیام", callback_data=f"wd:message:{rid}"),
        ],
        [IKB(text="🔄 بروزرسانی", callback_data=f"wd:refresh:{rid}")],
    ])


@sync_to_async
def get_min_withdrawal(chat_id: int) -> int:
    from account.models import TelegramGroup

    g = TelegramGroup.objects.filter(telegram_chat_id=int(chat_id)).first()
    return int(getattr(g, "min_withdrawal_amount", 0) or 0)


@sync_to_async
def set_min_withdrawal(chat_id: int, amount: int) -> int:
    from account.models import TelegramGroup

    g, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=int(chat_id), defaults={"name": ""},
    )
    g.min_withdrawal_amount = max(0, int(amount))
    g.save(update_fields=["min_withdrawal_amount"])
    return g.min_withdrawal_amount


def min_withdrawal_hint(minimum: int) -> str:
    if minimum <= 0:
        return ""
    return f"\n📌 حداقل مبلغ تسویه: {minimum:,} واحد"


def format_min_withdrawal_denial(minimum: int, available: int) -> str:
    return (
        "⛔️ امکان تسویه وجود ندارد\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 موجودی قابل تسویه شما: {available:,} واحد\n"
        f"📌 حداقل مبلغ تسویه در این گروه: {minimum:,} واحد\n\n"
        f"برای درخواست تسویه، موجودی قابل تسویه باید حداقل {minimum:,} واحد باشد."
    )


def format_min_amount_denial(minimum: int, amount: int) -> str:
    return (
        f"⛔️ حداقل مبلغ تسویه در این گروه {minimum:,} واحد است.\n"
        f"💰 مبلغ وارد شده: {amount:,} واحد"
    )


async def check_min_withdrawal(chat_id: int, available: int, amount: int | None = None) -> str | None:
    minimum = await get_min_withdrawal(chat_id)
    if minimum <= 0:
        return None
    if available < minimum:
        return format_min_withdrawal_denial(minimum, available)
    if amount is not None and amount < minimum:
        return format_min_amount_denial(minimum, amount)
    return None


def parse_min_withdrawal_command(text: str) -> tuple[str, int] | None:
    """('show', 0) | ('set', amount) | None — بدون «خاموش»."""
    if not text:
        return None
    t = text.strip()
    if t == "حداقل تسویه خاموش":
        return None
    if not t.startswith("حداقل تسویه"):
        return None
    suffix = t[len("حداقل تسویه"):].strip()
    if not suffix:
        return ("show", 0)
    raw = suffix.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if raw.isdigit() and int(raw) > 0:
        return ("set", int(raw))
    return None


@sync_to_async
def _wallet_and_card(chat_id: int, user_id: int):
    from account.models import TelegramGroupMember

    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=int(chat_id), telegram_user_id=int(user_id),
    ).first()
    balance = int(m.point or 0) if m else 0
    card = (getattr(m, "card_number", "") or "") if m else ""
    name = (getattr(m, "card_name", "") or "") if m else ""
    return balance, card, name


@sync_to_async
def _save_card_name(chat_id: int, user_id: int, *, card: str | None = None, name: str | None = None):
    from account.models import TelegramGroupMember, TelegramGroup

    grp, _ = TelegramGroup.objects.get_or_create(
        telegram_chat_id=int(chat_id), defaults={"name": ""},
    )
    obj, _ = TelegramGroupMember.objects.get_or_create(
        telegram_chat_id=int(chat_id),
        telegram_user_id=int(user_id),
        defaults={"group": grp, "role": "member"},
    )
    updates = []
    if card:
        obj.card_number = str(card)
        updates.append("card_number")
    if name:
        obj.card_name = str(name)
        updates.append("card_name")
    if updates:
        obj.save(update_fields=updates)


def waiting(user_id: int) -> bool:
    return int(user_id) in _flow


def _kb(has_card=False, has_name=False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            IKB(text=("💳 تغییر کارت" if has_card else "💳 ثبت کارت"), callback_data="wd:card"),
            IKB(text=("👤 تغییر نام" if has_name else "👤 ثبت نام"), callback_data="wd:name"),
        ],
        [
            IKB(text="✅ تسویه کامل", callback_data="wd:full"),
            IKB(text="✏️ عوض کردن مبلغ", callback_data="wd:amount"),
        ],
        [
            IKB(text="❌ لغو", callback_data="wd:cancel"),
        ],
    ])


def _kb_cancel_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="❌ لغو", callback_data="wd:cancel")],
    ])


async def begin(bot: Bot, group_id: int, user_id: int) -> str:
    from bot.finance_ban import is_finance_banned, FINANCE_BAN_USER_TEXT
    if await is_finance_banned(group_id, user_id):
        ok = await send_private(bot, user_id, FINANCE_BAN_USER_TEXT)
        return BEGIN_NO_PV if not ok else BEGIN_BANNED
    open_info = await get_open_withdrawal_info(group_id, user_id)
    if open_info:
        ok = await send_private(bot, user_id, format_open_withdrawal_user_block(open_info))
        if not ok:
            return BEGIN_NO_PV
        return BEGIN_PENDING
    total, available, pending = await get_playable_balance(group_id, user_id)
    blocked = await check_min_withdrawal(group_id, available)
    if blocked:
        await bot.send_message(user_id, blocked)
        return BEGIN_MIN_BLOCKED
    minimum = await get_min_withdrawal(group_id)
    min_line = min_withdrawal_hint(minimum)
    _, card, name = await _wallet_and_card(group_id, user_id)
    _flow[int(user_id)] = {"chat_id": int(group_id), "step": "card"}
    pending_line = f"\n⏳ در انتظار تسویه: {pending:,}" if pending > 0 else ""
    if card and name:
        _flow[int(user_id)].update({"step": "amount", "card": card, "name": name, "balance": available})
        text = (
            f"🧾 درخواست تسویه\n💰 موجودی قابل تسویه: {available:,}{pending_line}{min_line}\n"
            f"💳 کارت: <code>{card}</code>\n👤 نام: {name}\n\nمبلغ تسویه را وارد کنید."
        )
    else:
        text = (
            "👤 کاربر عزیز، ابتدا شماره کارت خود را ثبت کنید.\n\n"
            "لطفاً شماره کارت دقیقاً ۱۶ رقمی را ارسال کنید."
        )
    ok = await send_private(bot, user_id, text, reply_markup=_kb(bool(card), bool(name)))
    if not ok:
        _flow.pop(int(user_id), None)
        return BEGIN_NO_PV
    return BEGIN_OK


async def handle_text(bot: Bot, user_id: int, text: str) -> bool:
    data = _flow.get(int(user_id))
    if not data:
        return False
    t = (text or "").strip()
    if t in ("لغو", "انصراف", "cancel"):
        _flow.pop(int(user_id), None)
        await bot.send_message(user_id, "❌ درخواست تسویه لغو شد.")
        return True
    step = data.get("step")
    if step == "card":
        digits = "".join(ch for ch in t if ch.isdigit())
        if len(digits) != 16:
            await bot.send_message(
                user_id,
                "⚠️ شماره کارت باید دقیقاً ۱۶ رقم باشد.",
                reply_markup=_kb_cancel_only(),
            )
            return True
        data.update(step="name", card=digits)
        await _save_card_name(data["chat_id"], user_id, card=digits)
        await bot.send_message(
            user_id,
            "👤 نام و نام خانوادگی صاحب کارت را ارسال کنید.",
            reply_markup=_kb_cancel_only(),
        )
        return True
    if step == "name":
        if len(t) < 2:
            await bot.send_message(
                user_id,
                "⚠️ نام معتبر نیست.",
                reply_markup=_kb_cancel_only(),
            )
            return True
        data.update(step="amount", name=t)
        await _save_card_name(data["chat_id"], user_id, name=t)
        _, available, pending = await get_playable_balance(data["chat_id"], user_id)
        data["balance"] = available
        minimum = await get_min_withdrawal(data["chat_id"])
        min_line = min_withdrawal_hint(minimum)
        pending_line = f"\n⏳ در انتظار تسویه: {pending:,}" if pending > 0 else ""
        await bot.send_message(
            user_id,
            f"💰 مبلغ تسویه را وارد کنید (حداکثر {available:,}).{pending_line}{min_line}\n\n"
            f"💳 شماره کارت: <code>{data['card']}</code>\n👤 نام صاحب کارت: {data['name']}",
            reply_markup=_kb(True, True),
            parse_mode="HTML",
        )
        return True
    if step == "amount":
        try:
            amount = int(t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
        except ValueError:
            amount = 0
        available = int(data.get("balance", 0))
        if amount <= 0 or amount > available:
            await bot.send_message(
                user_id,
                "⚠️ مبلغ نامعتبر است یا از موجودی قابل تسویه بیشتر است.",
                reply_markup=_kb(True, True),
            )
            return True
        blocked = await check_min_withdrawal(data["chat_id"], available, amount)
        if blocked:
            await bot.send_message(user_id, blocked, reply_markup=_kb(True, True))
            return True
        open_info = await get_open_withdrawal_info(data["chat_id"], user_id)
        if open_info:
            _flow.pop(int(user_id), None)
            await bot.send_message(user_id, format_open_withdrawal_user_block(open_info))
            return True
        from account.models import WithdrawalRequest

        settle_kind = (data.get("settle_kind") or "").strip().lower()
        if settle_kind != "full":
            settle_kind = "full" if amount == available else "custom"
        req = await sync_to_async(WithdrawalRequest.objects.create)(
            telegram_chat_id=data["chat_id"],
            telegram_user_id=int(user_id),
            amount=amount,
            card_number=data["card"],
            card_name=data["name"],
            status="pending",
            settle_kind=settle_kind,
        )
        _flow.pop(int(user_id), None)
        try:
            u = await bot.get_chat(int(user_id))
            user_name = (u.full_name or u.first_name or "").strip() or str(user_id)
        except Exception:
            user_name = str(user_id)
        kind_fa = "کامل" if settle_kind == "full" else "دلخواه"
        msg = format_withdrawal_admin_text(
            user_name=user_name,
            amount=amount,
            card=data["card"],
            card_name=data["name"],
            status="pending",
            settle_kind=settle_kind,
        )
        kb = withdrawal_admin_keyboard(req.id, status="pending")
        delivered = 0
        from bot.wallet_helpers import collect_manager_ids

        manager_ids = await collect_manager_ids(bot, data["chat_id"])
        for mid in manager_ids:
            try:
                sent = await bot.send_message(mid, msg, reply_markup=kb, parse_mode="HTML")
                remember_wd_delivery(req.id, mid, sent.message_id)
                delivered += 1
            except Exception:
                pass
        if delivered == 0:
            try:
                sent = await bot.send_message(
                    data["chat_id"],
                    msg + "\n\n⚠️ پیوی مدیران در دسترس نبود؛ تأیید از داخل گروه انجام شود.",
                    reply_markup=kb,
                    parse_mode="HTML",
                )
                remember_wd_delivery(req.id, data["chat_id"], sent.message_id)
            except Exception:
                pass
        await bot.send_message(
            user_id,
            "✅ درخواست تسویه برای مدیران ارسال شد.\n"
            f"📌 نوع تسویه: {kind_fa}\n"
            f"💸 مبلغ تسویه: {amount:,}",
        )
        return True
    return True


@sync_to_async
def get_open_withdrawal_info(chat_id: int, user_id: int) -> dict | None:
    """آخرین درخواست تسویه باز (پیوی) — None اگر نداشته باشد."""
    from account.models import WithdrawalRequest

    rows = list(
        WithdrawalRequest.objects.filter(
            telegram_chat_id=int(chat_id),
            telegram_user_id=int(user_id),
            status__in=("pending", "receipt"),
        ).order_by("-created_at")
    )
    if not rows:
        return None
    latest = rows[0]
    return {
        "count": len(rows),
        "total_amount": sum(int(r.amount) for r in rows),
        "amount": int(latest.amount),
        "card": (latest.card_number or "").strip(),
        "card_name": (latest.card_name or "").strip(),
        "status": latest.status,
    }


def format_pending_pv_withdrawal_block(*, user_display: str = "", info: dict) -> str:
    """پیام هشدار وقتی ادمین می‌خواهد از گپ تسویه کند ولی درخواست پیوی باز است."""
    amount = int(info.get("total_amount") or info.get("amount") or 0)
    card = (info.get("card") or "").strip()
    card_name = (info.get("card_name") or "").strip()
    count = int(info.get("count") or 1)
    status = info.get("status") or "pending"
    status_fa = _STATUS_FA.get(status, status)

    lines = [
        "⚠️ تسویه از داخل گپ ممکن نیست",
        "━━━━━━━━━━━━━━━━━━",
    ]
    if user_display:
        lines.append(f"👤 کاربر: {user_display}")
    lines.append("📩 این کاربر قبلاً از پیوی ربات درخواست تسویه ثبت کرده است.")
    lines.append("")
    lines.append(f"📌 وضعیت: {status_fa}")
    lines.append(f"💰 مبلغ در انتظار: {amount:,} واحد")
    if count > 1:
        lines.append(f"🔢 تعداد درخواست باز: {count}")
    if card:
        lines.append(f"💳 کارت: <code>{card}</code>")
    if card_name:
        lines.append(f"👤 نام کارت: {card_name}")
    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        "💡 لطفاً همان درخواست را از پیوی ربات تأیید کنید.",
        "📌 برای لغو درخواست: روی پیام کاربر ریپلای کنید و «لغو درخواست تسویه» بفرستید.",
    ])
    return "\n".join(lines)


@sync_to_async
def _cancel_pending_withdrawals(chat_id: int, user_id: int, *, cancelled_by: int | None = None) -> dict:
    from account.models import WithdrawalRequest
    from django.utils import timezone

    rows = list(
        WithdrawalRequest.objects.filter(
            telegram_chat_id=int(chat_id),
            telegram_user_id=int(user_id),
            status__in=("pending", "receipt"),
        )
    )
    if not rows:
        return {"cancelled_count": 0, "total_amount": 0, "user_id": int(user_id)}

    total = sum(int(r.amount) for r in rows)
    now = timezone.now()
    WithdrawalRequest.objects.filter(
        id__in=[r.id for r in rows],
    ).update(status="cancelled", approved_by=cancelled_by, approved_at=now)
    return {"cancelled_count": len(rows), "total_amount": total, "user_id": int(user_id)}


async def admin_cancel_pending_withdrawals(
    bot: Bot, chat_id: int, user_id: int, *, cancelled_by: int | None = None, notify: bool = True,
) -> dict:
    result = await _cancel_pending_withdrawals(chat_id, user_id, cancelled_by=cancelled_by)
    if notify and result["cancelled_count"] > 0:
        try:
            await bot.send_message(
                int(user_id),
                f"❌ درخواست تسویه شما ({result['total_amount']:,} واحد) توسط مدیر لغو شد.\n"
                "💰 موجودی شما برای بازی و تراکنش‌ها آزاد شد.",
            )
        except Exception:
            pass
    return result


async def self_cancel_pending_withdrawals(bot: Bot, chat_id: int, user_id: int) -> dict:
    result = await _cancel_pending_withdrawals(chat_id, user_id, cancelled_by=user_id)
    if result["cancelled_count"] > 0:
        try:
            await bot.send_message(
                int(user_id),
                f"✅ درخواست تسویه شما ({result['total_amount']:,} واحد) لغو شد.\n"
                "💰 موجودی شما برای بازی و تراکنش‌ها آزاد شد.\n"
                "اکنون می‌توانید درخواست تسویه جدید ثبت کنید.",
            )
        except Exception:
            pass
    return result


async def handle_callback(call, bot: Bot) -> bool:
    data = call.data or ""
    state = _flow.get(call.from_user.id)
    if data == "wd:cancel":
        if not state:
            await call.answer("درخواستی در جریان نیست", show_alert=True)
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return True
        _flow.pop(call.from_user.id, None)
        await call.answer("لغو شد")
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.message.answer("❌ درخواست تسویه لغو شد.")
        return True
    if not state:
        await call.answer("نشست منقضی شده", show_alert=True)
        return True
    if data == "wd:card":
        state["step"] = "card"
        await call.answer()
        await call.message.answer(
            "💳 شماره کارت جدید ۱۶ رقمی را ارسال کنید.",
            reply_markup=_kb_cancel_only(),
        )
        return True
    if data == "wd:name":
        state["step"] = "name"
        await call.answer()
        await call.message.answer(
            "👤 نام و نام خانوادگی جدید را ارسال کنید.",
            reply_markup=_kb_cancel_only(),
        )
        return True
    if data == "wd:amount":
        if not state.get("card"):
            state["step"] = "card"
            await call.answer()
            await call.message.answer(
                "ابتدا شماره کارت ۱۶ رقمی را ارسال کنید.",
                reply_markup=_kb_cancel_only(),
            )
            return True
        if not state.get("name"):
            state["step"] = "name"
            await call.answer()
            await call.message.answer(
                "ابتدا نام صاحب کارت را ارسال کنید.",
                reply_markup=_kb_cancel_only(),
            )
            return True
        state["step"] = "amount"
        state["settle_kind"] = "custom"
        _, available, pending = await get_playable_balance(state["chat_id"], call.from_user.id)
        state["balance"] = available
        minimum = await get_min_withdrawal(state["chat_id"])
        min_line = min_withdrawal_hint(minimum)
        pending_line = f"\n⏳ در انتظار تسویه: {pending:,}" if pending > 0 else ""
        await call.answer()
        await call.message.answer(
            f"✏️ مبلغ جدید تسویه را وارد کنید (حداکثر {available:,})."
            f"{pending_line}{min_line}",
            reply_markup=_kb(True, True),
        )
        return True
    if data == "wd:full":
        if not state.get("card"):
            state["step"] = "card"
            await call.answer()
            await call.message.answer(
                "ابتدا شماره کارت ۱۶ رقمی را ارسال کنید.",
                reply_markup=_kb_cancel_only(),
            )
            return True
        if not state.get("name"):
            state["step"] = "name"
            await call.answer()
            await call.message.answer(
                "ابتدا نام صاحب کارت را ارسال کنید.",
                reply_markup=_kb_cancel_only(),
            )
            return True
        state["step"] = "amount"
        state["settle_kind"] = "full"
        _, available, _ = await get_playable_balance(state["chat_id"], call.from_user.id)
        state["balance"] = available
        await call.answer()
        return await handle_text(bot, call.from_user.id, str(available))
    return False
