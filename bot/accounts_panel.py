"""پنل اینلاین حساب‌های فعال — پیوی ادمین (تلگرام)."""
from __future__ import annotations

import html
import jdatetime
from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton as IKB, InlineKeyboardMarkup, Message

from bot.cache_manager import is_admin, is_owner
from bot.finance import (
    clear_all_wallets, clear_wallet, decrease_wallet,
    get_active_accounts, get_balance,
)
from bot.helpers import send_private
from bot.tx_reports import build_tx_report_text, tx_report_kb

PER_PAGE = 5

_GROUP_SUFFIXES = frozenset({
    "همون گروه", "همین گروه", "گروه", "در گروه",
})
_PM_SUFFIXES = frozenset({
    "پیوی", "پیو", "در پیوی",
})


def parse_accounts_command(text: str) -> str | None:
    """'pm' | 'group' | None — حساب ها → گروه؛ حساب ها پیوی → پیوی."""
    if not text:
        return None
    t = text.strip()
    if "مخفی" in t:
        return None
    if t.startswith("حساب‌ها"):
        rest = t[6:].strip()
    elif t.startswith("حساب ها"):
        rest = t[7:].strip()
    else:
        return None
    if not rest:
        return "group"
    if rest in _PM_SUFFIXES:
        return "pm"
    if rest in _GROUP_SUFFIXES:
        return "group"
    return None

# انتظار مبلغ تسویه دلخواه: user_id → dict
_amount_wait: dict[int, dict] = {}


def is_waiting_settle_amount(user_id: int) -> bool:
    return int(user_id) in _amount_wait


def set_amount_wait(user_id: int, data: dict) -> None:
    _amount_wait[int(user_id)] = data


def pop_amount_wait(user_id: int) -> dict | None:
    return _amount_wait.pop(int(user_id), None)


def get_amount_wait(user_id: int) -> dict | None:
    return _amount_wait.get(int(user_id))


def _cb(chat_id: int, *parts) -> str:
    return "acc:" + ":".join([str(chat_id), *[str(p) for p in parts]])


def _label_name(name: str, max_len: int = 12) -> str:
    name = (name or "کاربر").strip()
    return name if len(name) <= max_len else name[: max_len - 1] + "…"


_PLACEHOLDER_NAMES = frozenset({"کاربر", "user", "unknown", "کاربر ناشناس"})


def _is_meaningful_name(name: str | None) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if n.lower() in _PLACEHOLDER_NAMES:
        return False
    return not n.isdigit()


def _account_display_name(acc: dict, names: dict[int, str], uid: int) -> str:
    alias = (acc.get("alias") or "").strip()
    if _is_meaningful_name(alias):
        return alias
    return (names.get(uid) or "کاربر").strip() or "کاربر"


async def _resolve_names(bot: Bot, chat_id: int, accounts: list[dict]) -> dict[int, str]:
    names: dict[int, str] = {}
    for acc in accounts:
        uid = int(acc["telegram_user_id"])
        alias = (acc.get("alias") or "").strip()
        if _is_meaningful_name(alias):
            names[uid] = alias
            continue
        try:
            member = await bot.get_chat_member(chat_id, uid)
            tg_name = (member.user.full_name or member.user.first_name or "").strip()
            names[uid] = tg_name if _is_meaningful_name(tg_name) else "کاربر"
        except Exception:
            names[uid] = "کاربر"
    return names


def count_missing_account_names(accounts: list[dict], names: dict[int, str]) -> int:
    missing = 0
    for acc in accounts:
        uid = int(acc["telegram_user_id"])
        if not _is_meaningful_name(_account_display_name(acc, names, uid)):
            missing += 1
    return missing


def build_accounts_name_hint_inline(missing_count: int) -> str | None:
    if missing_count <= 0:
        return None
    who = f"{missing_count} نفر" if missing_count > 1 else "۱ نفر"
    return (
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 {who} در لیست بدون نام هستند.\n\n"
        "برای ثبت نام، روی پیام عضو در گروه ریپلای کنید:\n"
        "<code>تنظیم نام علی</code>\n"
        "<i>به‌جای «علی» نام دلخواه را بنویسید.</i>"
    )

def _admin_display_name(call: CallbackQuery | Message) -> str:
    user = call.from_user if hasattr(call, "from_user") else None
    if not user:
        return "ادمین"
    return (user.full_name or user.first_name or "ادمین").strip() or "ادمین"


