"""افزایش موجودی — بدون مبلغ: مبلغ در پیوی ادمین وارد می‌شود (تلگرام)."""
from __future__ import annotations

import html
import re

import jdatetime
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from django.utils import timezone

from bot.finance import increase_wallet
from bot.helpers import safe_send, send_private, user_mention_id

_increase_wait: dict[int, dict] = {}
_request_wait: dict[int, dict] = {}
_manual_increase_wait: dict[int, int] = {}
_admin_deliveries: dict[int, list[tuple[int, int]]] = {}  # request_id → [(chat_id, message_id)]

TIP_DIRECT = (
    "\n\n💡 برای افزایش مخفی (بدون اعلام مبلغ در گروه): "
    "روی پیام کاربر ریپلای کنید و بنویسید «افزایش موجودی» یا «افزایش موجودی پیوی»."
)

_INC_STATUS_FA = {
    "waiting_receipt": "📎 در انتظار رسید کاربر",
    "pending": "⏳ در انتظار تأیید",
    "approved": "✅ تأیید شده",
    "cancelled": "❌ رد شده",
}


def remember_admin_delivery(request_id: int, chat_id: int, message_id: int) -> None:
    rid = int(request_id)
    item = (int(chat_id), int(message_id))
    bucket = _admin_deliveries.setdefault(rid, [])
    if item not in bucket:
        bucket.append(item)


def get_admin_deliveries(request_id: int) -> list[tuple[int, int]]:
    return list(_admin_deliveries.get(int(request_id), []))


def format_increase_admin_text(
    *,
    user_name: str,
    amount: int,
    status: str = "pending",
    refreshed: bool = False,
) -> str:
    head = "🔄 درخواست افزایش موجودی (بروزرسانی‌شده)" if refreshed else "📥 درخواست افزایش موجودی"
    status_line = _INC_STATUS_FA.get(status, status)
    return (
        f"{head}\n"
        f"📌 وضعیت: {status_line}\n"
        f"👤 کاربر: {html.escape(user_name)}\n"
        f"💰 مبلغ: {int(amount):,}\n"
        f"🧾 رسید پیوست شده است."
    )


async def broadcast_increase_admin_update(bot: Bot, request_id: int, text: str, kb) -> int:
    updated = 0
    for chat_id, message_id in get_admin_deliveries(request_id):
        try:
            await bot.edit_message_caption(
                chat_id=chat_id, message_id=message_id, caption=text, reply_markup=kb,
            )
            updated += 1
            continue
        except Exception:
            pass
        try:
            await bot.edit_message_text(
                text, chat_id=chat_id, message_id=message_id, reply_markup=kb,
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


def is_waiting_increase_amount(user_id: int) -> bool:
    return int(user_id) in _increase_wait


def set_increase_wait(user_id: int, data: dict) -> None:
    _increase_wait[int(user_id)] = data


def pop_increase_wait(user_id: int) -> dict | None:
    return _increase_wait.pop(int(user_id), None)


def get_increase_wait(user_id: int) -> dict | None:
    return _increase_wait.get(int(user_id))


def is_waiting_increase_request(user_id: int) -> bool:
    return int(user_id) in _request_wait


def set_manual_increase_wait(admin_id: int, request_id: int) -> None:
    _manual_increase_wait[int(admin_id)] = int(request_id)


def pop_manual_increase_wait(admin_id: int) -> int | None:
    return _manual_increase_wait.pop(int(admin_id), None)


def is_waiting_manual_increase(admin_id: int) -> bool:
    return int(admin_id) in _manual_increase_wait


def increase_request_admin_keyboard(request_id: int, *, status: str = "pending") -> InlineKeyboardMarkup:
    if status != "pending":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 پیام", callback_data=f"inc_req:message:{request_id}"),
                InlineKeyboardButton(text="🔄 بروزرسانی", callback_data=f"inc_req:refresh:{request_id}"),
            ],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید", callback_data=f"inc_req:approve:{request_id}"),
            InlineKeyboardButton(text="✏️ افزایش دستی", callback_data=f"inc_req:manual:{request_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ رد", callback_data=f"inc_req:reject:{request_id}"),
            InlineKeyboardButton(text="🚫 بلاک", callback_data=f"inc_req:block:{request_id}"),
        ],
        [
            InlineKeyboardButton(text="💬 پیام", callback_data=f"inc_req:message:{request_id}"),
            InlineKeyboardButton(text="🔄 بروزرسانی", callback_data=f"inc_req:refresh:{request_id}"),
        ],
    ])


