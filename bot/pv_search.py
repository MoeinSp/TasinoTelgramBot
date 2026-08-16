"""جستجوی حریف پیوی از داخل ربات (محدود به اعضای همان گروه)."""
from __future__ import annotations

import asyncio
import time
import uuid

from aiogram import Bot
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton as IKB,
    InlineKeyboardMarkup,
    Message,
)
from asgiref.sync import sync_to_async
from django.db.models import Max
from django.utils import timezone

from bot.dice_game import BET_MODE_FIXED, BET_MODE_EXTRA, calc_bet_costs, is_user_involved_in_group_game
from bot.utils import normalize_numbers

ACTIVITY_HOURS = 1
CANDIDATE_LIMIT = 20
BROADCAST_LIMIT = 40
SEARCH_OFFER_TTL = 60  # مهلت قبول جستجو — هم‌تراز دعوت پیوی
_CHAT_ACT_TTL = 3600  # ثانیه — هم‌تراز با بازهٔ جستجو

# user_id → {step, group_id, bet_amount, group_name, offer_id?}
_search_wait: dict[int, dict] = {}
SEARCH_OFFERS: dict[str, dict] = {}
_offer_locks: dict[str, asyncio.Lock] = {}

SUGGESTED_BETS = (100, 200, 500, 1000, 2000)
_OFFER_SEARCH_KEY = "pv_search_offer:{}"


def mark_offer_search_after_increase(user_id: int) -> None:
    try:
        from django.core.cache import cache
        cache.set(_OFFER_SEARCH_KEY.format(int(user_id)), 1, 3600)
    except Exception:
        pass


def pop_offer_search_after_increase(user_id: int) -> bool:
    try:
        from django.core.cache import cache
        key = _OFFER_SEARCH_KEY.format(int(user_id))
        if cache.get(key):
            cache.delete(key)
            return True
    except Exception:
        pass
    return False


def search_opponent_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="🔍 جستجوی حریف", callback_data="pvs:go")],
    ])


def shortage_increase_kb(group_id: int, shortfall: int) -> InlineKeyboardMarkup:
    rows = []
    if shortfall > 0:
        rows.append([IKB(
            text=f"📈 شارژ کمبود ({shortfall:,})",
            callback_data=f"pvs:inc:{int(group_id)}:{int(shortfall)}",
        )])
    rows.append([IKB(
        text="✏️ مبلغ دلخواه",
        callback_data=f"pvs:inc:{int(group_id)}:0",
    )])
    rows.append([IKB(text="❌ لغو جستجو", callback_data="pvs:x")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_search_shortage_message(*, entry: int, playable: int, shortfall: int) -> str:
    return (
        "❌ موجودی کافی نیست\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 ورودی لازم: <b>{entry:,}</b> واحد\n"
        f"💰 موجودی قابل‌استفاده: <b>{playable:,}</b> واحد\n"
        f"🔻 کمبود: <b>{shortfall:,}</b> واحد\n\n"
        "با دکمه‌ها همان کمبود یا مبلغ دلخواه را درخواست دهید."
    )


def format_search_taken_message() -> str:
    return (
        "❌ این چالش دیگر در دسترس نیست\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "چه اتفاقی افتاد؟\n"
        "شخص دیگری زودتر درخواست را قبول کرده است "
        "(یا جستجو لغو / منقضی شده).\n\n"
        "می‌توانید دوباره حریف جستجو کنید."
    )


def _accept_search_kb(offer_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="✅ قبول چالش", callback_data=f"pvs:acc:{offer_id}")],
    ])


def _waiting_search_kb(offer_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [IKB(text="💰 تغییر مبلغ", callback_data="pvs:bet")],
        [IKB(text="❌ لغو جستجو", callback_data=f"pvs:cx:{offer_id}")],
    ])


def mark_group_chat_activity(chat_id, user_id) -> None:
    """ثبت چت اخیر در گپ برای جستجوی حریف (TTL یک ساعت)."""
    _mark_activity(f"pv_search_chat:{str(chat_id).strip()}", user_id)


def mark_pm_chat_activity(user_id) -> None:
    """ثبت پیام اخیر کاربر در پیوی ربات."""
    _mark_activity("pv_search_pm", user_id)


def _mark_activity(key: str, user_id) -> None:
    try:
        from django.core.cache import cache

        now = time.time()
        data = cache.get(key) or {}
        if not isinstance(data, dict):
            data = {}
        data[str(user_id).strip()] = now
        cutoff = now - _CHAT_ACT_TTL
        data = {u: float(t) for u, t in data.items() if float(t) >= cutoff}
        if len(data) > 400:
            data = dict(sorted(data.items(), key=lambda x: x[1], reverse=True)[:400])
        cache.set(key, data, _CHAT_ACT_TTL)
    except Exception:
        pass


def get_group_chat_activity(chat_id) -> dict[str, float]:
    return _get_activity(f"pv_search_chat:{str(chat_id).strip()}")


def get_pm_chat_activity() -> dict[str, float]:
    return _get_activity("pv_search_pm")


def _get_activity(key: str) -> dict[str, float]:
    try:
        from django.core.cache import cache

        data = cache.get(key) or {}
        if not isinstance(data, dict):
            return {}
        cutoff = time.time() - _CHAT_ACT_TTL
        return {str(u): float(t) for u, t in data.items() if float(t) >= cutoff}
    except Exception:
        return {}


def _merge_last(dst: dict, uid, ts) -> None:
    if uid is None or ts is None:
        return
    prev = dst.get(uid)
    if prev is None or ts > prev:
        dst[uid] = ts


