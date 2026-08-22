"""
دکمه‌های اینلاینِ زمینه‌ای برای گروه — بدونِ دست‌زدن به هندلرهای موجود.

منطق:
  • کیبوردها اینجا ساخته می‌شوند (balance_kb / insufficient_kb / game_end_kb / panel_kb).
  • میدل‌ویرِ `group_buttons_middleware` این کیبوردها را — بر اساسِ متنِ پیامِ خروجی و
    فقط وقتی پیام دکمه ندارد — به کارتِ موجودی / پیامِ «موجودی ناکافی» / نتیجه‌ی
    بازی می‌چسباند.
  • callbackهای `gi:*` اینجا هندل می‌شوند و «فقط برای صاحبِ همان پیام» کار می‌کنند.
    - پیام‌هایی که خودمان می‌سازیم: شناسه‌ی صاحب داخلِ callback_data است (`gi:act:OWNER`).
    - کارت‌هایی که میدل‌ویر می‌چسباند: صاحب = نویسنده‌ی پیامی که بات به آن ریپلای کرده.
  • خروجیِ هر view یا «در جا ادیت» می‌شود (پیامِ جدید نمی‌دهد تا گپ شلوغ نشود) یا اگر
    پیامِ فعلی «نتیجه‌ی بازی» باشد، پیامِ جدید می‌دهد تا نتیجه محفوظ بماند.

ایموجیِ ابتداییِ هر دکمه را میدل‌ویرِ پرمیوم به آیکونِ پرمیوم تبدیل می‌کند.
"""
from __future__ import annotations

import importlib
import logging

from aiogram import Bot, F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton as Btn,
    InlineKeyboardMarkup,
)

logger = logging.getLogger(__name__)

router = Router(name="group_inline")


# ─── کیبوردها ────────────────────────────────────────────────────────────────
def _cb(action: str, owner_id: int | None) -> str:
    """callback_data؛ اگر صاحب معلوم باشد، شناسه‌اش را می‌چسباند: gi:act:OWNER."""
    return f"gi:{action}:{owner_id}" if owner_id else f"gi:{action}"


def balance_kb(owner_id: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="➕ افزایش موجودی", callback_data=_cb("inc", owner_id)),
         Btn(text="🔄 بروزرسانی", callback_data=_cb("bal", owner_id))],
        [Btn(text="📊 آمار من", callback_data=_cb("stats", owner_id)),
         Btn(text="🏅 لیگ من", callback_data=_cb("league", owner_id))],
        [Btn(text="🎮 بازی‌ها", callback_data=_cb("games", owner_id)),
         Btn(text="🏆 برترین", callback_data=_cb("top", owner_id))],
    ])


def insufficient_kb(owner_id: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="➕ افزایش موجودی", callback_data=_cb("inc", owner_id))],
        [Btn(text="🎮 بازی‌ها", callback_data=_cb("games", owner_id)),
         Btn(text="💳 موجودی من", callback_data=_cb("bal", owner_id))],
    ])


def game_end_kb(owner_id: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🎲 تاس مجدد", callback_data=_cb("again", owner_id)),
         Btn(text="💳 موجودی من", callback_data=_cb("bal", owner_id))],
        [Btn(text="🏅 لیگ من", callback_data=_cb("league", owner_id)),
         Btn(text="🏆 برترین", callback_data=_cb("top", owner_id))],
        [Btn(text="🎮 بازی‌ها", callback_data=_cb("games", owner_id))],
    ])


