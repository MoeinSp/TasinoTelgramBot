"""پنل مالی پیوی — با ارسال شناسه گروه."""
from __future__ import annotations

import re

from aiogram import Bot
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup, Message
from asgiref.sync import sync_to_async

from bot.cache_manager import is_admin, is_owner
from bot.panel_ui import (
    SEP, panel_header, toggle_label,
    can_see_sensitive_finance, can_see_fee, is_creator,
)

_sessions: dict[int, int] = {}  # user_id → group chat_id
_await_group: set[int] = set()


def clear_finance_session(user_id: int) -> None:
    _sessions.pop(int(user_id), None)
    _await_group.discard(int(user_id))


def get_finance_group(user_id: int) -> int | None:
    return _sessions.get(int(user_id))


def set_finance_group(user_id: int, group_chat_id: int) -> None:
    _sessions[int(user_id)] = int(group_chat_id)


def extract_group_chat_id(text: str) -> int | None:
    if not text:
        return None
    t = text.strip().strip("`\"'")
    prefixes = (
        "شناسه گروه", "شناسه گپ", "شناسه", "گروه", "group", "chat_id", "chat id", "id",
    )
    low = t.lower()
    for prefix in prefixes:
        if low.startswith(prefix.lower()):
            t = t[len(prefix):].strip(" :-`\"'")
            break
    t = t.replace(" ", "")
    if not re.fullmatch(r"-?\d{6,}", t):
        return None
    return int(t)


@sync_to_async
def _resolve_group(group_chat_id: int, user_id: int) -> dict | None:
    from account.models import TelegramGroup, TelegramGroupMember

    gid = int(group_chat_id)
    uid = int(user_id)
    group = TelegramGroup.objects.filter(telegram_chat_id=gid).first()
    if not group:
        return None
    owner = is_owner(gid, uid) or is_creator(uid)
    admin = is_admin(gid, uid) or owner
    member = TelegramGroupMember.objects.filter(
        telegram_chat_id=gid, telegram_user_id=uid,
    ).first()
    balance = int(member.point or 0) if member else 0
    pv_admin_finance = bool(getattr(group, "pv_admin_finance_enabled", False))
    fee_hidden = bool(getattr(group, "fee_hidden", False))
    see_sens = can_see_sensitive_finance(uid, gid, is_owner_flag=owner)
    see_fee = can_see_fee(uid, gid, is_owner_flag=owner, fee_hidden=fee_hidden)
    can_manage_finance = bool(owner) or (bool(admin) and not owner and pv_admin_finance and see_sens)
    return {
        "group_id": gid,
        "group_name": (group.name or str(gid)).strip(),
        "balance": balance,
        "is_owner": bool(owner),
        "is_admin": bool(admin),
        "can_manage_finance": can_manage_finance,
        "pv_admin_finance_enabled": pv_admin_finance,
        "fee_hidden": fee_hidden,
        "can_see_sensitive": see_sens,
        "can_see_fee": see_fee,
    }


@sync_to_async
def _toggle_pv_admin_finance(group_chat_id: int) -> bool | None:
    from account.models import TelegramGroup

    group = TelegramGroup.objects.filter(telegram_chat_id=int(group_chat_id)).first()
    if not group:
        return None
    group.pv_admin_finance_enabled = not bool(group.pv_admin_finance_enabled)
    group.save(update_fields=["pv_admin_finance_enabled"])
    return group.pv_admin_finance_enabled


@sync_to_async
def _user_groups_by_activity(user_id: int) -> list[tuple[int, str]]:
    """گروه‌های کاربر مرتب‌شده بر اساس آخرین تراکنش / عضویت."""
    from django.db.models import Max
    from account.models import TelegramGroup, TelegramGroupMember, WalletTransaction

    uid = int(user_id)
    member_ids = list(
        TelegramGroupMember.objects.filter(telegram_user_id=uid)
        .values_list("telegram_chat_id", flat=True)[:40]
    )
    if not member_ids:
        return []

    last_tx = {
        row["telegram_chat_id"]: row["last_at"]
        for row in WalletTransaction.objects.filter(
            telegram_user_id=uid, telegram_chat_id__in=member_ids,
        ).values("telegram_chat_id").annotate(last_at=Max("created_at"))
    }
    names = {
        g.telegram_chat_id: (g.name or str(g.telegram_chat_id))
        for g in TelegramGroup.objects.filter(telegram_chat_id__in=member_ids)
    }
    ranked = sorted(
        member_ids,
        key=lambda cid: (cid in last_tx, last_tx.get(cid)),
        reverse=True,
    )
    return [(cid, names.get(cid, str(cid))) for cid in ranked[:20]]