@sync_to_async
def _list_recent_candidates(group_id: int, seeker_id: int) -> list[dict]:
    """فقط کسانی که ۱ ساعت گذشته در گپ یا پیوی ربات پیام داده‌اند (و عضو همین گپ‌اند)."""
    from datetime import datetime
    from account.models import TelegramGroupMember

    gid = int(group_id)
    seeker = int(seeker_id)
    last_by_user: dict[int, object] = {}

    def _ts_to_dt(ts):
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.get_current_timezone())
        except Exception:
            return timezone.now()

    for uid_s, ts in get_group_chat_activity(gid).items():
        try:
            uid = int(uid_s)
        except (TypeError, ValueError):
            continue
        if uid == seeker:
            continue
        _merge_last(last_by_user, uid, _ts_to_dt(ts))

    # پیام در پیوی ربات — فقط اگر عضو همین گروه باشند
    pm_uids = []
    for uid_s, ts in get_pm_chat_activity().items():
        try:
            uid = int(uid_s)
        except (TypeError, ValueError):
            continue
        if uid == seeker:
            continue
        pm_uids.append((uid, ts))

    if pm_uids:
        member_ids = set(
            TelegramGroupMember.objects.filter(
                telegram_chat_id=gid,
                telegram_user_id__in=[u for u, _ in pm_uids],
            )
            .exclude(role="banned")
            .values_list("telegram_user_id", flat=True)
        )
        for uid, ts in pm_uids:
            if int(uid) in member_ids:
                _merge_last(last_by_user, int(uid), _ts_to_dt(ts))

    if not last_by_user:
        return []

    members = {
        int(m.telegram_user_id): m
        for m in TelegramGroupMember.objects.filter(
            telegram_chat_id=gid,
            telegram_user_id__in=list(last_by_user.keys()),
        ).only("telegram_user_id", "alias", "role")
    }

    rows = []
    for uid, last_at in last_by_user.items():
        m = members.get(uid)
        if m is None:
            continue
        if (m.role or "") == "banned":
            continue
        name = (m.alias or "").strip() or f"کاربر {uid}"
        rows.append({"user_id": uid, "name": name, "last_at": last_at})

    rows.sort(key=lambda r: r["last_at"], reverse=True)
    return rows[:CANDIDATE_LIMIT]


def is_waiting_pv_search(user_id: int) -> bool:
    return int(user_id) in _search_wait


def clear_pv_search(user_id: int) -> None:
    """لغو کامل جستجو: سشن، آفر، و هر قفل search (حتی یتیم Redis)."""
    uid = int(user_id)
    sess = _search_wait.pop(uid, None)
    offer_ids: set[str] = set()
    if sess and sess.get("offer_id"):
        offer_ids.add(str(sess["offer_id"]))
    for oid, offer in list(SEARCH_OFFERS.items()):
        try:
            if int(offer.get("challenger_id") or 0) != uid:
                continue
        except (TypeError, ValueError):
            continue
        if offer.get("status") == "pending" or str(oid) in offer_ids:
            offer_ids.add(str(oid))
    for oid in offer_ids:
        _expire_offer(oid, reason="cancelled")
    try:
        from bot.pv_dice import unbind_search_offer, user_busy
        busy = user_busy(uid)
        if busy and busy[0] == "search":
            unbind_search_offer(uid)
        elif not offer_ids:
            # حتی بدون busy فعلی — برای اطمینان از پاک‌سازی Redis/حافظه
            unbind_search_offer(uid)
    except Exception:
        pass


def _expire_offer(offer_id: str, *, reason: str = "expired") -> dict | None:
    oid = str(offer_id)
    offer = SEARCH_OFFERS.get(oid)
    ch = None
    if offer:
        if offer.get("status") == "pending":
            offer["status"] = reason
        ch = offer.get("challenger_id")
    # حتی اگر آفر در حافظه نبود، قفل search متناظر را باز کن
    try:
        from bot.pv_dice import unbind_search_offer, USER_BUSY
        if ch:
            unbind_search_offer(int(ch), oid)
        else:
            for uid, busy in list(USER_BUSY.items()):
                if busy and busy[0] == "search" and str(busy[1]) == oid:
                    unbind_search_offer(int(uid), oid)
    except Exception:
        pass
    return offer