async def _notify_user_settled(
    bot: Bot,
    *,
    target_id: int,
    admin_name: str,
    amount: int,
    group_name: str | None,
    full: bool,
    new_balance: int = 0,
) -> None:
    j_time = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
    safe_admin = html.escape(admin_name)
    if full:
        body = (
            "🧾 تسویه حساب\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💸 مبلغ {amount:,} واحد اعتباری از حساب شما صفر شد.\n"
            f"📊 موجودی فعلی: 0 واحد\n"
            f"🕒 تاریخ: {j_time}\n"
            f"🛡 توسط مدیر: {safe_admin}\n"
        )
    else:
        body = (
            "🧾 تسویه جزئی حساب\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💸 مبلغ {amount:,} واحد از حساب شما کسر شد.\n"
            f"📊 موجودی فعلی: {new_balance:,} واحد\n"
            f"🕒 تاریخ: {j_time}\n"
            f"🛡 توسط مدیر: {safe_admin}\n"
        )
    if group_name:
        body += f"🏷 گروه: {html.escape(group_name)}\n"
    body += "\n✔ حساب شما به‌روزرسانی شد."
    await send_private(bot, target_id, body)


async def build_accounts_text(
    chat_id: int,
    bot: Bot,
    page: int = 1,
    *,
    group_name: str | None = None,
) -> tuple[str, int, list[dict], dict[int, str]]:
    accounts = await get_active_accounts(chat_id)
    names = await _resolve_names(bot, chat_id, accounts)
    total = len(accounts)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE) if total else 1
    page = max(1, min(page, total_pages))

    if not accounts:
        text = (
            "✅ همه حساب‌ها صاف شده!\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💡 با دکمه‌ها می‌توانید لیست را تازه کنید."
        )
        if group_name:
            text += f"\n🏷 گروه: {html.escape(group_name)}"
        return text, 1, accounts, names

    start = (page - 1) * PER_PAGE
    chunk = accounts[start: start + PER_PAGE]
    total_balance = sum(int(a["point"] or 0) for a in accounts)

    lines = [
        "📒 لیست حساب‌های فعال گروه",
        "━━━━━━━━━━━━━━━━━━",
        f"📄 صفحه {page} از {total_pages}",
    ]
    if group_name:
        lines.append(f"🏷 گروه: {html.escape(group_name)}")
    lines.append("")

    for i, acc in enumerate(chunk):
        idx = start + i + 1
        uid = int(acc["telegram_user_id"])
        bal = int(acc["point"] or 0)
        name = html.escape(_account_display_name(acc, names, uid))
        if bal < 0:
            line = f"{idx}. {name} — 🔻 {abs(bal):,} واحد بدهکار"
        else:
            line = f"{idx}. {name} — {bal:,} واحد"
        if acc.get("balance_hidden"):
            line += " 🔒"
        lines.append(line)

    missing_count = count_missing_account_names(accounts, names)
    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        f"💼 مجموع تراز گروه: {total_balance:,} واحد",
        f"🔢 تعداد حساب‌های تسویه نشده: {total}",
    ])
    hint_inline = build_accounts_name_hint_inline(missing_count)
    if hint_inline:
        lines.extend(["", hint_inline])
    else:
        lines.extend([
            "",
            "💡 روی نام کاربر بزنید یا دکمه ✅ تسویه را استفاده کنید.",
        ])
    return "\n".join(lines), total_pages, accounts, names