@sync_to_async
def _user_owned_groups(user_id: int) -> list[tuple[int, str]]:
    from account.models import TelegramGroup, TelegramGroupMember

    uid = int(user_id)
    ids = list(
        TelegramGroupMember.objects.filter(telegram_user_id=uid, is_owner=True)
        .values_list("telegram_chat_id", flat=True)[:20]
    )
    if not ids:
        return []
    names = {
        g.telegram_chat_id: (g.name or str(g.telegram_chat_id))
        for g in TelegramGroup.objects.filter(telegram_chat_id__in=ids)
    }
    return [(cid, names.get(cid, str(cid))) for cid in ids]


def kb_finance_panel(
    *,
    is_admin: bool = False,
    is_owner: bool = False,
    can_manage_finance: bool = False,
    pv_admin_finance_enabled: bool = False,
    can_see_sensitive: bool = True,
    can_see_fee: bool = True,
) -> InlineKeyboardMarkup:
    rows = [
        [
            IKB(text="درخواست افزایش", callback_data="pf:i"),
            IKB(text="درخواست تسویه", callback_data="pf:w"),
        ],
        [
            IKB(text="گزارش تراکنش", callback_data="pf:t"),
            IKB(text="بروزرسانی", callback_data="pf:h"),
        ],
        [IKB(text="تغییر گروه", callback_data="pf:g")],
    ]
    if can_manage_finance and can_see_sensitive:
        rows.append([
            IKB(text="حساب ادمین‌ها", callback_data="pf:oa"),
            IKB(text="فعالیت‌ها", callback_data="pf:oy"),
        ])
        rows.append([IKB(text="حساب اعضا", callback_data="pf:oc")])
    if can_manage_finance and can_see_fee:
        rows.append([IKB(text="حق واسطه", callback_data="pf:of")])
    if is_owner or is_admin:
        rows.append([IKB(text="چالش‌ها", callback_data="pf:ch")])
    if is_owner:
        rows.append([IKB(
            text=toggle_label(pv_admin_finance_enabled, "دسترسی مالی ادمین"),
            callback_data="pf:ad",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_group_pick(groups: list[tuple[int, str]]) -> InlineKeyboardMarkup | None:
    if not groups:
        return None
    rows = []
    for gid, name in groups[:8]:
        label = (name[:28] + "…") if len(name) > 29 else name
        rows.append([IKB(text=f"📍 {label}", callback_data=f"pf:sg:{gid}")])
    rows.append([IKB(text="شناسه گروه دیگر", callback_data="pf:g")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_action_group_pick(groups: list[tuple[int, str]], *, kind: str) -> InlineKeyboardMarkup | None:
    if not groups:
        return None
    prefix = "pf:incsg:" if kind == "inc" else "pf:wdsg:"
    rows = []
    for gid, name in groups[:8]:
        label = (name[:28] + "…") if len(name) > 29 else name
        rows.append([IKB(text=f"📍 {label}", callback_data=f"{prefix}{gid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _panel_text(ctx: dict) -> str:
    role = "مالک" if ctx.get("is_owner") else ("ادمین" if ctx.get("is_admin") else "عضو")
    lines = [
        panel_header("💰", "پنل مالی"),
        f"گروه: <b>{_esc(ctx['group_name'])}</b>",
        f"شناسه: <code>{ctx['group_id']}</code>",
        f"نقش: <b>{role}</b>",
        f"موجودی: <b>{ctx['balance']:,}</b> واحد",
        SEP,
    ]
    if ctx.get("is_owner"):
        status = "روشن" if ctx.get("pv_admin_finance_enabled") else "خاموش"
        lines.extend([
            "",
            "منوی مالک در دکمه‌ها:",
            "• حساب ادمین‌ها · حق واسطه · فعالیت‌ها · حساب اعضا · چالش‌ها",
            f"• دسترسی مالی ادمین: <b>{status}</b>",
        ])
    elif ctx.get("can_manage_finance"):
        lines.extend(["", "دسترسی مالی ادمین فعال است."])
    elif ctx.get("is_admin"):
        lines.extend(["", "چالش‌ها برای شما در دسترس است."])
    lines.extend(["", "از دکمه‌های زیر استفاده کنید."])
    return "\n".join(lines)


def _esc(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _panel_kb(ctx: dict) -> InlineKeyboardMarkup:
    return kb_finance_panel(
        is_admin=bool(ctx.get("is_admin")),
        is_owner=bool(ctx.get("is_owner")),
        can_manage_finance=bool(ctx.get("can_manage_finance")),
        pv_admin_finance_enabled=bool(ctx.get("pv_admin_finance_enabled")),
        can_see_sensitive=bool(ctx.get("can_see_sensitive", True)),
        can_see_fee=bool(ctx.get("can_see_fee", True)),
    )


async def open_finance_panel(bot: Bot, user_id: int, group_chat_id: int) -> bool:
    ctx = await _resolve_group(group_chat_id, user_id)
    if not ctx:
        await bot.send_message(
            user_id,
            "❌ گروه پیدا نشد.\n\n"
            "شناسه را از گروه با دستور <code>شناسه گپ</code> بگیرید "
            "و مطمئن شوید ربات در آن گروه نصب شده است.",
            parse_mode="HTML",
        )
        return False

    _sessions[int(user_id)] = int(ctx["group_id"])
    _await_group.discard(int(user_id))
    await bot.send_message(
        user_id,
        _panel_text(ctx),
        parse_mode="HTML",
        reply_markup=_panel_kb(ctx),
        disable_web_page_preview=True,
    )
    return True


async def prompt_group_id(bot: Bot, user_id: int) -> None:
    _await_group.add(int(user_id))
    groups = await _user_owned_groups(user_id)
    kb = kb_group_pick(groups)
    text = (
        panel_header("💰", "پنل مالی")
        + "شناسه گروه را ارسال کنید یا از لیست زیر انتخاب کنید.\n\n"
        "در گروه بنویسید: <code>شناسه گپ</code>"
    )
    await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)


async def prompt_member_request_group(bot: Bot, user_id: int, kind: str) -> None:
    groups = await _user_groups_by_activity(user_id)
    kb = kb_action_group_pick(groups, kind=kind)
    title = "درخواست افزایش" if kind == "inc" else "درخواست تسویه"
    text = (
        panel_header("💰", title)
        + "گروه مورد نظر را انتخاب کنید.\n"
        "(مرتب‌شده بر اساس آخرین فعالیت)"
    )
    if kb:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
    else:
        await bot.send_message(
            user_id,
            text + "\n\n❌ گروهی پیدا نشد.\nابتدا در یک گروه با ربات فعالیت کنید.",
            parse_mode="HTML",
        )


async def try_handle_member_request_text(bot: Bot, user_id: int, text: str) -> bool:
    from bot.hidden_increase import MEMBER_INCREASE_TEXTS, MEMBER_SETTLE_TEXTS

    t = (text or "").strip()
    if t in MEMBER_INCREASE_TEXTS:
        await prompt_member_request_group(bot, user_id, "inc")
        return True
    if t in MEMBER_SETTLE_TEXTS:
        await prompt_member_request_group(bot, user_id, "wd")
        return True
    return False


async def try_handle_group_id_text(bot: Bot, user_id: int, text: str) -> bool:
    gid = extract_group_chat_id(text)
    if gid is None:
        return False
    return await open_finance_panel(bot, user_id, gid)


async def handle_finance_panel_callback(call, bot: Bot) -> bool:
    data = call.data or ""
    if not data.startswith("pf:"):
        return False

    uid = call.from_user.id
    await call.answer()

    if data.startswith("pf:sg:"):
        gid = int(data.split(":")[2])
        await open_finance_panel(bot, uid, gid)
        return True

    if data.startswith("pf:incsg:"):
        gid = int(data.split(":")[2])
        from bot.hidden_increase import start_increase_request_flow
        from bot.finance_ban import is_finance_banned, FINANCE_BAN_USER_TEXT
        _sessions[int(uid)] = int(gid)
        if await is_finance_banned(gid, uid):
            await bot.send_message(uid, FINANCE_BAN_USER_TEXT)
            return True
        ok = await start_increase_request_flow(bot, uid, gid)
        if ok:
            await bot.send_message(
                uid,
                "📩 مراحل درخواست افزایش در همین پیوی ادامه دارد.\n"
                "مبلغ را بفرستید، سپس <b>عکس رسید</b> واریز را ارسال کنید.",
                parse_mode="HTML",
            )
        else:
            await bot.send_message(uid, "⚠️ خطا در شروع درخواست. دوباره تلاش کنید.")
        return True

    if data.startswith("pf:wdsg:"):
        gid = int(data.split(":")[2])
        from bot.withdrawal_flow import (
            begin as begin_withdrawal, BEGIN_NO_PV, BEGIN_PENDING, BEGIN_BANNED,
        )
        _sessions[int(uid)] = int(gid)
        result = await begin_withdrawal(bot, gid, uid)
        if result == BEGIN_NO_PV:
            await bot.send_message(uid, "⚠️ خطا در شروع درخواست تسویه.")
        elif result == BEGIN_PENDING:
            pass
        elif result == BEGIN_BANNED:
            pass
        return True

    if data == "pf:g":
        await prompt_group_id(bot, uid)
        return True

    group_id = _sessions.get(uid)
    if not group_id:
        await bot.send_message(uid, "⚠️ ابتدا شناسه گروه را ارسال کنید.")
        return True

    ctx = await _resolve_group(group_id, uid)
    if not ctx:
        _sessions.pop(uid, None)
        await bot.send_message(uid, "❌ نشست منقضی شد — شناسه گروه را دوباره بفرستید.")
        return True

    if data == "pf:h":
        await bot.send_message(
            uid, _panel_text(ctx), parse_mode="HTML", reply_markup=_panel_kb(ctx),
        )
        return True

    if data == "pf:ad":
        if not ctx.get("is_owner"):
            await bot.send_message(uid, "❌ فقط مالک می‌تواند دسترسی ادمین را تغییر دهد.")
            return True
        new_state = await _toggle_pv_admin_finance(group_id)
        if new_state is None:
            await bot.send_message(uid, "❌ گروه پیدا نشد.")
            return True
        ctx = await _resolve_group(group_id, uid)
        label = "روشن شد" if new_state else "خاموش شد"
        await bot.send_message(
            uid,
            f"✅ دسترسی ادمین‌ها به پنل مالی {label}.",
            parse_mode="HTML",
            reply_markup=_panel_kb(ctx),
        )
        return True

    if data == "pf:ch":
        if not (ctx.get("is_owner") or ctx.get("is_admin")):
            await bot.send_message(uid, "❌ پنل چالش فقط برای مالک و ادمین گروه است.")
            return True
        from bot.challenge_panel import open_challenge_home
        await open_challenge_home(bot, uid, group_id)
        return True

    if data == "pf:i":
        from bot.hidden_increase import start_increase_request_flow
        from bot.finance_ban import is_finance_banned, FINANCE_BAN_USER_TEXT
        if await is_finance_banned(group_id, uid):
            await bot.send_message(uid, FINANCE_BAN_USER_TEXT)
            return True
        ok = await start_increase_request_flow(bot, uid, group_id)
        if ok:
            await bot.send_message(
                uid,
                "📩 مراحل درخواست افزایش در همین پیوی ادامه دارد.\n"
                "مبلغ را بفرستید، سپس <b>عکس رسید</b> واریز را ارسال کنید.",
                parse_mode="HTML",
            )
        else:
            await bot.send_message(uid, "⚠️ خطا در شروع درخواست. دوباره تلاش کنید.")
        return True

    if data == "pf:w":
        from bot.withdrawal_flow import (
            begin as begin_withdrawal, BEGIN_NO_PV, BEGIN_PENDING, BEGIN_BANNED,
        )

        result = await begin_withdrawal(bot, group_id, uid)
        if result == BEGIN_NO_PV:
            await bot.send_message(uid, "⚠️ خطا در شروع درخواست تسویه.")
        elif result in (BEGIN_PENDING, BEGIN_BANNED):
            pass
        return True

    if data == "pf:t":
        from bot.tx_reports import build_tx_report_text, tx_report_kb
        text, total_pages = await build_tx_report_text(
            group_id, bot, uid, 1, group_name=ctx["group_name"],
        )
        await bot.send_message(
            uid, text, parse_mode="HTML",
            reply_markup=tx_report_kb(group_id, uid, 1, total_pages),
            disable_web_page_preview=True,
        )
        return True

    if data in ("pf:oa", "pf:of", "pf:oy", "pf:oc"):
        if data == "pf:of" and not ctx.get("can_see_fee"):
            await bot.send_message(uid, "❌ حق واسطه مخفی است.")
            return True
        if data in ("pf:oa", "pf:oy", "pf:oc") and not (
            ctx.get("can_manage_finance") and ctx.get("can_see_sensitive")
        ):
            await bot.send_message(uid, "❌ این بخش فقط برای مالک یا ادمینِ مجاز است.")
            return True
        if data == "pf:of" and not ctx.get("can_manage_finance"):
            await bot.send_message(uid, "❌ این بخش فقط برای مالک یا ادمینِ مجاز است.")
            return True

        if data == "pf:oa":
            from bot.admin_accounting import (
                remember_context, report as admin_report, render, report_keyboard,
            )
            rows = await admin_report(group_id, "0")
            remember_context(group_id, uid)
            await bot.send_message(
                uid, render(rows, "0"), parse_mode="HTML",
                reply_markup=report_keyboard(group_id, rows, "0"),
                disable_web_page_preview=True,
            )
            return True

        if data == "pf:oy":
            from bot.admin_accounting import (
                list_activity_sessions, list_activity_day_keys, remember_context,
                render_activities_list, activities_keyboard,
            )
            sessions = await list_activity_sessions(group_id)
            day_keys = await list_activity_day_keys(group_id)
            remember_context(group_id, uid)
            await bot.send_message(
                uid, render_activities_list(sessions, day_keys), parse_mode="HTML",
                reply_markup=activities_keyboard(group_id, sessions, day_keys=day_keys),
                disable_web_page_preview=True,
            )
            return True

        if data == "pf:of":
            from bot.fee_reports import build_fee_text_by_mode, fee_report_kb
            text = await build_fee_text_by_mode(group_id, bot, "0")
            if not text:
                await bot.send_message(uid, "⚠️ گزارشی برای نمایش وجود ندارد.")
                return True
            await bot.send_message(
                uid, text, parse_mode="HTML",
                reply_markup=fee_report_kb(group_id),
                disable_web_page_preview=True,
            )
            return True

        if data == "pf:oc":
            from bot.accounts_panel import build_accounts_pm_payload
            text, kb = await build_accounts_pm_payload(
                group_id, bot, 1, group_name=ctx["group_name"],
            )
            await bot.send_message(
                uid, text, parse_mode="HTML", reply_markup=kb,
                disable_web_page_preview=True,
            )
            return True

    return False


async def handle_group_id_message(message: Message, bot: Bot) -> bool:
    """اگر متن شناسه گروه باشد پنل را باز می‌کند. True = پیام مصرف شد."""
    text = (message.text or "").strip()
    if not text:
        return False
    return await try_handle_group_id_text(bot, message.from_user.id, text)