def _cancel_words(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in ("لغو", "انصراف", "cancel", "/cancel", "لغو جستجو", "لغو جستجوی حریف", "لغو پیوی"):
        return True
    # «لغو پیوی» / «لغو جستجو» با فاصلهٔ اضافه
    compact = "".join(t.split())
    return compact in ("لغوپیوی", "لغوجستجو", "لغوجستجویحریف")


async def try_cancel_pv_search_command(bot, user_id: int, *, message=None) -> bool:
    """لغو جستجو حتی اگر سشن حافظه از بین رفته باشد (قفل یتیم)."""
    from bot.pv_dice import user_busy, ensure_sweeper

    await ensure_sweeper(bot)
    uid = int(user_id)
    busy = user_busy(uid)
    had_session = uid in _search_wait
    had_search_busy = bool(busy and busy[0] == "search")
    had_offer = any(
        int(o.get("challenger_id") or 0) == uid and o.get("status") == "pending"
        for o in SEARCH_OFFERS.values()
    )
    if not (had_session or had_search_busy or had_offer):
        return False
    clear_pv_search(uid)
    text = "❌ جستجوی حریف لغو شد."
    if message is not None:
        await message.answer(text)
    else:
        from bot.helpers import send_private
        await send_private(bot, uid, text)
    return True


@sync_to_async
def _list_user_pv_groups(user_id: int) -> list[tuple[int, str]]:
    """گروه‌های عضو با شروع پیوی روشن و حداقل یک تراکنش کیف‌پول، مرتب بر اساس آخرین تراکنش."""
    from account.models import TelegramGroup, TelegramGroupMember, WalletTransaction

    uid = int(user_id)
    member_ids = list(
        TelegramGroupMember.objects.filter(telegram_user_id=uid)
        .exclude(role="banned")
        .values_list("telegram_chat_id", flat=True)[:40]
    )
    if not member_ids:
        return []

    enabled = {
        int(g.telegram_chat_id): (g.name or str(g.telegram_chat_id))
        for g in TelegramGroup.objects.filter(
            telegram_chat_id__in=member_ids,
            pv_start_enabled=True,
        )
    }
    if not enabled:
        return []

    last_tx = {
        int(row["telegram_chat_id"]): row["last_at"]
        for row in WalletTransaction.objects.filter(
            telegram_user_id=uid,
            telegram_chat_id__in=list(enabled.keys()),
        )
        .values("telegram_chat_id")
        .annotate(last_at=Max("created_at"))
    }
    # فقط گپ‌هایی که برای این کاربر تراکنش دارند
    ranked = sorted(
        (cid for cid in enabled if cid in last_tx),
        key=lambda cid: last_tx[cid],
        reverse=True,
    )
    return [(cid, enabled[cid]) for cid in ranked[:12]]


@sync_to_async
def _group_min_and_name(group_id: int) -> tuple[int, str]:
    from account.models import TelegramGroup
    from bot.pv_dice import MIN_BET

    g = TelegramGroup.objects.filter(telegram_chat_id=int(group_id)).first()
    gmin = int(getattr(g, "min_pv_bet", 0) or 0) if g else 0
    eff = max(MIN_BET, gmin) if gmin > 0 else MIN_BET
    name = (g.name if g else "") or str(group_id)
    return eff, name


@sync_to_async
def _group_fee_mode(group_id: int) -> tuple[int, str]:
    from account.models import TelegramGroup

    g = TelegramGroup.objects.filter(telegram_chat_id=int(group_id)).first()
    fee = 10
    mode = BET_MODE_FIXED
    if g:
        if g.fee_percent is not None:
            fee = int(g.fee_percent)
        gm = getattr(g, "bet_mode", None)
        if gm in (BET_MODE_FIXED, BET_MODE_EXTRA):
            mode = gm
        elif gm == "fixed":
            mode = BET_MODE_FIXED
        elif gm == "extra":
            mode = BET_MODE_EXTRA
    return fee, mode


@sync_to_async
def _list_funded_user_ids(group_id: int, seeker_id: int, entry: int) -> list[int]:
    """اعضای گروه با point ≥ ورودی."""
    from account.models import TelegramGroupMember

    gid = int(group_id)
    seeker = int(seeker_id)
    need = max(0, int(entry or 0))
    qs = (
        TelegramGroupMember.objects.filter(
            telegram_chat_id=gid,
            point__gte=need,
        )
        .exclude(telegram_user_id=seeker)
        .exclude(role="banned")
        .order_by("-point")
        .values_list("telegram_user_id", flat=True)[:BROADCAST_LIMIT * 2]
    )
    return [int(x) for x in qs if x][:BROADCAST_LIMIT]


def _kb_amount(minimum: int) -> InlineKeyboardMarkup:
    amounts = [a for a in SUGGESTED_BETS if a >= int(minimum)]
    rows: list[list[IKB]] = []
    row: list[IKB] = []
    for a in amounts:
        row.append(IKB(text=f"{a:,}", callback_data=f"pvs:a:{a}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([IKB(text="✏️ دلخواه", callback_data="pvs:a:custom")])
    rows.append([IKB(text="❌ لغو", callback_data="pvs:x")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _kb_groups(groups: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = []
    for gid, name in groups:
        label = (name[:28] + "…") if len(name) > 29 else name
        rows.append([IKB(text=f"📍 {label}", callback_data=f"pvs:g:{gid}")])
    rows.append([IKB(text="❌ لغو", callback_data="pvs:x")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _collect_broadcast_targets(group_id: int, seeker_id: int, entry: int) -> tuple[list[int], dict]:
    """همه با موجودی کافی + فعالان ۱ ساعته بدون موجودی کافی.

    خروجی: (لیست هدف، آمار) — آمار شامل تعداد مشغول‌ها برای پیام بهتر است.
    """
    from bot.pv_dice import user_busy_label
    from bot.finance import get_playable_balance, spendable_for_games

    seeker = int(seeker_id)
    need = max(0, int(entry or 0))
    funded = await _list_funded_user_ids(group_id, seeker_id, entry)
    recent = await _list_recent_candidates(group_id, seeker_id)

    out: list[int] = []
    seen: set[int] = set()
    busy_count = 0
    considered = 0

    async def _try_add(uid, *, require_funded: bool | None = None):
        nonlocal busy_count, considered
        try:
            u = int(uid)
        except (TypeError, ValueError):
            return
        if not u or u == seeker or u in seen:
            return
        seen.add(u)
        considered += 1
        if user_busy_label(u) or is_user_involved_in_group_game(group_id, u):
            busy_count += 1
            return
        playable = 0
        if need > 0:
            _, playable, pending = await get_playable_balance(group_id, u)
            playable = int(spendable_for_games(playable, pending))
        can_pay = playable >= need if need > 0 else True
        if require_funded is True and not can_pay:
            return
        if require_funded is False and can_pay:
            return
        out.append(u)

    for uid in funded:
        await _try_add(uid, require_funded=True)
        if len(out) >= BROADCAST_LIMIT:
            return out, {"busy": busy_count, "considered": considered}

    for r in recent:
        await _try_add(r["user_id"], require_funded=False)
        if len(out) >= BROADCAST_LIMIT:
            break
    return out, {"busy": busy_count, "considered": considered}


def _format_no_broadcast_targets(*, gname: str, bet: int, busy: int) -> str:
    head = (
        "🔍 جستجوی حریف پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 گروه: {gname}\n"
        f"💰 مبلغ بازی: {bet:,} واحد\n\n"
    )
    if busy > 0:
        return (
            head
            + "⏳ الان حریف آزادی پیدا نشد.\n"
            + f"در این گپ {busy} نفر مشغول بازی یا دعوت پیوی هستند.\n\n"
            + "لطفاً چند لحظه صبر کنید و دوباره جستجو کنید."
        )
    return (
        head
        + "📭 گیرنده‌ای پیدا نشد.\n"
        + "کسی با موجودی کافی در این گپ نیست، و در ۱ ساعت گذشته "
        + "کسی بدون موجودی کافی در گپ/پیوی فعال نبوده.\n"
        + "بعداً دوباره «جستجو» کنید."
    )


async def _plain_name(bot: Bot, user_id: int, group_id: int | None = None) -> str:
    import re as _re
    from bot.helpers import user_mention_id

    try:
        html = await user_mention_id(user_id, bot, group_id)
        plain = _re.sub(r"<[^>]+>", "", html or "").strip()
        return plain or str(user_id)
    except Exception:
        return str(user_id)


async def _broadcast_search_offer(
    bot: Bot, user_id: int, *, message: Message | None = None, edit_message=None,
) -> None:
    """به‌جای انتخاب حریف: پخش درخواست به واجدین شرایط."""
    from bot.helpers import send_private
    from bot.pv_dice import (
        bind_search_offer, user_busy_label, format_pv_busy_message,
    )

    sess = _search_wait.get(int(user_id))
    if not sess or not sess.get("group_id") or not sess.get("bet_amount"):
        clear_pv_search(user_id)
        return

    async def _reply(text: str, **kw):
        if edit_message is not None:
            try:
                await edit_message.edit_text(text, **kw)
                return
            except Exception:
                pass
        if message:
            await message.answer(text, **kw)
        else:
            await send_private(bot, user_id, text, reply_markup=kw.get("reply_markup"))

    my_busy = user_busy_label(user_id)
    if my_busy and my_busy != "search":
        await _reply(format_pv_busy_message(my_busy, user_id=user_id))
        return

    group_id = int(sess["group_id"])
    bet = int(sess["bet_amount"])
    gname = sess.get("group_name") or str(group_id)
    fee = int(sess.get("fee_percent") or 0)
    bet_mode = sess.get("bet_mode") or BET_MODE_FIXED
    costs = calc_bet_costs(bet, fee, bet_mode, 2)
    entry = int(costs.get("entry") or 0)
    mode_label = "فیکس" if bet_mode == BET_MODE_FIXED else "اضافه"

    targets, stats = await _collect_broadcast_targets(group_id, user_id, entry)
    if not targets:
        text = _format_no_broadcast_targets(
            gname=gname, bet=bet, busy=int(stats.get("busy") or 0),
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [IKB(text="🔄 تلاش دوباره", callback_data="pvs:r")],
            [IKB(text="💰 تغییر مبلغ بازی", callback_data="pvs:bet")],
            [IKB(text="❌ لغو", callback_data="pvs:x")],
        ])
        sess["step"] = "waiting"
        sess.pop("offer_id", None)
        _search_wait[int(user_id)] = sess
        await _reply(text, reply_markup=kb)
        return

    ch_name = await _plain_name(bot, user_id, group_id)
    offer_id = uuid.uuid4().hex[:12]
    offer = {
        "id": offer_id,
        "group_id": int(group_id),
        "challenger_id": int(user_id),
        "challenger_name": ch_name,
        "bet_amount": bet,
        "fee_percent": fee,
        "bet_mode": bet_mode,
        "entry": entry,
        "winner_amount": int(costs.get("winner_total") or 0),
        "fee_amount": int(costs.get("total_fee") or 0),
        "mode_label": mode_label,
        "group_name": gname,
        "status": "pending",
        "created_at": time.time(),
        "expires_at": time.time() + SEARCH_OFFER_TTL,
        "recipients": list(targets),
        "claimed_by": None,
    }
    SEARCH_OFFERS[offer_id] = offer
    bind_search_offer(user_id, offer_id)

    money = (
        f"💳 ورودی هر نفر: {entry:,} واحد ({mode_label})\n"
        f"🏆 جایزه برنده: {int(costs.get('winner_total') or 0):,} واحد\n"
    )
    if int(costs.get("total_fee") or 0) > 0:
        money += f"💸 حق واسطه: {int(costs['total_fee']):,} واحد\n"

    challenge_text = (
        "⚔️ درخواست چالش پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"از طرف: {ch_name}\n"
        f"📍 گروه: {gname}\n"
        f"{money}"
        f"⏳ مهلت پاسخ: حدود {SEARCH_OFFER_TTL} ثانیه\n\n"
        "اولین نفری که در دسترس باشد و قبول کند، بازی شروع می‌شود.\n"
        "اگر موجودی کافی ندارید، با قبول کردن می‌توانید افزایش موجودی بزنید."
    )
    kb_acc = _accept_search_kb(offer_id)

    sent = 0
    for tid in targets:
        try:
            ok = await send_private(bot, tid, challenge_text, reply_markup=kb_acc)
            if ok:
                sent += 1
        except Exception:
            pass

    sess["step"] = "waiting"
    sess["offer_id"] = offer_id
    _search_wait[int(user_id)] = sess

    await _reply(
        "📤 درخواست چالش ارسال شد\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 گروه: {gname}\n"
        f"💰 مبلغ بازی: {bet:,} واحد\n"
        f"📨 ارسال موفق: {sent} نفر\n"
        f"⏳ منتظر اولین قبول‌کننده…\n\n"
        "تا قبل از قبول می‌توانید لغو کنید.",
        reply_markup=_waiting_search_kb(offer_id),
    )
    asyncio.create_task(_search_offer_timeout(bot, offer_id))


async def _search_offer_timeout(bot: Bot, offer_id: str) -> None:
    try:
        from bot.helpers import send_private

        offer = SEARCH_OFFERS.get(offer_id)
        if not offer:
            return
        wait = max(0.5, float(offer.get("expires_at") or 0) - time.time() + 0.3)
        await asyncio.sleep(wait)
        offer = SEARCH_OFFERS.get(offer_id)
        if not offer or offer.get("status") != "pending":
            return
        ch = offer.get("challenger_id")
        _expire_offer(offer_id, reason="timeout")
        if ch:
            # جلوگیری از لغو دوبارهٔ همان آفر در clear
            sess = _search_wait.get(int(ch))
            if sess and sess.get("offer_id") == offer_id:
                sess.pop("offer_id", None)
            clear_pv_search(ch)
            try:
                await send_private(
                    bot, int(ch),
                    "⏰ مهلت جستجوی حریف تمام شد؛ کسی قبول نکرد.\n"
                    "دوباره «جستجو» کنید.",
                )
            except Exception:
                pass
    except Exception:
        pass


async def _show_opponents(
    bot: Bot, user_id: int, *, edit_message=None, message: Message | None = None,
) -> None:
    """سازگاری: همان پخش همگانی."""
    await _broadcast_search_offer(bot, user_id, edit_message=edit_message, message=message)


async def start_pv_search(bot: Bot, user_id: int, *, message: Message | None = None) -> None:
    """شروع فلو جستجو با دستور «جستجو»."""
    from bot.pv_dice import ensure_sweeper, user_busy_label, format_pv_busy_message, is_in_active_pv_game

    await ensure_sweeper(bot)
    clear_pv_search(user_id)

    if is_in_active_pv_game(user_id):
        text = "⚠️ وسط بازی پیوی هستید؛ اول بازی فعلی را تمام کنید."
        if message:
            await message.answer(text)
        else:
            from bot.helpers import send_private
            await send_private(bot, user_id, text)
        return

    my_busy = user_busy_label(user_id)
    if my_busy:
        text = format_pv_busy_message(my_busy, user_id=user_id)
        if message:
            await message.answer(text)
        else:
            from bot.helpers import send_private
            await send_private(bot, user_id, text)
        return

    groups = await _list_user_pv_groups(user_id)

    async def _reply(text: str, **kw):
        if message:
            await message.answer(text, **kw)
        else:
            from bot.helpers import send_private
            await send_private(bot, user_id, text, **kw)

    if not groups:
        await _reply(
            "❌ گروهی برای جستجو پیدا نشد.\n\n"
            "باید عضو گپی باشید که:\n"
            "• شروع پیوی در آن روشن باشد\n"
            "• حداقل یک تراکنش کیف‌پول در آن داشته باشید"
        )
        return

    await _offer_groups_or_auto(bot, user_id, groups, message=message)


async def _offer_groups_or_auto(
    bot: Bot, user_id: int, groups: list[tuple[int, str]], *, message: Message | None = None,
) -> None:
    """یک گپ → مستقیم مبلغ؛ چند گپ → دکمه‌های انتخاب."""
    if len(groups) == 1:
        gid, gname = groups[0]
        await _ask_amount(bot, user_id, gid, gname, message=message)
        return

    _search_wait[int(user_id)] = {"step": "group"}
    text = (
        "🔍 جستجوی حریف پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "گروه را انتخاب کنید "
        "(فقط گپ‌هایی که شروع پیوی روشن است و تراکنش دارید):"
    )
    kb = _kb_groups(groups)
    if message:
        await message.answer(text, reply_markup=kb)
    else:
        from bot.helpers import send_private
        await send_private(bot, user_id, text, reply_markup=kb)


async def _ask_amount(
    bot: Bot, user_id: int, group_id: int, group_name: str,
    *, message: Message | None = None, edit_message=None,
) -> None:
    from bot.pv_dice import get_pv_start_settings, format_off_message

    cfg = await get_pv_start_settings(group_id)
    if not cfg.get("enabled"):
        text = format_off_message(cfg.get("reason") or "")
        if message:
            await message.answer(text)
        else:
            from bot.helpers import send_private
            await send_private(bot, user_id, text)
        clear_pv_search(user_id)
        return

    eff, _ = await _group_min_and_name(group_id)
    _search_wait[int(user_id)] = {
        "step": "amount",
        "group_id": int(group_id),
        "group_name": group_name,
        "min_bet": int(eff),
    }
    text = (
        "🔍 جستجوی حریف پیوی\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 گروه: {group_name}\n\n"
        f"💰 مبلغ بازی را انتخاب کنید.\n"
        f"حداقل در این گروه: <b>{eff:,}</b> واحد\n\n"
        "یا «✏️ دلخواه» را بزنید و عدد بفرستید."
    )
    kb = _kb_amount(eff)
    if edit_message is not None:
        try:
            await edit_message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass
    if message:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        from bot.helpers import send_private
        await send_private(bot, user_id, text, reply_markup=kb)


async def _commit_bet_amount(
    bot: Bot, uid: int, amount: int, *, message: Message | None = None, edit_message=None,
) -> bool:
    """اعتبارسنجی مبلغ و پخش چالش. True اگر موفق."""
    sess = _search_wait.get(int(uid))
    if not sess or not sess.get("group_id"):
        return False

    from bot.pv_dice import effective_min_pv_bet, get_min_pv_bet, format_min_pv_denial
    from bot.finance import get_playable_balance

    group_id = int(sess["group_id"])
    group_min = await get_min_pv_bet(group_id)
    eff = effective_min_pv_bet(group_min)

    async def _err(text: str, **kw):
        if edit_message is not None:
            try:
                await edit_message.answer(text, **kw)
                return
            except Exception:
                pass
        if message:
            await message.answer(text, **kw)
        else:
            from bot.helpers import send_private
            await send_private(bot, uid, text)

    if amount < eff:
        await _err(
            format_min_pv_denial(eff, amount) + "\n\nمبلغ دیگری انتخاب کنید.",
            parse_mode="HTML",
        )
        return False

    fee, bet_mode = await _group_fee_mode(group_id)
    costs = calc_bet_costs(amount, fee, bet_mode, 2)
    entry = int(costs.get("entry") or 0)
    if entry > 0:
        from bot.finance import spendable_for_games
        total_bal, playable, pending = await get_playable_balance(group_id, uid)
        spendable = spendable_for_games(playable, pending)
        if spendable < entry:
            shortfall = max(1, entry - int(spendable))
            text = format_search_shortage_message(
                entry=entry, playable=int(spendable), shortfall=shortfall,
            )
            kb = shortage_increase_kb(group_id, shortfall)
            if edit_message is not None:
                try:
                    await edit_message.answer(text, reply_markup=kb, parse_mode="HTML")
                    return False
                except Exception:
                    pass
            if message:
                await message.answer(text, reply_markup=kb, parse_mode="HTML")
            else:
                from bot.helpers import send_private
                await send_private(bot, uid, text, reply_markup=kb)
            return False

    sess["bet_amount"] = amount
    sess["fee_percent"] = fee
    sess["bet_mode"] = bet_mode
    sess["step"] = "waiting"
    _search_wait[int(uid)] = sess
    await _broadcast_search_offer(bot, uid, edit_message=edit_message, message=message)
    return True


async def handle_pv_search_text(message: Message, bot: Bot) -> bool:
    """پردازش مبلغ دلخواه / لغو در فلو جستجو."""
    uid = message.from_user.id
    sess = _search_wait.get(int(uid))
    if not sess:
        return False

    raw = (message.text or "").strip()
    if _cancel_words(raw):
        clear_pv_search(uid)
        await message.answer("❌ جستجوی حریف لغو شد.")
        return True

    step = sess.get("step")
    if step == "group":
        if raw in ("جستجو", "جستجوی حریف", "جستجو حریف"):
            await start_pv_search(bot, uid, message=message)
            return True
        groups = await _list_user_pv_groups(uid)
        if not groups:
            clear_pv_search(uid)
            await message.answer(
                "❌ گروهی برای جستجو پیدا نشد.\n\n"
                "باید عضو گپی باشید که شروع پیوی روشن باشد و تراکنش داشته باشید."
            )
            return True
        await _offer_groups_or_auto(bot, uid, groups, message=message)
        return True

    if step == "pick" or step == "waiting":
        if raw in ("جستجو", "جستجوی حریف", "جستجو حریف"):
            await start_pv_search(bot, uid, message=message)
            return True
        if raw == "بروزرسانی" and step == "waiting":
            await message.answer("درخواست قبلاً ارسال شده؛ منتظر قبول باشید یا لغو کنید.")
            return True
        await message.answer("منتظر قبول حریف باشید، یا «لغو» بزنید.")
        return True

    if step == "amount":
        await message.answer(
            "مبلغ را از دکمه‌ها انتخاب کنید، یا «✏️ دلخواه» را بزنید.",
            reply_markup=_kb_amount(int(sess.get("min_bet") or 100)),
        )
        return True

    if step != "amount_custom":
        clear_pv_search(uid)
        return False

    normalized = normalize_numbers(raw).replace(",", "").replace("_", "").strip()
    if not normalized.isdigit():
        await message.answer(
            "❌ مبلغ باید عدد باشد.\nمثال: <code>100</code>\nبرای لغو: لغو",
            parse_mode="HTML",
        )
        return True

    await _commit_bet_amount(bot, uid, int(normalized), message=message)
    return True


async def handle_pv_search_callback(call: CallbackQuery, bot: Bot) -> bool:
    data = call.data or ""
    if not data.startswith("pvs:"):
        return False

    uid = call.from_user.id
    await call.answer()

    if data == "pvs:x":
        clear_pv_search(uid)
        try:
            await call.message.edit_text("❌ جستجوی حریف لغو شد.")
        except Exception:
            await call.message.answer("❌ جستجوی حریف لغو شد.")
        return True

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "cx" and len(parts) >= 3:
        offer_id = parts[2]
        offer = SEARCH_OFFERS.get(offer_id)
        if offer and int(offer.get("challenger_id") or 0) == int(uid) and offer.get("status") == "pending":
            _expire_offer(offer_id, reason="cancelled")
        # جلوگیری از double-expire در clear
        sess = _search_wait.get(int(uid))
        if sess and sess.get("offer_id") == offer_id:
            sess.pop("offer_id", None)
        clear_pv_search(uid)
        try:
            await call.message.edit_text("❌ جستجوی حریف لغو شد.")
        except Exception:
            await call.message.answer("❌ جستجوی حریف لغو شد.")
        return True

    if action == "g" and len(parts) >= 3:
        try:
            group_id = int(parts[2])
        except ValueError:
            return True
        groups = await _list_user_pv_groups(uid)
        gname = next((n for g, n in groups if int(g) == group_id), str(group_id))
        if not any(int(g) == group_id for g, _ in groups):
            await call.message.answer("❌ این گروه برای شما در دسترس نیست یا شروع پیوی خاموش است.")
            clear_pv_search(uid)
            return True
        await _ask_amount(bot, uid, group_id, gname, message=call.message)
        return True

    if action == "a" and len(parts) >= 3:
        sess = _search_wait.get(int(uid))
        if not sess or sess.get("step") not in ("amount", "amount_custom"):
            await call.message.answer("جلسه جستجو منقضی شده؛ دوباره «جستجو» بنویسید.")
            return True
        token = parts[2]
        if token == "custom":
            sess["step"] = "amount_custom"
            _search_wait[int(uid)] = sess
            min_bet = int(sess.get("min_bet") or 0)
            try:
                await call.message.edit_text(
                    "✏️ مبلغ دلخواه را بفرستید.\n"
                    f"حداقل: <b>{min_bet:,}</b> واحد\n\n"
                    "برای لغو: لغو",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        IKB(text="❌ لغو", callback_data="pvs:x"),
                    ]]),
                )
            except Exception:
                await call.message.answer(
                    "✏️ مبلغ دلخواه را بفرستید.\n"
                    f"حداقل: <b>{min_bet:,}</b> واحد\nبرای لغو: لغو",
                    parse_mode="HTML",
                )
            return True
        try:
            amount = int(token)
        except ValueError:
            return True
        await _commit_bet_amount(bot, uid, amount, edit_message=call.message, message=call.message)
        return True

    if action == "go":
        clear_pv_search(uid)
        await start_pv_search(bot, uid, message=call.message)
        return True

    if action == "inc" and len(parts) >= 4:
        try:
            group_id = int(parts[2])
            suggested = int(parts[3])
        except ValueError:
            return True
        from bot.hidden_increase import start_increase_request_flow
        mark_offer_search_after_increase(uid)
        ok = await start_increase_request_flow(
            bot, uid, group_id,
            suggested_amount=(suggested if suggested > 0 else None),
        )
        if not ok:
            await call.message.answer("⚠️ شروع درخواست افزایش ناموفق بود.")
        return True

    if action == "r":
        sess = _search_wait.get(int(uid))
        if not sess or sess.get("step") not in ("waiting", "pick"):
            await call.message.answer("جلسه جستجو منقضی شده؛ دوباره «جستجو» بنویسید.")
            return True
        if not sess.get("offer_id") and sess.get("bet_amount") and sess.get("group_id"):
            await _broadcast_search_offer(
                bot, uid, edit_message=call.message, message=call.message,
            )
            return True
        await call.message.answer("درخواست قبلاً ارسال شده؛ منتظر قبول باشید یا لغو کنید.")
        return True

    if action == "bet":
        sess = _search_wait.get(int(uid))
        if not sess or not sess.get("group_id"):
            await call.message.answer("جلسه جستجو منقضی شده؛ دوباره «جستجو» بنویسید.")
            return True
        if sess.get("offer_id"):
            _expire_offer(sess["offer_id"], reason="cancelled")
            sess.pop("offer_id", None)
        group_id = int(sess["group_id"])
        gname = sess.get("group_name") or str(group_id)
        await _ask_amount(
            bot, uid, group_id, gname,
            message=call.message, edit_message=call.message,
        )
        return True

    if action == "acc" and len(parts) >= 3:
        await _accept_search_offer(bot, uid, parts[2], call=call)
        return True

    if action == "o" and len(parts) >= 3:
        # سازگاری دکمه‌های قدیمی — دیگر استفاده نمی‌شود
        await call.message.answer(
            "این روش انتخاب حریف دیگر فعال نیست.\n"
            "جستجو الان به‌صورت همگانی ارسال می‌شود؛ از «جستجوی حریف» استفاده کنید.",
            reply_markup=search_opponent_kb(),
        )
        return True

    return True


async def _accept_search_offer(
    bot: Bot, uid: int, offer_id: str, *, call: CallbackQuery | None = None,
) -> None:
    from bot.helpers import send_private
    from bot.pv_dice import (
        create_invite,
        ensure_sweeper,
        user_busy_label,
        format_pv_busy_message,
        get_pv_start_settings,
        format_off_message,
        unbind_search_offer,
        bind_search_offer,
        _accept_invite,
    )
    from bot.finance import get_playable_balance

    async def _reply(text: str, **kw):
        if call is not None:
            try:
                await call.message.answer(text, **kw)
                return
            except Exception:
                pass
        await send_private(bot, uid, text, reply_markup=kw.get("reply_markup"))

    await ensure_sweeper(bot)
    offer_id = str(offer_id)
    lock = _offer_locks.setdefault(offer_id, asyncio.Lock())
    async with lock:
        offer = SEARCH_OFFERS.get(offer_id)
        if not offer or offer.get("status") != "pending":
            await _reply(
                format_search_taken_message(),
                reply_markup=search_opponent_kb(),
            )
            return

        if time.time() > float(offer.get("expires_at") or 0):
            _expire_offer(offer_id, reason="timeout")
            await _reply(
                format_search_taken_message(),
                reply_markup=search_opponent_kb(),
            )
            return

        challenger = int(offer.get("challenger_id"))
        acceptor = int(uid)
        if acceptor == challenger:
            await _reply("❌ نمی‌توانید چالش خودتان را قبول کنید.")
            return

        group_id = int(offer["group_id"])
        entry = int(offer.get("entry") or 0)
        bet = int(offer.get("bet_amount") or 0)
        fee = int(offer.get("fee_percent") or 0)
        bet_mode = offer.get("bet_mode") or BET_MODE_FIXED

        cfg = await get_pv_start_settings(group_id)
        if not cfg.get("enabled"):
            await _reply(format_off_message(cfg.get("reason") or ""))
            return

        my_busy = user_busy_label(acceptor)
        if my_busy:
            await _reply(format_pv_busy_message(my_busy, user_id=acceptor))
            return
        if is_user_involved_in_group_game(group_id, acceptor):
            await _reply("⚠️ شما در بازی گروهی این گپ هستید؛ اول آن را تمام کنید.")
            return

        if entry > 0:
            from bot.finance import spendable_for_games
            _, playable, pending = await get_playable_balance(group_id, acceptor)
            spendable = spendable_for_games(playable, pending)
            if spendable < entry:
                shortfall = max(1, entry - int(spendable))
                await _reply(
                    format_search_shortage_message(
                        entry=entry, playable=int(spendable), shortfall=shortfall,
                    ),
                    parse_mode="HTML",
                    reply_markup=shortage_increase_kb(group_id, shortfall),
                )
                return

        ch_busy = user_busy_label(challenger)
        if ch_busy and ch_busy != "search":
            await _reply(
                "⚠️ فرستنده چالش الان مشغول است و نمی‌توان بازی را شروع کرد.",
            )
            return

        tg_name = await _plain_name(bot, acceptor, group_id)
        ch_name = offer.get("challenger_name") or await _plain_name(bot, challenger, group_id)

        # claim
        offer["status"] = "claimed"
        offer["claimed_by"] = acceptor
        unbind_search_offer(challenger, offer_id)
        # clear بدون expire دوباره
        sess = _search_wait.get(challenger)
        if sess and sess.get("offer_id") == offer_id:
            sess.pop("offer_id", None)
        clear_pv_search(challenger)

        invite_id = await create_invite(
            bot,
            group_id=group_id,
            challenger_id=challenger,
            target_id=acceptor,
            bet_amount=bet,
            has_bet=True,
            bet_mode=bet_mode,
            fee_percent=fee,
            group_msg_id=None,
            challenger_name=ch_name,
            target_name=tg_name,
            via_search=True,
            deliver=False,
        )
        if not invite_id:
            offer["status"] = "pending"
            offer["claimed_by"] = None
            try:
                bind_search_offer(challenger, offer_id)
                _search_wait[int(challenger)] = {
                    "step": "waiting",
                    "group_id": group_id,
                    "group_name": offer.get("group_name"),
                    "bet_amount": bet,
                    "fee_percent": fee,
                    "bet_mode": bet_mode,
                    "offer_id": offer_id,
                }
            except Exception:
                pass
            await _reply(
                "⚠️ الان نمی‌توان بازی را شروع کرد؛ یکی از طرفین مشغول است. دوباره تلاش کنید.",
            )
            return

        ok = await _accept_invite(bot, acceptor, invite_id)
        if not ok:
            from bot.pv_dice import INVITES, _expire_invite
            leftover = INVITES.get(invite_id)
            if leftover and leftover.get("status") in ("pending", "accepting"):
                leftover["status"] = "pending"
                try:
                    await _expire_invite(bot, invite_id, reason="search_accept_fail")
                except Exception:
                    pass
            offer = SEARCH_OFFERS.get(offer_id)
            if offer and offer.get("status") == "claimed" and int(offer.get("claimed_by") or 0) == acceptor:
                offer["status"] = "pending"
                offer["claimed_by"] = None
                try:
                    bind_search_offer(challenger, offer_id)
                    _search_wait[int(challenger)] = {
                        "step": "waiting",
                        "group_id": group_id,
                        "group_name": offer.get("group_name"),
                        "bet_amount": bet,
                        "fee_percent": fee,
                        "bet_mode": bet_mode,
                        "offer_id": offer_id,
                    }
                except Exception:
                    pass
            await _reply("⚠️ قبول چالش انجام نشد. دوباره تلاش کنید.")
            return
        # پیام شروع بازی از _accept_invite می‌آید
        return


async def _invite_from_search(bot: Bot, uid: int, target_id: int, *, call: CallbackQuery) -> None:
    await call.message.answer(
        "انتخاب تکی حریف حذف شده؛ بعد از تعیین مبلغ، درخواست به همه واجدین شرایط ارسال می‌شود.",
        reply_markup=search_opponent_kb(),
    )