def accounts_list_kb(
    chat_id: int,
    accounts: list[dict],
    names: dict[int, str],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows: list[list[IKB]] = []
    if accounts:
        start = (page - 1) * PER_PAGE
        chunk = accounts[start: start + PER_PAGE]
        for i, acc in enumerate(chunk):
            idx = start + i + 1
            uid = int(acc["telegram_user_id"])
            bal = int(acc["point"] or 0)
            name = _label_name(_account_display_name(acc, names, uid))
            bal_s = f"-{abs(bal):,}" if bal < 0 else f"{bal:,}"
            rows.append([
                IKB(text=f"{idx}. {name} · {bal_s}", callback_data=_cb(chat_id, "u", idx)),
                IKB(text="✅ تسویه", callback_data=_cb(chat_id, "s", idx)),
            ])

    rows.append([
        IKB(text="🔄 تازه‌سازی", callback_data=_cb(chat_id, "l", page)),
        IKB(text="🧾 تسویه همه", callback_data=_cb(chat_id, "a")),
    ])

    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(IKB(text="◀️ قبلی", callback_data=_cb(chat_id, "l", page - 1)))
        nav.append(IKB(text=f"📄 {page}/{total_pages}", callback_data=_cb(chat_id, "l", page)))
        if page < total_pages:
            nav.append(IKB(text="بعدی ▶️", callback_data=_cb(chat_id, "l", page + 1)))
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _user_menu_kb(chat_id: int, idx: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="✅ تسویه", callback_data=_cb(chat_id, "s", idx))],
        [
            IKB(text="💳 موجودی", callback_data=_cb(chat_id, "bal", idx)),
            IKB(text="📑 گزارش", callback_data=_cb(chat_id, "tx", idx)),
        ],
        [IKB(text="◀️ بازگشت به لیست", callback_data=_cb(chat_id, "l", page))],
    ])


def _settle_options_kb(chat_id: int, idx: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="✅ تسویه کامل", callback_data=_cb(chat_id, "sok", idx))],
        [IKB(text="✏️ تسویه دلخواه", callback_data=_cb(chat_id, "sp", idx))],
        [IKB(text="❌ لغو تسویه", callback_data=_cb(chat_id, "sc", idx))],
        [IKB(text="◀️ بازگشت به لیست", callback_data=_cb(chat_id, "l", page))],
    ])


def _confirm_all_kb(chat_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            IKB(text="✅ بله، همه تسویه شوند", callback_data=_cb(chat_id, "aok")),
            IKB(text="❌ انصراف", callback_data=_cb(chat_id, "l", page)),
        ],
    ])


def _cancel_amount_kb(chat_id: int, idx: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="❌ لغو تسویه", callback_data=_cb(chat_id, "sc", idx))],
        [IKB(text="◀️ بازگشت به لیست", callback_data=_cb(chat_id, "l", page))],
    ])


