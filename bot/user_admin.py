"""مدیریت کاربر با شناسه در پیوی ربات (ادمین/مالک)."""
from __future__ import annotations

import html
import re

from aiogram import Bot
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton as IKB,
    InlineKeyboardMarkup,
    Message,
)
from asgiref.sync import sync_to_async

from bot.cache_manager import is_admin, is_owner
from bot.constants import CREATOR_USER_ID
from bot.finance import clear_wallet, decrease_wallet, get_balance, increase_wallet
from bot.helpers import send_private
from bot.utils import normalize_numbers

_USER_CMD_RE = re.compile(
    r"^(?:کاربر|شناسه\s*کاربر|مدیریت\s*کاربر)\s+(\d{5,})$",
    re.UNICODE,
)

# admin_id → {"mode": "inc"|"dec"|"ban", "group_id", "target_id"}
_amount_wait: dict[int, dict] = {}


def is_waiting_user_admin(user_id: int) -> bool:
    return int(user_id) in _amount_wait


def clear_user_admin_wait(user_id: int) -> None:
    _amount_wait.pop(int(user_id), None)


def parse_user_admin_command(text: str) -> int | None:
    if not text:
        return None
    m = _USER_CMD_RE.match(normalize_numbers(text).strip())
    if not m:
        return None
    return int(m.group(1))


def _can_manage(group_id: int, admin_id: int) -> bool:
    if int(admin_id) == int(CREATOR_USER_ID):
        return True
    return is_owner(group_id, admin_id) or is_admin(group_id, admin_id)


@sync_to_async
def _list_manageable_groups(admin_id: int, target_id: int) -> list[tuple[int, str, int]]:
    """[(group_id, name, balance), ...] گروه‌هایی که ادمین دسترسی دارد و کاربر عضو/حساب دارد."""
    from account.models import TelegramGroup, TelegramGroupMember

    aid = int(admin_id)
    tid = int(target_id)
    memberships = list(
        TelegramGroupMember.objects.filter(telegram_user_id=tid)
        .exclude(role="banned")
        .values_list("telegram_chat_id", "point", "alias")[:40]
    )
    if not memberships and aid == int(CREATOR_USER_ID):
        # سازنده: اگر عضو ثبت نشده، باز هم از روی موجودی/گروه‌های اخیر تلاش نکن — خالی
        return []

    out = []
    for gid, point, alias in memberships:
        gid = int(gid)
        if not _can_manage(gid, aid):
            continue
        g = TelegramGroup.objects.filter(telegram_chat_id=gid).only("name").first()
        name = (g.name if g else "") or str(gid)
        out.append((gid, name, int(point or 0)))
    out.sort(key=lambda r: r[2], reverse=True)
    return out


@sync_to_async
def _target_display(group_id: int, target_id: int) -> str:
    from account.models import TelegramGroupMember

    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=int(group_id), telegram_user_id=int(target_id),
    ).only("alias").first()
    if m and (m.alias or "").strip():
        return (m.alias or "").strip()
    return f"کاربر {target_id}"


def _menu_kb(group_id: int, target_id: int) -> InlineKeyboardMarkup:
    g, u = int(group_id), int(target_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            IKB(text="📈 افزایش", callback_data=f"ua:inc:{g}:{u}"),
            IKB(text="📉 کاهش", callback_data=f"ua:dec:{g}:{u}"),
        ],
        [
            IKB(text="💳 موجودی", callback_data=f"ua:bal:{g}:{u}"),
            IKB(text="📑 گزارش", callback_data=f"ua:tx:{g}:{u}"),
        ],
        [
            IKB(text="✅ تسویه کامل", callback_data=f"ua:set:{g}:{u}"),
        ],
        [
            IKB(text="🚫 بن مالی", callback_data=f"ua:ban:{g}:{u}"),
            IKB(text="🔓 آنبن مالی", callback_data=f"ua:unban:{g}:{u}"),
        ],
        [
            IKB(text="🚫 بن از گروه", callback_data=f"ua:kick:{g}:{u}"),
        ],
    ])