def increase_request_user_keyboard(*, phase: str = "receipt") -> InlineKeyboardMarkup:
    """phase=amount → فقط لغو؛ phase=receipt → عوض کردن مبلغ + لغو."""
    if phase == "amount":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو", callback_data="inc_flow:cancel")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ عوض کردن مبلغ", callback_data="inc_flow:amount"),
            InlineKeyboardButton(text="❌ لغو", callback_data="inc_flow:cancel"),
        ],
    ])


def increase_request_manual_only_keyboard(request_id: int) -> InlineKeyboardMarkup:
    """بعد از تأیید — فقط پیام و بروزرسانی (بدون افزایش دستی مجدد)."""
    return increase_request_admin_keyboard(request_id, status="approved")


async def _receipt_prompt_text(group_id, amount: int, *, html: bool = True) -> str:
    """متن مرحلهٔ رسید + کارت ادمین فعال (شروع فعالیت)."""
    from bot.admin_accounting import active_cashier_payment_info

    payment = await active_cashier_payment_info(group_id)
    if payment and payment.get("card"):
        holder = payment.get("name") or ("مالک گروه" if payment.get("is_owner") else "ادمین فعال")
        if html:
            return (
                "💰 درخواست افزایش موجودی\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"مبلغ: <b>{amount:,}</b> واحد\n\n"
                f"💳 شماره کارت واریز:\n<code>{payment['card']}</code>\n"
                f"👤 به نام: <b>{holder}</b>\n\n"
                "🧾 مبلغ را به کارت بالا واریز کنید و رسید را به‌صورت عکس یا فایل بفرستید."
            )
        return (
            "💰 درخواست افزایش موجودی\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"مبلغ: **{amount:,}** واحد\n\n"
            f"💳 شماره کارت واریز: `{payment['card']}`\n"
            f"👤 به نام: {holder}\n\n"
            "🧾 مبلغ را به کارت بالا واریز کنید و رسید را به‌صورت عکس بفرستید."
        )
    if html:
        return (
            "💰 درخواست افزایش موجودی\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"مبلغ: <b>{amount:,}</b> واحد\n\n"
            "⚠️ فعلاً کارت ادمین فعال ثبت نشده؛ با مدیر هماهنگ کنید.\n\n"
            "🧾 بعد از واریز، رسید را به‌صورت عکس یا فایل بفرستید."
        )
    return (
        "💰 درخواست افزایش موجودی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"مبلغ: **{amount:,}** واحد\n\n"
        "⚠️ فعلاً کارت ادمین فعال ثبت نشده؛ با مدیر هماهنگ کنید.\n\n"
        "🧾 بعد از واریز، رسید را به‌صورت عکس بفرستید."
    )


async def start_increase_request_flow(
    bot: Bot, user_id: int, group_id: int, *, suggested_amount: int | None = None,
) -> bool:
    from bot.finance_ban import is_finance_banned, FINANCE_BAN_USER_TEXT
    if await is_finance_banned(group_id, user_id):
        await send_private(bot, user_id, FINANCE_BAN_USER_TEXT)
        return False
    suggested = int(suggested_amount or 0)
    if suggested > 0:
        _request_wait[int(user_id)] = {
            "group_id": int(group_id),
            "phase": "receipt",
            "amount": suggested,
        }
        prompt = await _receipt_prompt_text(group_id, suggested, html=True)
        ok = await send_private(
            bot, user_id,
            prompt,
            reply_markup=increase_request_user_keyboard(phase="receipt"),
        )
    else:
        _request_wait[int(user_id)] = {"group_id": int(group_id), "phase": "amount"}
        ok = await send_private(
            bot, user_id,
            "💰 درخواست افزایش موجودی\n\nمبلغ موردنظر را به‌صورت عددی بفرستید.",
            reply_markup=increase_request_user_keyboard(phase="amount"),
        )
    if not ok:
        _request_wait.pop(int(user_id), None)
    return ok


