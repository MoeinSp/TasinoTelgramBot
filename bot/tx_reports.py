"""گزارش تراکنش‌ها — متن و کیبورد اینلاین (پیوی تلگرام)."""
from __future__ import annotations

import html
import jdatetime
from aiogram import Bot
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup

from bot.finance import get_balance, get_transactions, get_transactions_count
from bot.helpers import deliver_private_or_warn, send_private, user_mention_id

PER_PAGE = 5


def _tx_label(tx_type: str) -> tuple[str, str]:
    labels = {
        "admin_increase": ("افزایش موجودی", "➕"),
        "admin_decrease": ("کاهش موجودی", "➖"),
        "admin_clear": ("تسویه حساب", "🧾"),
        "bet": ("شرط مسابقه", "🎲"),
        "win": ("برد مسابقه", "🏆"),
    }
    return labels.get(tx_type, ("تراکنش", "🔹"))


def tx_report_kb(chat_id: int, target_id: int, page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    if total_pages <= 1:
        return InlineKeyboardMarkup(inline_keyboard=[[
            IKB(text="📑 گزارش تراکنش‌ها", callback_data=f"txr:{chat_id}:{target_id}:1"),
        ]])
    row = []
    if page > 1:
        row.append(IKB(text="◀️ قبلی", callback_data=f"txr:{chat_id}:{target_id}:{page - 1}"))
    row.append(IKB(text=f"📑 {page}/{total_pages}", callback_data=f"txr:{chat_id}:{target_id}:{page}"))
    if page < total_pages:
        row.append(IKB(text="بعدی ▶️", callback_data=f"txr:{chat_id}:{target_id}:{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def build_tx_report_text(
    chat_id: int,
    bot: Bot,
    target_id: int,
    page: int = 1,
    *,
    group_name: str | None = None,
) -> tuple[str, int]:
    limit = PER_PAGE
    total = await get_transactions_count(chat_id, target_id)
    total_pages = max(1, (total + limit - 1) // limit) if total else 1
    page = max(1, min(page, total_pages))

    if total == 0:
        try:
            member = await bot.get_chat_member(chat_id, target_id)
            name = html.escape(member.user.full_name or member.user.first_name or "کاربر")
        except Exception:
            name = "کاربر"
        text = (
            "📭 گزارش تراکنش‌ها\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 {name}\n"
            f"🆔 <code>{target_id}</code>\n"
        )
        if group_name:
            text += f"🏷 گروه: {html.escape(group_name)}\n"
        text += "\nتراکنشی ثبت نشده است."
        return text, 1

    offset = (page - 1) * limit
    transactions = await get_transactions(chat_id, target_id, limit, offset)
    current_balance = await get_balance(chat_id, target_id)
    tag = await user_mention_id(target_id, bot, chat_id)

    lines = [
        "📊 گزارش تراکنش‌ها",
        "━━━━━━━━━━━━━━━━━━",
        f"👤 {tag}",
        f"🆔 <code>{target_id}</code>",
    ]
    if group_name:
        lines.append(f"🏷 گروه: {html.escape(group_name)}")
    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        f"📄 صفحه {page} از {total_pages}",
        f"💰 موجودی فعلی: {current_balance:,} واحد",
        "━━━━━━━━━━━━━━━━━━",
        "",
    ])

    for t in transactions:
        action, emoji = _tx_label(t.type)
        j_time = jdatetime.datetime.fromgregorian(datetime=t.created_at).strftime("%Y/%m/%d - %H:%M")
        lines.append(f"{emoji} {action}")
        lines.append(f"   💰 مبلغ: {t.amount:,} واحد")
        lines.append(f"   📊 موجودی پس از: {t.balance_after:,} واحد")
        if t.type in ("bet", "win"):
            lines.append("   🤖 عامل: ربات")
        elif t.admin_id:
            admin_tag = await user_mention_id(t.admin_id, bot, chat_id)
            lines.append(f"   👤 عامل: {admin_tag}")
        else:
            lines.append("   🤖 عامل: ربات")
        if t.description:
            lines.append(f"   📝 {html.escape(t.description)}")
        lines.append(f"   🕒 {j_time}")
        lines.append("")

    if total_pages > 1:
        lines.append("💡 از دکمه‌های زیر بین صفحات جابه‌جا شوید.")
    return "\n".join(lines), total_pages