def _groups_kb(target_id: int, groups: list[tuple[int, str, int]]) -> InlineKeyboardMarkup:
    rows = []
    for gid, name, bal in groups[:12]:
        label = (name[:22] + "…") if len(name) > 23 else name
        rows.append([IKB(
            text=f"📍 {label} · {bal:,}",
            callback_data=f"ua:open:{gid}:{int(target_id)}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _panel_text(group_id: int, target_id: int) -> str:
    name = html.escape(await _target_display(group_id, target_id))
    bal = await sync_to_async(get_balance)(group_id, target_id)
    from bot.finance_ban import get_finance_ban
    ban = await get_finance_ban(group_id, target_id)
    ban_line = ""
    if ban:
        ban_line = f"\n🚫 بن مالی: فعال — {html.escape(str(ban.get('reason') or ''))}"
    return (
        "👤 مدیریت کاربر\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 {name}\n"
        f"🆔 <code>{int(target_id)}</code>\n"
        f"📍 گروه: <code>{int(group_id)}</code>\n"
        f"💳 موجودی: <b>{int(bal):,}</b> واحد"
        f"{ban_line}\n\n"
        "یک عملیات را انتخاب کنید:"
    )


async def start_user_admin(
    bot: Bot, admin_id: int, target_id: int, *, message: Message | None = None,
    preferred_group_id: int | None = None,
) -> None:
    groups = await _list_manageable_groups(admin_id, target_id)

    async def _reply(text: str, **kw):
        if message:
            await message.answer(text, parse_mode="HTML", **kw)
        else:
            await send_private(bot, admin_id, text, reply_markup=kw.get("reply_markup"))

    if preferred_group_id is not None and _can_manage(int(preferred_group_id), admin_id):
        text = await _panel_text(preferred_group_id, target_id)
        await _reply(text, reply_markup=_menu_kb(preferred_group_id, target_id))
        return

    if not groups:
        await _reply(
            "❌ گروهی پیدا نشد که هم این کاربر در آن باشد و هم شما ادمین/مالک آن باشید.\n\n"
            f"شناسه: <code>{int(target_id)}</code>"
        )
        return

    if len(groups) == 1:
        gid, _, _ = groups[0]
        text = await _panel_text(gid, target_id)
        await _reply(text, reply_markup=_menu_kb(gid, target_id))
        return

    lines = [
        "👤 مدیریت کاربر\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <code>{int(target_id)}</code>\n\n"
        "گروه مورد نظر را انتخاب کنید:",
    ]
    await _reply("\n".join(lines), reply_markup=_groups_kb(target_id, groups))


async def handle_user_admin_text(message: Message, bot: Bot) -> bool:
    """پردازش مبلغ افزایش/کاهش یا دلیل بن مالی."""
    admin_id = message.from_user.id
    wait = _amount_wait.get(int(admin_id))
    if not wait:
        return False

    raw = normalize_numbers((message.text or "").strip())
    if raw in ("لغو", "انصراف", "cancel"):
        clear_user_admin_wait(admin_id)
        await message.answer("❌ عملیات لغو شد.")
        return True

    mode = wait.get("mode")
    group_id = int(wait["group_id"])
    target_id = int(wait["target_id"])

    if not _can_manage(group_id, admin_id):
        clear_user_admin_wait(admin_id)
        await message.answer("❌ دسترسی ندارید.")
        return True

    if mode == "ban":
        reason = (message.text or "").strip()
        if len(reason) < 2:
            await message.answer("⚠️ دلیل بن را بنویسید (حداقل ۲ کاراکتر) یا «لغو».")
            return True
        from bot.finance_ban import ban_finance, format_group_finance_ban_announce
        clear_user_admin_wait(admin_id)
        ban = await ban_finance(group_id, target_id, admin_id, reason)
        try:
            name = await _target_display(group_id, target_id)
            announce = format_group_finance_ban_announce(
                user_display=name, reason=ban["reason"], admin_display=str(admin_id),
            )
            await bot.send_message(group_id, announce)
        except Exception:
            pass
        await message.answer(
            f"✅ بن مالی ثبت شد.\n📝 دلیل: {html.escape(ban['reason'])}",
            parse_mode="HTML",
            reply_markup=_menu_kb(group_id, target_id),
        )
        return True

    amount_raw = raw.replace(",", "").replace("_", "").strip()
    if not amount_raw.isdigit() or int(amount_raw) <= 0:
        await message.answer("⚠️ مبلغ نامعتبر است.\nعدد مثبت بفرستید یا «لغو».")
        return True
    amount = int(amount_raw)
    clear_user_admin_wait(admin_id)

    if mode == "inc":
        new_bal = await increase_wallet(group_id, target_id, amount, admin_id=admin_id)
        try:
            from bot.challenges import flush_challenge_breaks
            await flush_challenge_breaks(bot, group_id)
        except Exception:
            pass
        await message.answer(
            f"✅ موجودی افزایش یافت.\n💰 +{amount:,}\n📊 موجودی: {int(new_bal):,}",
            reply_markup=_menu_kb(group_id, target_id),
        )
        return True

    if mode == "dec":
        new_bal = await decrease_wallet(group_id, target_id, amount, admin_id=admin_id)
        await message.answer(
            f"✅ موجودی کاهش یافت.\n💰 −{amount:,}\n📊 موجودی: {int(new_bal):,}",
            reply_markup=_menu_kb(group_id, target_id),
        )
        return True

    return True


async def handle_user_admin_callback(call: CallbackQuery, bot: Bot) -> bool:
    data = call.data or ""
    if not data.startswith("ua:"):
        return False

    admin_id = call.from_user.id
    parts = data.split(":")
    if len(parts) < 4:
        await call.answer("نامعتبر", show_alert=True)
        return True

    action, group_s, user_s = parts[1], parts[2], parts[3]
    try:
        group_id = int(group_s)
        target_id = int(user_s)
    except ValueError:
        await call.answer("نامعتبر", show_alert=True)
        return True

    if not _can_manage(group_id, admin_id):
        await call.answer("دسترسی ندارید.", show_alert=True)
        return True

    await call.answer()

    async def _edit(text: str, kb=None):
        try:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await send_private(bot, admin_id, text, reply_markup=kb)

    if action == "open":
        clear_user_admin_wait(admin_id)
        # اگر دکمه از گپ نتایج زده شد، پنل را در پیوی بفرست
        chat_type = getattr(call.message.chat, "type", "") if call.message else ""
        text = await _panel_text(group_id, target_id)
        kb = _menu_kb(group_id, target_id)
        if chat_type in ("group", "supergroup"):
            ok = await send_private(bot, admin_id, text, reply_markup=kb)
            if ok:
                await call.message.answer("📲 پنل مدیریت در پیوی ارسال شد.")
            else:
                await call.message.answer("⚠️ اول ربات را در پیوی /start کنید.")
        else:
            await _edit(text, kb)
        return True

    if action == "bal":
        text = await _panel_text(group_id, target_id)
        await _edit(text, _menu_kb(group_id, target_id))
        return True

    if action == "tx":
        from bot.tx_reports import build_tx_report_text, tx_report_kb
        text, total_pages = await build_tx_report_text(group_id, bot, target_id, page=1)
        kb = tx_report_kb(group_id, target_id, 1, total_pages)
        await _edit(text, kb)
        return True

    if action == "set":
        cleared = await clear_wallet(group_id, target_id, admin_id=admin_id)
        await _edit(
            f"✅ تسویه کامل انجام شد.\n💰 مبلغ: {int(cleared or 0):,}\n\n" + await _panel_text(group_id, target_id),
            _menu_kb(group_id, target_id),
        )
        return True

    if action == "unban":
        from bot.finance_ban import unban_finance, format_group_finance_unban_announce
        removed = await unban_finance(group_id, target_id)
        if removed:
            try:
                name = await _target_display(group_id, target_id)
                announce = format_group_finance_unban_announce(
                    user_display=name, admin_display=str(admin_id),
                )
                await bot.send_message(group_id, announce)
            except Exception:
                pass
            msg = "🔓 بن مالی برداشته شد."
        else:
            msg = "ℹ️ بن مالی فعالی نبود."
        await _edit(msg + "\n\n" + await _panel_text(group_id, target_id), _menu_kb(group_id, target_id))
        return True

    if action == "kick":
        try:
            await bot.ban_chat_member(group_id, target_id)
            from bot.helpers import db_ban_user
            try:
                await sync_to_async(db_ban_user)(group_id, target_id)
            except Exception:
                pass
            msg = "✅ کاربر از گروه بن شد."
        except Exception as e:
            msg = f"❌ بن از گروه ناموفق:\n{e}"
        await _edit(msg + "\n\n" + await _panel_text(group_id, target_id), _menu_kb(group_id, target_id))
        return True

    if action == "inc":
        _amount_wait[int(admin_id)] = {"mode": "inc", "group_id": group_id, "target_id": target_id}
        await _edit(
            "📈 افزایش موجودی\nمبلغ را عدد بفرستید.\nبرای لغو: لغو",
            InlineKeyboardMarkup(inline_keyboard=[[
                IKB(text="❌ لغو", callback_data=f"ua:open:{group_id}:{target_id}"),
            ]]),
        )
        return True

    if action == "dec":
        _amount_wait[int(admin_id)] = {"mode": "dec", "group_id": group_id, "target_id": target_id}
        await _edit(
            "📉 کاهش موجودی\nمبلغ را عدد بفرستید.\nبرای لغو: لغو",
            InlineKeyboardMarkup(inline_keyboard=[[
                IKB(text="❌ لغو", callback_data=f"ua:open:{group_id}:{target_id}"),
            ]]),
        )
        return True

    if action == "ban":
        _amount_wait[int(admin_id)] = {"mode": "ban", "group_id": group_id, "target_id": target_id}
        await _edit(
            "🚫 بن مالی\nدلیل را بنویسید.\nبرای لغو: لغو",
            InlineKeyboardMarkup(inline_keyboard=[[
                IKB(text="❌ لغو", callback_data=f"ua:open:{group_id}:{target_id}"),
            ]]),
        )
        return True

    return True