async def handle_increase_request_callback(call, bot: Bot) -> bool:
    data = call.data or ""
    if not data.startswith("inc_flow:"):
        return False
    uid = call.from_user.id
    state = _request_wait.get(int(uid))
    if data == "inc_flow:cancel":
        if not state:
            await call.answer("درخواستی در جریان نیست", show_alert=True)
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return True
        _request_wait.pop(int(uid), None)
        await call.answer("لغو شد")
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.message.answer("❌ درخواست افزایش لغو شد.")
        return True
    if data == "inc_flow:amount":
        if not state:
            await call.answer("نشست منقضی شده", show_alert=True)
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return True
        state.pop("amount", None)
        state["phase"] = "amount"
        await call.answer()
        await call.message.answer(
            "✏️ مبلغ جدید را به‌صورت عددی بفرستید.",
            reply_markup=increase_request_user_keyboard(phase="amount"),
        )
        return True
    return False


async def handle_increase_request_message(message: Message, bot: Bot) -> bool:
    data = _request_wait.get(int(message.from_user.id))
    if not data:
        return False
    if data.get("phase") == "receipt":
        await message.answer(
            "🧾 لطفاً رسید را فقط به‌صورت عکس یا فایل ارسال کنید.",
            reply_markup=increase_request_user_keyboard(phase="receipt"),
        )
        return True
    raw = (message.text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if raw in ("لغو", "انصراف", "cancel"):
        _request_wait.pop(int(message.from_user.id), None)
        await message.answer("❌ درخواست افزایش لغو شد.")
        return True
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(
            "⚠️ مبلغ معتبر نیست؛ فقط عدد مثبت بفرستید.",
            reply_markup=increase_request_user_keyboard(phase="amount"),
        )
        return True
    data["amount"] = int(raw)
    data["phase"] = "receipt"
    prompt = await _receipt_prompt_text(data["group_id"], data["amount"], html=True)
    await message.answer(prompt, parse_mode="HTML", reply_markup=increase_request_user_keyboard(phase="receipt"))
    return True


def manual_increase_prompt(req, *, already_processed: bool = False) -> str:
    text = (
        f"✏️ افزایش دستی\n"
        f"💰 مبلغ درخواست کاربر: {int(req.amount):,}\n\n"
    )
    if already_processed:
        text += (
            "⚠️ توجه: شما قبلاً این تراکنش را تأیید کرده‌اید یا افزایش دستی داده‌اید.\n"
            "اگر دوباره مبلغ بفرستید، موجودی کاربر مجدداً افزایش می‌یابد.\n\n"
        )
    text += (
        "مبلغ افزایش را به‌صورت عدد بفرستید.\n"
        "برای انصراف: لغو"
    )
    return text


async def handle_increase_request_receipt(message: Message, bot: Bot) -> bool:
    data = _request_wait.get(int(message.from_user.id))
    if not data:
        return False
    if data.get("phase") == "amount":
        await message.answer(
            "⚠️ اول باید مبلغ را به‌صورت عدد بفرستید.\n"
            "بعد از ثبت مبلغ، عکس رسید را ارسال کنید.\n"
            "مثال مبلغ: 50000",
            reply_markup=increase_request_user_keyboard(phase="amount"),
        )
        return True
    if data.get("phase") != "receipt":
        return False
    file_id, kind = "", ""
    if message.photo:
        file_id, kind = message.photo[-1].file_id, "photo"
    elif message.document:
        file_id, kind = message.document.file_id, "document"
    if not file_id:
        await message.answer("⚠️ رسید باید به‌صورت عکس یا فایل ارسال شود.")
        return True
    from account.models import BalanceIncreaseRequest
    from bot.wallet_helpers import collect_manager_ids

    req = await sync_to_async(BalanceIncreaseRequest.objects.create)(
        telegram_chat_id=data["group_id"], telegram_user_id=message.from_user.id,
        amount=data["amount"], status="pending", receipt_file_id=file_id, receipt_note=kind,
    )
    _request_wait.pop(int(message.from_user.id), None)
    await message.answer("✅ رسید دریافت شد؛ درخواست برای مدیران ارسال شد.")
    kb = increase_request_admin_keyboard(req.id, status="pending")
    text = format_increase_admin_text(
        user_name=message.from_user.full_name or str(message.from_user.id),
        amount=data["amount"],
        status="pending",
    )
    manager_ids = await collect_manager_ids(bot, data["group_id"])
    delivered = 0
    for mid in manager_ids:
        try:
            if kind == "photo":
                sent = await bot.send_photo(mid, file_id, caption=text, reply_markup=kb)
            else:
                sent = await bot.send_document(mid, file_id, caption=text, reply_markup=kb)
            remember_admin_delivery(req.id, mid, sent.message_id)
            delivered += 1
        except Exception:
            pass
    if delivered == 0:
        try:
            if kind == "photo":
                sent = await bot.send_photo(
                    data["group_id"], file_id,
                    caption=text + "\n\n⚠️ پیوی مدیران در دسترس نبود؛ تأیید از داخل گروه انجام شود.",
                    reply_markup=kb,
                )
            else:
                sent = await bot.send_document(
                    data["group_id"], file_id,
                    caption=text + "\n\n⚠️ پیوی مدیران در دسترس نبود؛ تأیید از داخل گروه انجام شود.",
                    reply_markup=kb,
                )
            remember_admin_delivery(req.id, data["group_id"], sent.message_id)
        except Exception:
            pass
    return True


@sync_to_async
def approve_increase_request_with_amount(request_id: int, admin_id: int, amount: int):
    """اولین تأیید با مبلغ دلخواه. برای سازگاری قدیمی False/True برمی‌گرداند."""
    req, mode = _apply_manual_topup_sync(request_id, admin_id, amount)
    return req, mode == "first"


@sync_to_async
def apply_manual_topup_amount(request_id: int, admin_id: int, amount: int):
    """(req, mode) — mode: first | additional | None"""
    return _apply_manual_topup_sync(request_id, admin_id, amount)


def _apply_manual_topup_sync(request_id: int, admin_id: int, amount: int):
    from django.db import transaction
    from account.models import BalanceIncreaseRequest

    amount = int(amount)
    with transaction.atomic():
        req = BalanceIncreaseRequest.objects.select_for_update().filter(id=request_id).first()
        if not req or req.status == "cancelled":
            return req, None
        if req.status == "pending":
            req.amount = amount
            req.status = "approved"
            req.approved_by = admin_id
            req.approved_at = timezone.now()
            req.save(update_fields=["amount", "status", "approved_by", "approved_at"])
            return req, "first"
        if req.status == "approved":
            req.approved_by = admin_id
            req.approved_at = timezone.now()
            req.save(update_fields=["approved_by", "approved_at"])
            return req, "additional"
        return req, None


async def apply_increase_request_approval(
    bot: Bot, req, approver_id: int, amount: int, admin_chat_id: int,
    *, is_extra: bool = False,
) -> int:
    from bot.wallet_helpers import notify_other_admins

    balance = await increase_wallet(
        req.telegram_chat_id,
        req.telegram_user_id,
        int(amount),
        admin_id=approver_id,
        description="افزایش دستی مجدد درخواست" if is_extra else "تأیید درخواست افزایش با رسید",
        receipt_file_id=req.receipt_file_id,
        receipt_note=req.receipt_note,
    )
    try:
        from bot.challenges import flush_challenge_breaks
        await flush_challenge_breaks(bot, req.telegram_chat_id)
    except Exception:
        pass
    try:
        user_chat = await bot.get_chat(req.telegram_user_id)
        user_name = user_chat.full_name or f"کاربر {req.telegram_user_id}"
    except Exception:
        user_name = f"کاربر {req.telegram_user_id}"
    try:
        approver_chat = await bot.get_chat(approver_id)
        approver_name = approver_chat.full_name or str(approver_id)
    except Exception:
        approver_name = str(approver_id)

    if is_extra:
        user_text = (
            f"✅ موجودی شما مجدداً افزایش یافت.\n"
            f"🛡 مدیر: {approver_name}\n"
            f"💰 مبلغ افزایش: {int(amount):,}\n"
            f"💰 موجودی جدید: {balance:,}"
        )
        group_text = (
            f"✅ افزایش دستی مجدد برای کاربر «{user_name}» به مبلغ {int(amount):,} "
            f"توسط مدیر «{approver_name}» انجام شد."
        )
        admin_text = f"✅ افزایش دستی مجدد به مبلغ {int(amount):,} انجام شد."
        notify_text = (
            f"📢 {approver_name} افزایش دستی مجدد برای کاربر «{user_name}» "
            f"به مبلغ {int(amount):,} انجام داد."
        )
    else:
        user_text = (
            f"✅ درخواست افزایش موجودی شما تأیید شد.\n"
            f"🛡 مدیر تأییدکننده: {approver_name}\n"
            f"💰 مبلغ افزایش: {int(amount):,}\n"
            f"💰 موجودی جدید: {balance:,}"
        )
        group_text = (
            f"✅ درخواست افزایش موجودی کاربر «{user_name}» به مبلغ {int(amount):,} "
            f"توسط مدیر «{approver_name}» تأیید شد."
        )
        admin_text = f"✅ درخواست به مبلغ {int(amount):,} تأیید شد."
        notify_text = (
            f"📢 {approver_name} درخواست افزایش موجودی کاربر «{user_name}» "
            f"به مبلغ {int(amount):,} را تأیید کرد."
        )

    try:
        from bot.pv_dice import _store_member_offer, _pv_member_offer_kb
        from bot.pv_search import pop_offer_search_after_increase, search_opponent_kb
        from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup

        tok = _store_member_offer(int(req.telegram_chat_id), int(req.telegram_user_id))
        offer_kb = _pv_member_offer_kb(tok)
        if pop_offer_search_after_increase(int(req.telegram_user_id)):
            rows = list(offer_kb.inline_keyboard) if offer_kb else []
            rows.append([IKB(text="🔍 جستجوی حریف", callback_data="pvs:go")])
            kb = InlineKeyboardMarkup(inline_keyboard=rows)
        else:
            kb = offer_kb
        await bot.send_message(
            req.telegram_user_id, user_text, reply_markup=kb,
        )
    except Exception:
        try:
            from bot.pv_search import pop_offer_search_after_increase, search_opponent_kb
            kb = search_opponent_kb() if pop_offer_search_after_increase(int(req.telegram_user_id)) else None
            await bot.send_message(req.telegram_user_id, user_text, reply_markup=kb)
        except Exception:
            pass
    await bot.send_message(req.telegram_chat_id, group_text)
    await bot.send_message(admin_chat_id, admin_text)
    await notify_other_admins(bot, req.telegram_chat_id, approver_id, notify_text)
    return balance


async def handle_manual_increase_amount_message(message: Message, bot: Bot) -> bool:
    admin_id = int(message.from_user.id)
    request_id = _manual_increase_wait.get(admin_id)
    if not request_id:
        return False

    raw = (message.text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if raw in ("لغو", "انصراف", "cancel"):
        pop_manual_increase_wait(admin_id)
        await message.answer("❌ افزایش دستی لغو شد.")
        return True

    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("⚠️ مبلغ نامعتبر است.\nیک عدد مثبت بفرستید یا «لغو» را بزنید.")
        return True

    req = await get_increase_request(request_id)
    if not req or req.status == "cancelled":
        pop_manual_increase_wait(admin_id)
        await message.answer("⚠️ این درخواست رد شده و قابل افزایش نیست.")
        return True
    if req.status != "pending":
        pop_manual_increase_wait(admin_id)
        await message.answer("⚠️ بعد از تأیید، افزایش دستی ممکن نیست.")
        return True

    amount = int(raw)
    req, mode = await apply_manual_topup_amount(request_id, admin_id, amount)
    pop_manual_increase_wait(admin_id)
    if not mode:
        await message.answer("⚠️ امکان افزایش دستی برای این درخواست وجود ندارد.")
        return True

    await apply_increase_request_approval(
        bot, req, admin_id, amount, admin_id, is_extra=(mode == "additional"),
    )
    return True


@sync_to_async
def approve_increase_request(request_id: int, admin_id: int):
    from django.db import transaction
    from account.models import BalanceIncreaseRequest
    with transaction.atomic():
        req = BalanceIncreaseRequest.objects.select_for_update().filter(id=request_id).first()
        if not req or req.status != "pending":
            return req, False
        req.status = "approved"
        req.approved_by = admin_id
        req.approved_at = timezone.now()
        req.save(update_fields=["status", "approved_by", "approved_at"])
        return req, True


@sync_to_async
def get_increase_request(request_id: int):
    from account.models import BalanceIncreaseRequest
    return BalanceIncreaseRequest.objects.filter(id=request_id).first()


@sync_to_async
def reject_increase_request(request_id: int, admin_id: int):
    from django.db import transaction
    from account.models import BalanceIncreaseRequest
    with transaction.atomic():
        req = BalanceIncreaseRequest.objects.select_for_update().filter(id=request_id).first()
        if not req or req.status != "pending":
            return req, False
        req.status = "cancelled"
        req.approved_by = admin_id
        req.approved_at = timezone.now()
        req.save(update_fields=["status", "approved_by", "approved_at"])
        return req, True


def parse_increase_command(text: str) -> tuple[str, int | None]:
    raw = (text or "").strip()
    parts = raw.split()
    if raw in ("درخواست افزایش", "درخواست افزایش موجودی"):
        return "pv", None
    if len(parts) >= 2 and parts[0] == "افزایش" and parts[1] == "موجودی":
        if len(parts) == 2:
            return "pv", None
        if len(parts) >= 3:
            if parts[2] in ("پیوی", "پیو", "در پیوی"):
                return "pv", None
            try:
                return "direct", int(parts[2])
            except ValueError:
                return "invalid", None
        return "invalid", None
    if len(parts) == 2 and parts[0] == "افزایش":
        try:
            return "direct", int(parts[1])
        except ValueError:
            return "invalid", None
    return "invalid", None


_DIG = r"[0-9۰-۹٠-٩]+"
INCREASE_COMMAND_RE = (
    rf"^(?:"
    rf"درخواست افزایش(?: موجودی)?"
    rf"|افزایش(?: موجودی)?(?:\s+(?:پیوی|پیو|در پیوی|{_DIG}))?"
    rf"|افزایش\s+{_DIG}"
    rf")$"
)
SETTLE_COMMAND_RE = (
    rf"^(?:"
    rf"درخواست تسویه(?: حساب)?"
    rf"|تسویه(?: حساب)?"
    rf"|تسویه\s+{_DIG}"
    rf"|تسویه کاربر\s+{_DIG}"
    rf"|تسویه (?:همه حساب ها|تمام حساب ها|حساب ها)"
    rf")$"
)
MEMBER_INCREASE_TEXTS = frozenset({
    "افزایش",
    "افزایش موجودی",
    "درخواست افزایش",
    "درخواست افزایش موجودی",
})
MEMBER_SETTLE_TEXTS = frozenset({
    "تسویه",
    "تسویه حساب",
    "درخواست تسویه",
    "درخواست تسویه حساب",
})
_INCREASE_COMMAND_RX = re.compile(INCREASE_COMMAND_RE)
_SETTLE_COMMAND_RX = re.compile(SETTLE_COMMAND_RE)


def is_increase_command(text: str) -> bool:
    """فقط دستور واقعی افزایش — نه «افزایش بده / افزایش میدی؟»."""
    return bool(_INCREASE_COMMAND_RX.fullmatch((text or "").strip()))


def is_settle_command(text: str) -> bool:
    """فقط دستور واقعی تسویه — نه «تسویه میکنی؟ / منو تسویه کن»."""
    return bool(_SETTLE_COMMAND_RX.fullmatch((text or "").strip()))


async def start_increase_pv_flow(
    bot: Bot, chat_id: int, admin_id: int, target_id: int, group_msg_id: int,
) -> None:
    set_increase_wait(admin_id, {
        "chat_id": chat_id,
        "target_id": target_id,
        "group_msg_id": group_msg_id,
        "admin_id": admin_id,
    })
    await safe_send(
        bot, chat_id,
        (
            "🔐 لطفاً داخل پیوی ربات مبلغ افزایش موجودی را وارد کنید.\n\n"
            "برای انصراف در پیوی بنویسید: <code>لغو</code>"
        ),
        reply_to=group_msg_id,
    )
    prompt = (
        "💰 افزایش موجودی\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "مبلغ افزایش را به‌صورت عدد بفرستید.\n"
        "مثال: <code>5000</code>\n\n"
        "برای انصراف: <code>لغو</code>"
    )
    ok = await send_private(bot, admin_id, prompt)
    if not ok:
        await safe_send(
            bot, chat_id,
            "⚠️ برای دریافت پیام در پیوی، یک‌بار ربات را /start کنید.",
            reply_to=group_msg_id,
        )


async def handle_increase_amount_message(message: Message, bot: Bot) -> bool:
    admin_id = message.from_user.id
    wait = get_increase_wait(admin_id)
    if not wait:
        return False

    raw = (message.text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if raw in ("لغو", "انصراف", "cancel"):
        pop_increase_wait(admin_id)
        await message.answer("❌ افزایش موجودی لغو شد.")
        return True

    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("⚠️ مبلغ نامعتبر است.\nیک عدد مثبت بفرستید یا «لغو» را بزنید.")
        return True

    amount = int(raw)
    pop_increase_wait(admin_id)
    chat_id = int(wait["chat_id"])
    target_id = int(wait["target_id"])
    group_msg_id = wait.get("group_msg_id")

    new_balance = await increase_wallet(chat_id, target_id, amount, admin_id=admin_id)
    try:
        from bot.challenges import flush_challenge_breaks
        await flush_challenge_breaks(bot, chat_id)
    except Exception:
        pass
    user_tag = await user_mention_id(target_id, bot, chat_id)
    admin_tag = await user_mention_id(admin_id, bot, chat_id)

    group_text = (
        "✅ عملیات افزایش موجودی با موفقیت انجام شد\n\n"
        f"👤 کاربر: {user_tag}\n"
        f"🛡 مدیر اجراکننده: {admin_tag}\n\n"
        f"💰 مبلغ افزایش: مخفی\n"
        f"📊 موجودی فعلی: مخفی"
    )
    await safe_send(bot, chat_id, group_text, reply_to=group_msg_id)

    try:
        chat = await bot.get_chat(chat_id)
        group_name = chat.title or str(chat_id)
    except Exception:
        group_name = str(chat_id)

    admin_name = message.from_user.full_name or message.from_user.first_name or "ادمین"
    date_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
    target_pv = (
        "💰 افزایش موجودی حساب\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ {amount:,} واحد اعتباری به حساب شما افزوده شد.\n\n"
        f"📊 موجودی فعلی: {new_balance:,} واحد اعتباری\n"
        f"🕒 تاریخ: {date_str}\n"
        f"🏷 گروه: {html.escape(group_name)}\n\n"
        f"🛡 ثبت توسط مدیر: {html.escape(admin_name)}"
    )
    ok = await send_private(bot, target_id, target_pv)
    if not ok:
        await safe_send(
            bot, chat_id,
            "⚠️ پیام جزئیات برای کاربر ارسال نشد (ربات را در پیوی /start نکرده).",
            reply_to=group_msg_id,
        )

    await message.answer(
        "✅ افزایش موجودی ثبت شد.\n\n"
        f"💰 مبلغ: {amount:,} واحد\n"
        f"📊 موجودی جدید کاربر: {new_balance:,} واحد\n"
        f"🏷 گروه: {html.escape(group_name)}\n\n"
        "💡 دفعه‌های بعد همین‌طور کافی است: روی پیام کاربر ریپلای کنید "
        "و فقط بنویسید «افزایش موجودی»."
    )
    return True
