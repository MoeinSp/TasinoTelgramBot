"""افزایش موجودی — بدون مبلغ: مبلغ در پیوی ادمین وارد می‌شود (تلگرام)."""
from __future__ import annotations

import html
import jdatetime
from aiogram import Bot
from aiogram.types import Message

from bot.finance import increase_wallet
from bot.helpers import safe_send, send_private, user_mention_id

_increase_wait: dict[int, dict] = {}

TIP_DIRECT = (
    "\n\n💡 برای افزایش مخفی (بدون اعلام مبلغ در گروه): "
    "روی پیام کاربر ریپلای کنید و بنویسید «افزایش موجودی» یا «افزایش موجودی پیوی»."
)


def is_waiting_increase_amount(user_id: int) -> bool:
    return int(user_id) in _increase_wait


def set_increase_wait(user_id: int, data: dict) -> None:
    _increase_wait[int(user_id)] = data


def pop_increase_wait(user_id: int) -> dict | None:
    return _increase_wait.pop(int(user_id), None)


def get_increase_wait(user_id: int) -> dict | None:
    return _increase_wait.get(int(user_id))


def parse_increase_command(text: str) -> tuple[str, int | None]:
    raw = (text or "").strip()
    parts = raw.split()
    if len(parts) >= 2 and parts[0] == "افزایش" and parts[1] == "موجودی":
        if len(parts) == 2:
            return "pv", None
        if len(parts) == 3:
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