def panel_kb(owner_id: int | None = None) -> InlineKeyboardMarkup:
    """کیبوردِ یکپارچه برای view‌های ادیت‌شده — با شناسه‌ی صاحب در callback_data."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="💳 موجودی", callback_data=_cb("bal", owner_id)),
         Btn(text="📊 آمار من", callback_data=_cb("stats", owner_id))],
        [Btn(text="🏅 لیگ من", callback_data=_cb("league", owner_id)),
         Btn(text="🏆 برترین", callback_data=_cb("top", owner_id))],
        [Btn(text="🎮 بازی‌ها", callback_data=_cb("games", owner_id)),
         Btn(text="➕ افزایش", callback_data=_cb("inc", owner_id))],
    ])


# ─── تشخیصِ نوعِ پیام از روی متن (میدل‌ویر این را صدا می‌زند) ──────────────────
def detect_keyboard(text: str) -> InlineKeyboardMarkup | None:
    """
    بر اساسِ نشانه‌های یکتای متن، کیبوردِ مناسب را برمی‌گرداند (یا None).
    بدونِ owner_id ساخته می‌شود؛ صاحب هنگامِ callback از روی reply تشخیص داده می‌شود.
    """
    if not text:
        return None
    if "💳 موجودی حساب" in text:
        return balance_kb()
    if "❌ موجودی ناکافی" in text:
        return insufficient_kb()
    if ("🏆 نتایج نهایی" in text
            or "مسابقه تاس تمام شد" in text
            or "مسابقه تاس به پایان" in text):
        return game_end_kb()
    return None


# ─── تشخیصِ صاحبِ دکمه ────────────────────────────────────────────────────────
def _owner_id(cq: CallbackQuery) -> int | None:
    """
    صاحبِ دکمه: اول از callback_data (gi:act:OWNER)، وگرنه نویسنده‌ی پیامی که بات
    به آن ریپلای کرده (درخواست‌کننده‌ی اصلی). اگر هیچ‌کدام نبود، None (بدونِ محدودیت).
    """
    parts = (cq.data or "").split(":")
    if len(parts) >= 3 and parts[2].lstrip("-").isdigit():
        return int(parts[2])
    msg = cq.message
    rt = getattr(msg, "reply_to_message", None) if msg else None
    if rt and rt.from_user and not rt.from_user.is_bot:
        return rt.from_user.id
    return None


def _check_owner(cq: CallbackQuery) -> bool:
    oid = _owner_id(cq)
    return oid is None or cq.from_user.id == oid


# ─── تحویلِ خروجی: نتیجه‌ی بازی محفوظ می‌ماند؛ بقیه در جا ادیت می‌شوند ──────────
_RESULT_MARKERS = ("نتایج نهایی", "مسابقه تاس")


def _is_result_message(cq: CallbackQuery) -> bool:
    t = (cq.message.text or cq.message.caption or "") if cq.message else ""
    return any(m in t for m in _RESULT_MARKERS)


async def _deliver(cq: CallbackQuery, text: str, *, preserve: bool, owner_id: int) -> None:
    """preserve=True → پیامِ جدید (نتیجه محفوظ)؛ False → ادیتِ در جا. خطاها بی‌صدا."""
    try:
        if preserve:
            await cq.message.answer(text, reply_markup=panel_kb(owner_id), parse_mode="HTML")
        else:
            await cq.message.edit_text(text, reply_markup=panel_kb(owner_id), parse_mode="HTML")
    except Exception as exc:
        logger.debug("gi deliver skipped (preserve=%s): %s", preserve, exc)


class _EditRedirectBot:
    """
    پوششِ سبک روی bot تا خروجیِ هندلرهای موجود (که با safe_send→bot.send_message
    می‌فرستند) را کنترل کنیم: اولین send_message را یا «در جا ادیت» می‌کند
    (preserve=False) یا به پیامِ جدیدِ ریپلای‌شده تبدیل می‌کند (preserve=True؛ برای
    نتیجه‌ها). کیبورد همیشه panel_kb با شناسه‌ی صاحب است. بقیه pass-through.
    """
    def __init__(self, real_bot, chat_id: int, message_id: int, preserve: bool, owner_id: int):
        self._bot = real_bot
        self._chat_id = chat_id
        self._mid = message_id
        self._preserve = preserve
        self._owner = owner_id
        self._used = False

    def __getattr__(self, name):
        return getattr(self._bot, name)

    async def send_message(self, chat_id, text, **kwargs):
        if not self._used:
            self._used = True
            pm = kwargs.get("parse_mode", "HTML")
            try:
                if self._preserve:
                    return await self._bot.send_message(
                        self._chat_id, text,
                        reply_to_message_id=self._mid,
                        parse_mode=pm, reply_markup=panel_kb(self._owner),
                    )
                return await self._bot.edit_message_text(
                    text=text, chat_id=self._chat_id, message_id=self._mid,
                    reply_markup=panel_kb(self._owner), parse_mode=pm,
                )
            except Exception as exc:
                logger.debug("redirect deliver failed, sending plain: %s", exc)
        return await self._bot.send_message(chat_id, text, **kwargs)


async def _run_via_handler(cq: CallbackQuery, bot: Bot, module: str, fn_name: str, wants_bot: bool) -> None:
    """
    هندلرِ موجود را با هویتِ لمس‌کننده اجرا می‌کند و خروجی‌اش را در جا ادیت یا
    (روی نتیجه‌ها) پیامِ جدید تحویل می‌دهد. آرگومانِ bot همان botِ واقعی می‌ماند.
    """
    fn = getattr(importlib.import_module(module), fn_name)
    proxy = cq.message.model_copy(update={"from_user": cq.from_user})
    wrapped = _EditRedirectBot(
        bot, cq.message.chat.id, cq.message.message_id,
        preserve=_is_result_message(cq), owner_id=cq.from_user.id,
    )
    proxy.as_(wrapped)
    if wants_bot:
        await fn(proxy, bot)
    else:
        await fn(proxy)


# ─── دیسپچرِ واحدِ callback ────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("gi:"))
async def gi_dispatch(cq: CallbackQuery, bot: Bot):
    parts = (cq.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""

    # فقط صاحبِ همان پیام مجاز است
    if not _check_owner(cq):
        return await cq.answer("این دکمه برای شما نیست 🚫", show_alert=False)

    me = cq.from_user.id  # از این‌جا به بعد، صاحبِ view = خودِ لمس‌کننده

    try:
        if action == "inc":
            return await cq.answer(
                "برای افزایش موجودی:\n"
                "• از ادمین گروه بخواه روی پیامت «افزایش 5000» بزند.\n"
                "• اگر درخواست از پیوی روشن باشد، در پیوی ربات مبلغ را بفرست.",
                show_alert=True,
            )
        if action == "again":
            return await cq.answer(
                "برای شروع بازیِ جدید، در گروه بنویس: «تاس»\n"
                "یا نام بازی: بسکتبال · دارت · پنالتی · بولینگ · اسلات",
                show_alert=True,
            )
        if action == "bal":
            from bot.finance import get_playable_balance, format_balance_card
            import html as _html
            import jdatetime
            total, playable, pending = await get_playable_balance(cq.message.chat.id, me)
            name = cq.from_user.full_name or cq.from_user.first_name or "کاربر"
            time_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
            text = format_balance_card(
                playable=playable, pending=pending, total=total,
                time_str=time_str, viewer_name=_html.escape(name),
                viewing_other=False, html=True,
            )
            await _deliver(cq, text, preserve=_is_result_message(cq), owner_id=me)
            return await cq.answer()
        if action == "stats":
            await _run_via_handler(cq, bot, "bot.handlers.main_group", "cmd_stats", True)
            return await cq.answer()
        if action == "league":
            await _run_via_handler(cq, bot, "bot.handlers.main_group", "cmd_league_me", True)
            return await cq.answer()
        if action == "top":
            await _run_via_handler(cq, bot, "bot.handlers.main_group", "cmd_top_users", True)
            return await cq.answer()
        if action == "games":
            await _run_via_handler(cq, bot, "bot.handlers.main_group", "cmd_games_list", False)
            return await cq.answer()
        return await cq.answer()
    except Exception:
        logger.exception("gi_dispatch %s failed", action)
        return await cq.answer("خطا", show_alert=False)