async def build_accounts_pm_payload(
    chat_id: int,
    bot: Bot,
    page: int = 1,
    *,
    group_name: str | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    text, total_pages, accounts, names = await build_accounts_text(
        chat_id, bot, page, group_name=group_name,
    )
    kb = accounts_list_kb(chat_id, accounts, names, page, total_pages)
    return text, kb


async def deliver_accounts_pm(
    bot: Bot,
    chat_id: int,
    admin_id: int,
    group_msg_id: int,
    *,
    group_name: str | None = None,
) -> bool:
    from bot.helpers import deliver_private_or_warn, safe_send

    text, kb = await build_accounts_pm_payload(
        chat_id, bot, 1, group_name=group_name,
    )
    try:
        await bot.send_message(
            admin_id, text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        await safe_send(
            bot, chat_id,
            "📲 لیست حساب‌ها در پیوی ارسال شد.",
            reply_to=group_msg_id,
        )
        return True
    except Exception as exc:
        print(f"deliver_accounts_pm error ({admin_id}): {exc}")
        return await deliver_private_or_warn(
            bot, chat_id, admin_id, group_msg_id, text, reply_markup=kb,
        )


def _page_for_idx(idx: int) -> int:
    return max(1, (idx - 1) // PER_PAGE + 1)


async def _edit_or_send(call: CallbackQuery, bot: Bot, text: str, kb: InlineKeyboardMarkup):
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await send_private(bot, call.from_user.id, text, reply_markup=kb)


async def handle_settle_amount_message(message: Message, bot: Bot) -> bool:
    """اگر ادمین در پیوی مبلغ تسویه دلخواه می‌فرستد."""
    user_id = message.from_user.id
    wait = get_amount_wait(user_id)
    if not wait:
        return False

    raw = (message.text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    chat_id = wait["chat_id"]
    idx = wait["idx"]
    page = wait["page"]
    group_name = wait.get("group_name")

    if raw in ("لغو", "انصراف", "cancel"):
        pop_amount_wait(user_id)
        await message.answer(
            "❌ تسویه لغو شد.",
            reply_markup=_settle_options_kb(chat_id, idx, page),
        )
        return True

    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(
            "⚠️ مبلغ نامعتبر است.\nیک عدد مثبت بفرستید یا «لغو» را بزنید.",
            reply_markup=_cancel_amount_kb(chat_id, idx, page),
        )
        return True

    amount = int(raw)
    pop_amount_wait(user_id)
    target_id = wait["target_id"]
    admin_name = _admin_display_name(message)

    new_balance = await decrease_wallet(
        chat_id, target_id, amount,
        admin_id=user_id,
        description="تسویه دلخواه از پنل حساب‌ها",
    )
    await _notify_user_settled(
        bot,
        target_id=target_id,
        admin_name=admin_name,
        amount=amount,
        group_name=group_name,
        full=False,
        new_balance=new_balance,
    )

    text, kb = await build_accounts_pm_payload(chat_id, bot, page, group_name=group_name)
    try:
        member = await bot.get_chat_member(chat_id, target_id)
        name = html.escape(member.user.full_name or member.user.first_name or "کاربر")
    except Exception:
        name = "کاربر"
    await message.answer(
        f"✅ تسویه دلخواه برای {name}: {amount:,} واحد\n"
        f"📊 موجودی جدید: {new_balance:,}\n"
        f"🛡 مدیر: {html.escape(admin_name)}\n\n" + text,
        reply_markup=kb,
        parse_mode="HTML",
    )
    return True


async def handle_accounts_callback(call: CallbackQuery, bot: Bot) -> bool:
    parts = (call.data or "").split(":")
    if len(parts) < 3 or parts[0] != "acc":
        return False
    try:
        chat_id = int(parts[1])
    except ValueError:
        await call.answer("گروه نامعتبر", show_alert=True)
        return True

    user_id = call.from_user.id
    if not is_admin(chat_id, user_id) and not is_owner(chat_id, user_id):
        await call.answer(
            "⛔️ دسترسی ندارید.\nاین دستور فقط برای ادمین‌های گروه فعال است.",
            show_alert=True,
        )
        return True

    action = parts[2]
    arg = parts[3] if len(parts) > 3 else None

    if action != "sp":
        pop_amount_wait(user_id)

    group_name = None
    try:
        chat = await bot.get_chat(chat_id)
        group_name = chat.title
    except Exception:
        pass

    accounts = await get_active_accounts(chat_id)
    names = await _resolve_names(bot, chat_id, accounts)
    admin_name = _admin_display_name(call)

    def _get_acc(idx: int):
        if idx < 1 or idx > len(accounts):
            return None
        return accounts[idx - 1]

    if action == "l":
        page = max(1, int(arg or 1))
        text, kb = await build_accounts_pm_payload(
            chat_id, bot, page, group_name=group_name,
        )
        await _edit_or_send(call, bot, text, kb)
        await call.answer()
        return True

    if action == "a":
        text = (
            "⚠️ تأیید تسویه همه حساب‌ها\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🔢 تعداد حساب‌ها: {len(accounts)}\n"
            "این عملیات موجودی همه کاربران غیرصفر را صفر می‌کند."
        )
        await _edit_or_send(call, bot, text, _confirm_all_kb(chat_id, 1))
        await call.answer()
        return True

    if action == "aok":
        results = await clear_all_wallets(chat_id, admin_id=user_id)
        for uid, cleared in results:
            await _notify_user_settled(
                bot,
                target_id=int(uid),
                admin_name=admin_name,
                amount=abs(int(cleared)),
                group_name=group_name,
                full=True,
            )
        text, kb = await build_accounts_pm_payload(
            chat_id, bot, 1, group_name=group_name,
        )
        note = (
            f"✅ {len(results)} حساب تسویه شد.\n🛡 مدیر: {html.escape(admin_name)}\n\n"
            if results else "✅ حساب فعالی برای تسویه نبود.\n\n"
        )
        await _edit_or_send(call, bot, note + text, kb)
        await call.answer("تسویه همه انجام شد")
        return True

    if action not in ("u", "s", "sok", "sp", "sc", "bal", "tx") or arg is None:
        await call.answer("نامعتبر", show_alert=True)
        return True

    try:
        idx = int(arg)
    except ValueError:
        await call.answer("نامعتبر", show_alert=True)
        return True

    acc = _get_acc(idx)
    page = _page_for_idx(idx)

    if action == "sc":
        if acc:
            uid = int(acc["telegram_user_id"])
            bal = int(acc["point"] or 0)
            name = html.escape(names.get(uid, "کاربر"))
            text = (
                f"❌ تسویه لغو شد.\n\n"
                f"👤 کاربر: {name}\n"
                f"🆔 <code>{uid}</code>\n"
                f"📊 موجودی: {bal:,} واحد"
            )
            await _edit_or_send(call, bot, text, _user_menu_kb(chat_id, idx, page))
        else:
            text, kb = await build_accounts_pm_payload(chat_id, bot, 1, group_name=group_name)
            await _edit_or_send(call, bot, "❌ تسویه لغو شد.\n\n" + text, kb)
        await call.answer("لغو شد")
        return True

    if not acc:
        text, kb = await build_accounts_pm_payload(chat_id, bot, 1, group_name=group_name)
        await _edit_or_send(call, bot, "⚠️ این حساب دیگر در لیست نیست.\n\n" + text, kb)
        await call.answer()
        return True

    uid = int(acc["telegram_user_id"])
    bal = int(acc["point"] or 0)
    name = html.escape(names.get(uid, "کاربر"))

    if action == "u":
        text = (
            f"👤 کاربر: {name}\n"
            f"🆔 <code>{uid}</code>\n"
            f"📊 موجودی: {bal:,} واحد\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "یک عملیات را انتخاب کنید:"
        )
        await _edit_or_send(call, bot, text, _user_menu_kb(chat_id, idx, page))
        await call.answer()
        return True

    if action == "s":
        text = (
            f"🧾 تسویه حساب\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 {name}\n"
            f"📊 موجودی فعلی: {bal:,} واحد\n\n"
            f"نوع تسویه را انتخاب کنید:"
        )
        await _edit_or_send(call, bot, text, _settle_options_kb(chat_id, idx, page))
        await call.answer()
        return True

    if action == "sp":
        set_amount_wait(user_id, {
            "chat_id": chat_id,
            "target_id": uid,
            "idx": idx,
            "page": page,
            "group_name": group_name,
        })
        text = (
            f"✏️ تسویه دلخواه\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 {name}\n"
            f"📊 موجودی فعلی: {bal:,} واحد\n\n"
            f"مبلغ مورد نظر را به عدد بفرستید.\n"
            f"برای انصراف: «لغو»"
        )
        await _edit_or_send(call, bot, text, _cancel_amount_kb(chat_id, idx, page))
        await call.answer()
        return True

    if action == "sok":
        cleared = await clear_wallet(chat_id, uid, admin_id=user_id)
        await _notify_user_settled(
            bot,
            target_id=uid,
            admin_name=admin_name,
            amount=abs(cleared),
            group_name=group_name,
            full=True,
        )
        text, kb = await build_accounts_pm_payload(
            chat_id, bot, page, group_name=group_name,
        )
        note = (
            f"✅ تسویه کامل {name} انجام شد ({cleared:,} واحد).\n"
            f"🛡 مدیر: {html.escape(admin_name)}\n\n"
        )
        await _edit_or_send(call, bot, note + text, kb)
        await call.answer("تسویه شد")
        return True

    if action == "bal":
        live = await get_balance(chat_id, uid)
        j_time = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
        if live < 0:
            bal_text = f"🔻 {abs(live):,} واحد بدهکار"
        else:
            bal_text = f"{live:,} واحد اعتباری"
        text = (
            "💳 وضعیت موجودی حساب\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 کاربر: {name}\n"
            f"🆔 <code>{uid}</code>\n"
            f"📊 موجودی فعلی: {bal_text}\n"
            f"🕒 زمان استعلام: {j_time}\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        if group_name:
            text += f"\n🏷 گروه: {html.escape(group_name)}"
        await _edit_or_send(call, bot, text, _user_menu_kb(chat_id, idx, page))
        await call.answer()
        return True

    if action == "tx":
        text, total_pages = await build_tx_report_text(
            chat_id, bot, uid, 1, group_name=group_name,
        )
        kb = tx_report_kb(chat_id, uid, 1, total_pages)
        rows = list(kb.inline_keyboard)
        rows.append([IKB(text="◀️ بازگشت", callback_data=_cb(chat_id, "u", idx))])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await _edit_or_send(call, bot, text, kb)
        await call.answer()
        return True

    return True
