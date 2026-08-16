"""گزارش تراکنش‌ها — متن و کیبورد اینلاین (پیوی تلگرام)."""
from __future__ import annotations

import html
import jdatetime
from aiogram import Bot
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup

from bot.finance import get_balance, get_transactions, get_transactions_count
from bot.helpers import deliver_private_or_warn, send_private, user_mention_id

PER_PAGE = 5

_REPORT_PM_SUFFIXES = frozenset({"پیوی", "پیو", "در پیوی"})

import re

_GAME_ID_RE = re.compile(r"(?:·\s*)?آیدی بازی\s+(\d+)")
_OPPONENT_RE = re.compile(r"حریف:\s*([^·\n]+)")
_INVITE_RE = re.compile(r"دعوت:([^\s·\n]+)")


def _parse_game_id(desc: str) -> int | None:
    m = _GAME_ID_RE.search(desc or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _parse_opponent_from_desc(desc: str) -> str:
    m = _OPPONENT_RE.search(desc or "")
    return (m.group(1).strip() if m else "") or ""


def _format_tx_description(desc: str, *, escape_html: bool = False) -> list[str]:
    """جدا کردن آیدی بازی از توضیح برای نمایش واضح در گزارش."""
    text = (desc or "").strip()
    if not text:
        return []
    m = _GAME_ID_RE.search(text)
    lines = []
    if m:
        lines.append(f"   🆔 آیدی بازی: {m.group(1)}")
        text = (_GAME_ID_RE.sub("", text)).replace("·", "").strip(" -·")
    text = _OPPONENT_RE.sub("", text)
    text = _INVITE_RE.sub("", text)
    text = text.replace("·", "").strip(" -·")
    if text:
        pretty = text
        if "شرکت در مسابقه تاس" in text:
            pretty = "ورودی مسابقه"
        elif "برنده مسابقه تاس" in text:
            pretty = "برد مسابقه"
        elif "بازگشت ورودی بازی پیوی (لغو)" in text:
            pretty = "بازگشت ورودی — لغو بازی"
        elif "بازگشت ورودی بازی پیوی (تساوی)" in text:
            pretty = "بازگشت ورودی — تساوی"
        elif "بازگشت ورودی" in text:
            pretty = "بازگشت ورودی مسابقه"
        show = html.escape(pretty) if escape_html else pretty
        lines.append(f"   📝 توضیح: {show}")
    return lines


def parse_report_command(text: str) -> tuple[str, int] | None:
    """('pm', page) | None — فقط «گزارش پیوی»."""
    if not text:
        return None
    parts = text.strip().split()
    if not parts or parts[0] != "گزارش":
        return None
    if len(parts) >= 2 and parts[1] == "حق":
        return None
    suffix_parts = parts[1:]
    if not suffix_parts or suffix_parts[0] not in _REPORT_PM_SUFFIXES:
        return None
    suffix_parts = suffix_parts[1:]
    page = 1
    if suffix_parts and suffix_parts[0].isdigit():
        page = max(1, int(suffix_parts[0]))
    return ("pm", page)


def _tx_label(tx_type: str) -> tuple[str, str]:
    labels = {
        "admin_increase": ("افزایش موجودی", "➕"),
        "admin_decrease": ("کاهش موجودی", "➖"),
        "admin_clear": ("تسویه حساب", "🧾"),
        "bet": ("کسر ورودی مسابقه", "❌"),
        "win": ("برد مسابقه", "🏆"),
        "transfer_in": ("دریافت انتقال", "📥"),
        "transfer_out": ("ارسال انتقال", "📤"),
    }
    return labels.get(tx_type, ("تراکنش", "🔹"))


from asgiref.sync import sync_to_async


@sync_to_async
def _game_report_context(chat_id, target_id, game_ids: list[int], invite_ids: list[str] | None = None) -> dict:
    from account.models import WalletTransaction

    cid = int(chat_id)
    uid = int(target_id)
    won: set[int] = set()
    refunded: set[int] = set()
    refund_kind: dict[int, str] = {}
    refunded_invites: set[str] = set()
    invite_kind: dict[str, str] = {}
    peer_ids: dict[int, list[int]] = {}
    unique_ids = sorted({int(g) for g in game_ids if g})
    for gid in unique_ids:
        needle = f"آیدی بازی {gid}"
        rows = list(
            WalletTransaction.objects.filter(
                telegram_chat_id=cid, description__contains=needle,
            ).values("telegram_user_id", "type", "description")[:120]
        )
        peers: list[int] = []
        for r in rows:
            sid = int(r["telegram_user_id"])
            desc = r.get("description") or ""
            ttype = r.get("type") or ""
            if ttype == "win" and sid == uid:
                won.add(gid)
            if sid == uid and "بازگشت" in desc:
                refunded.add(gid)
                if "تساوی" in desc:
                    refund_kind[gid] = "tie"
                elif "لغو" in desc or "دعوت" in desc:
                    refund_kind[gid] = "cancel"
                else:
                    refund_kind[gid] = "refund"
            if sid != uid and sid not in peers:
                peers.append(sid)
        peer_ids[gid] = peers

    for inv in {str(i).strip() for i in (invite_ids or []) if str(i).strip()}:
        tag = f"دعوت:{inv}"
        rows = list(
            WalletTransaction.objects.filter(
                telegram_chat_id=cid, telegram_user_id=uid, description__contains=tag,
            ).values("type", "description")[:40]
        )
        for r in rows:
            desc = r.get("description") or ""
            if "بازگشت" in desc:
                refunded_invites.add(inv)
                invite_kind[inv] = "tie" if "تساوی" in desc else "cancel"
    return {
        "won": won,
        "refunded": refunded,
        "refund_kind": refund_kind,
        "refunded_invites": refunded_invites,
        "invite_kind": invite_kind,
        "peers": peer_ids,
    }


def _parse_invite_id(desc: str) -> str | None:
    m = _INVITE_RE.search(desc or "")
    return (m.group(1).strip() if m else None) or None


def _refund_kind_label(kind: str | None) -> tuple[str, str]:
    if kind == "tie":
        return "تساوی", "تساوی — ورودی برگشت داده شد"
    if kind == "cancel":
        return "لغو", "بازی لغو شد — ورودی برگشت داده شد"
    return "استرداد", "ورودی برگشت داده شد"


def _format_wallet_adjust_lines(t, *, escape_html: bool = False) -> list[str] | None:
    desc = getattr(t, "description", "") or ""
    if t.type != "admin_increase" or "بازگشت" not in desc:
        return None
    kind = "refund"
    if "تساوی" in desc:
        kind = "tie"
    elif "لغو" in desc or "دعوت" in desc:
        kind = "cancel"
    title, result = _refund_kind_label(kind)
    lines = [
        f"↩️ بازگشت ورودی ({title})",
        f"   💰 مبلغ: {t.amount:,} واحد",
        f"   📌 نتیجه: {result}",
    ]
    opp = _parse_opponent_from_desc(desc)
    if opp:
        if escape_html:
            opp = html.escape(opp)
        lines.append(f"   🥊 حریف: {opp}")
    return lines


def _format_match_tx_lines(
    t,
    *,
    won_games: set[int],
    refunded_games: set[int],
    refund_kind: dict[int, str],
    refunded_invites: set[str],
    invite_kind: dict[str, str],
    peers_by_game: dict[int, list[int]],
    name_map: dict[int, str],
    escape_html: bool = False,
) -> list[str]:
    lines: list[str] = []
    desc = getattr(t, "description", "") or ""
    gid = _parse_game_id(desc)
    invite_id = _parse_invite_id(desc)
    tx_type = t.type

    if tx_type == "bet":
        is_refunded = (gid and gid in refunded_games) or (
            invite_id and invite_id in refunded_invites
        )
        kind = None
        if gid and gid in refund_kind:
            kind = refund_kind[gid]
        elif invite_id and invite_id in invite_kind:
            kind = invite_kind[invite_id]

        if gid and gid in won_games:
            action, emoji = "کسر ورودی مسابقه", "❌"
            result = "ورودی از موجودی کسر شد"
        elif is_refunded:
            title, result = _refund_kind_label(kind)
            action, emoji = f"ورودی مسابقه ({title})", "↩️"
        elif gid:
            action, emoji = "باخت مسابقه", "❌"
            result = "باخت — ورودی به حریف رسید"
        else:
            action, emoji = "کسر ورودی مسابقه", "❌"
            result = "ورودی از موجودی کسر شد"
        lines.append(f"{emoji} {action}")
        lines.append(f"   💰 مبلغ: {t.amount:,} واحد")
        lines.append(f"   📌 نتیجه: {result}")
    elif tx_type == "win":
        lines.append("🏆 برد مسابقه")
        lines.append(f"   💰 مبلغ: {t.amount:,} واحد")
        lines.append("   📌 نتیجه: برد — جایزه به موجودی اضافه شد")
    else:
        action, emoji = _tx_label(tx_type)
        lines.append(f"{emoji} {action}")
        lines.append(f"   💰 مبلغ: {t.amount:,} واحد")

    opp = _parse_opponent_from_desc(desc)
    if not opp and gid and gid in peers_by_game:
        names = []
        for pid in peers_by_game[gid]:
            n = (name_map.get(int(pid)) or "").strip() or str(pid)
            if escape_html:
                n = html.escape(n)
            if n not in names:
                names.append(n)
        if names:
            opp = "، ".join(names[:3])
            if len(names) > 3:
                opp += f" و {len(names) - 3} نفر دیگر"
    elif opp and escape_html:
        opp = html.escape(opp)
    if opp and tx_type in ("bet", "win"):
        lines.append(f"   🥊 حریف: {opp}")
    return lines


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

    game_ids = [
        g for g in (_parse_game_id(getattr(t, "description", "") or "") for t in transactions) if g
    ]
    invite_ids = [
        i for i in (_parse_invite_id(getattr(t, "description", "") or "") for t in transactions) if i
    ]
    ctx = await _game_report_context(
        chat_id, target_id, game_ids, invite_ids=invite_ids,
    ) if (game_ids or invite_ids) else {
        "won": set(), "refunded": set(), "refund_kind": {},
        "refunded_invites": set(), "invite_kind": {}, "peers": {},
    }
    won_games = ctx.get("won") or set()
    refunded_games = ctx.get("refunded") or set()
    refund_kind = ctx.get("refund_kind") or {}
    refunded_invites = ctx.get("refunded_invites") or set()
    invite_kind = ctx.get("invite_kind") or {}
    peers_by_game = ctx.get("peers") or {}
    name_map: dict[int, str] = {}
    peer_uids = {pid for peers in peers_by_game.values() for pid in peers}
    for pid in peer_uids:
        try:
            member = await bot.get_chat_member(chat_id, pid)
            name_map[pid] = (member.user.full_name or member.user.first_name or str(pid)).strip()
        except Exception:
            name_map[pid] = str(pid)

    for t in transactions:
        j_time = jdatetime.datetime.fromgregorian(datetime=t.created_at).strftime("%Y/%m/%d - %H:%M")
        special = _format_wallet_adjust_lines(t, escape_html=True)
        if special is not None:
            lines.extend(special)
        elif t.type in ("bet", "win"):
            lines.extend(
                _format_match_tx_lines(
                    t,
                    won_games=won_games,
                    refunded_games=refunded_games,
                    refund_kind=refund_kind,
                    refunded_invites=refunded_invites,
                    invite_kind=invite_kind,
                    peers_by_game=peers_by_game,
                    name_map=name_map,
                    escape_html=True,
                )
            )
        else:
            action, emoji = _tx_label(t.type)
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
            lines.extend(_format_tx_description(t.description, escape_html=True))
        lines.append(f"   🕒 {j_time}")
        lines.append("")

    if total_pages > 1:
        lines.append("💡 از دکمه‌های زیر بین صفحات جابه‌جا شوید.")
    return "\n".join(lines), total_pages


async def send_tx_report_pm(
    bot: Bot,
    group_chat_id: int,
    sender_id: int,
    group_msg_id: int,
    target_id: int,
    page: int = 1,
    *,
    group_name: str | None = None,
) -> bool:
    from bot.helpers import deliver_private_or_warn

    if group_name is None:
        try:
            chat = await bot.get_chat(group_chat_id)
            group_name = chat.title
        except Exception:
            group_name = None

    text, total_pages = await build_tx_report_text(
        group_chat_id, bot, target_id, page, group_name=group_name,
    )
    return await deliver_private_or_warn(
        bot, group_chat_id, sender_id, group_msg_id, text,
        reply_markup=tx_report_kb(group_chat_id, target_id, page, total_pages),
    )
