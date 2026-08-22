"""
دکمه‌های اینلاینِ زمینه‌ای برای گروه — بدونِ دست‌زدن به هندلرهای موجود.

منطق:
  • کیبوردها اینجا ساخته می‌شوند (balance_kb / insufficient_kb / game_end_kb).
  • میدل‌ویرِ `group_buttons_middleware` این کیبوردها را — بر اساسِ متنِ پیامِ خروجی و
    فقط وقتی پیام دکمه ندارد — به کارتِ موجودی / پیامِ «موجودی ناکافی» / نتیجه‌ی
    بازی می‌چسباند.
  • callbackهای `gi:*` اینجا هندل می‌شوند و «همان پیام را ادیت می‌کنند» (پیامِ جدید
    نمی‌فرستند تا گپ شلوغ نشود)، با «هویتِ کاربرِ لمس‌کننده».

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
def balance_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="➕ افزایش موجودی", callback_data="gi:inc"),
         Btn(text="🔄 بروزرسانی", callback_data="gi:bal")],
        [Btn(text="📊 آمار من", callback_data="gi:stats"),
         Btn(text="🏅 لیگ من", callback_data="gi:league")],
        [Btn(text="🎮 بازی‌ها", callback_data="gi:games"),
         Btn(text="🏆 برترین", callback_data="gi:top")],
    ])


def insufficient_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="➕ افزایش موجودی", callback_data="gi:inc")],
        [Btn(text="🎮 بازی‌ها", callback_data="gi:games"),
         Btn(text="💳 موجودی من", callback_data="gi:bal")],
    ])


def game_end_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🎲 تاس مجدد", callback_data="gi:again"),
         Btn(text="💳 موجودی من", callback_data="gi:bal")],
        [Btn(text="🏅 لیگ من", callback_data="gi:league"),
         Btn(text="🏆 برترین", callback_data="gi:top")],
        [Btn(text="🎮 بازی‌ها", callback_data="gi:games")],
    ])


def panel_kb() -> InlineKeyboardMarkup:
    """کیبوردِ یکپارچه برای view‌های ادیت‌شده — پیمایش بینِ بخش‌ها در همان پیام."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="💳 موجودی", callback_data="gi:bal"),
         Btn(text="📊 آمار من", callback_data="gi:stats")],
        [Btn(text="🏅 لیگ من", callback_data="gi:league"),
         Btn(text="🏆 برترین", callback_data="gi:top")],
        [Btn(text="🎮 بازی‌ها", callback_data="gi:games"),
         Btn(text="➕ افزایش", callback_data="gi:inc")],
    ])


# ─── تشخیصِ نوعِ پیام از روی متن (میدل‌ویر این را صدا می‌زند) ──────────────────
def detect_keyboard(text: str) -> InlineKeyboardMarkup | None:
    """
    بر اساسِ نشانه‌های یکتای متن، کیبوردِ مناسب را برمی‌گرداند (یا None).
    متن در این مرحله هنوز خام است (قبل از تزریقِ tg-emoji).
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


# ─── نتیجه‌ی بازی محفوظ می‌ماند؛ بقیه در جا ادیت می‌شوند ──────────────────────
# اگر پیامِ لمس‌شده «نتیجه‌ی بازی» باشد، ادیتش نمی‌کنیم (پیامِ جدید می‌دهیم) تا نتیجه
# در گپ بماند. کارتِ موجودی/آمار/... در جا ادیت می‌شوند تا گپ شلوغ نشود.
_RESULT_MARKERS = ("نتایج نهایی", "مسابقه تاس")


def _is_result_message(cq: CallbackQuery) -> bool:
    t = (cq.message.text or cq.message.caption or "") if cq.message else ""
    return any(m in t for m in _RESULT_MARKERS)


async def _deliver(cq: CallbackQuery, text: str, *, preserve: bool) -> None:
    """preserve=True → پیامِ جدید (نتیجه محفوظ)؛ False → ادیتِ در جا. خطاها بی‌صدا."""
    try:
        if preserve:
            await cq.message.answer(text, reply_markup=panel_kb(), parse_mode="HTML")
        else:
            await cq.message.edit_text(text, reply_markup=panel_kb(), parse_mode="HTML")
    except Exception as exc:
        logger.debug("gi deliver skipped (preserve=%s): %s", preserve, exc)


class _EditRedirectBot:
    """
    پوششِ سبک روی bot تا خروجیِ هندلرهای موجود (که با safe_send→bot.send_message
    می‌فرستند) را کنترل کنیم: اولین send_message را یا «در جا ادیت» می‌کند
    (preserve=False) یا به یک پیامِ جدیدِ ریپلای‌شده با panel_kb تبدیل می‌کند
    (preserve=True؛ برای پیام‌های نتیجه که نباید محو شوند). بقیه pass-through.
    """
    def __init__(self, real_bot, chat_id: int, message_id: int, preserve: bool):
        self._bot = real_bot
        self._chat_id = chat_id
        self._mid = message_id
        self._preserve = preserve
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
                        parse_mode=pm, reply_markup=panel_kb(),
                    )
                return await self._bot.edit_message_text(
                    text=text, chat_id=self._chat_id, message_id=self._mid,
                    reply_markup=panel_kb(), parse_mode=pm,
                )
            except Exception as exc:
                logger.debug("redirect deliver failed, sending plain: %s", exc)
        # fallback / ارسال‌های بعدی: عادی بفرست
        return await self._bot.send_message(chat_id, text, **kwargs)


async def _run_via_handler(cq: CallbackQuery, bot: Bot, module: str, fn_name: str, wants_bot: bool) -> None:
    """
    هندلرِ موجود را با هویتِ لمس‌کننده اجرا می‌کند و خروجی‌اش را — بسته به اینکه
    پیامِ فعلی «نتیجه» است یا نه — در جا ادیت یا به‌صورتِ پیامِ جدید تحویل می‌دهد.
    آرگومانِ bot (برای get_chat_member و ...) همان botِ واقعی می‌ماند.
    """
    fn = getattr(importlib.import_module(module), fn_name)
    proxy = cq.message.model_copy(update={"from_user": cq.from_user})
    wrapped = _EditRedirectBot(
        bot, cq.message.chat.id, cq.message.message_id, preserve=_is_result_message(cq),
    )
    proxy.as_(wrapped)
    if wants_bot:
        await fn(proxy, bot)
    else:
        await fn(proxy)


# ─── callbackها ──────────────────────────────────────────────────────────────
@router.callback_query(F.data == "gi:bal")
async def cb_balance(cq: CallbackQuery):
    try:
        from bot.finance import get_playable_balance, format_balance_card
        import html as _html
        import jdatetime
        total, playable, pending = await get_playable_balance(cq.message.chat.id, cq.from_user.id)
        name = cq.from_user.full_name or cq.from_user.first_name or "کاربر"
        time_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
        text = format_balance_card(
            playable=playable, pending=pending, total=total,
            time_str=time_str, viewer_name=_html.escape(name),
            viewing_other=False, html=True,
        )
        await _deliver(cq, text, preserve=_is_result_message(cq))
        await cq.answer()
    except Exception:
        logger.exception("gi:bal failed")
        await cq.answer("خطا در دریافت موجودی", show_alert=False)


@router.callback_query(F.data == "gi:inc")
async def cb_increase(cq: CallbackQuery):
    await cq.answer(
        "برای افزایش موجودی:\n"
        "• از ادمین گروه بخواه روی پیامت «افزایش 5000» بزند.\n"
        "• اگر درخواست از پیوی روشن باشد، در پیوی ربات مبلغ را بفرست.",
        show_alert=True,
    )


@router.callback_query(F.data == "gi:again")
async def cb_again(cq: CallbackQuery):
    await cq.answer(
        "برای شروع بازیِ جدید، در گروه بنویس: «تاس»\n"
        "یا نام بازی: بسکتبال · دارت · پنالتی · بولینگ · اسلات",
        show_alert=True,
    )


@router.callback_query(F.data == "gi:stats")
async def cb_stats(cq: CallbackQuery, bot: Bot):
    try:
        await _run_via_handler(cq, bot, "bot.handlers.main_group", "cmd_stats", True)
        await cq.answer()
    except Exception:
        logger.exception("gi:stats failed")
        await cq.answer("خطا", show_alert=False)


@router.callback_query(F.data == "gi:league")
async def cb_league(cq: CallbackQuery, bot: Bot):
    try:
        await _run_via_handler(cq, bot, "bot.handlers.main_group", "cmd_league_me", True)
        await cq.answer()
    except Exception:
        logger.exception("gi:league failed")
        await cq.answer("خطا", show_alert=False)


@router.callback_query(F.data == "gi:top")
async def cb_top(cq: CallbackQuery, bot: Bot):
    try:
        await _run_via_handler(cq, bot, "bot.handlers.main_group", "cmd_top_users", True)
        await cq.answer()
    except Exception:
        logger.exception("gi:top failed")
        await cq.answer("خطا", show_alert=False)


@router.callback_query(F.data == "gi:games")
async def cb_games(cq: CallbackQuery, bot: Bot):
    try:
        await _run_via_handler(cq, bot, "bot.handlers.main_group", "cmd_games_list", False)
        await cq.answer()
    except Exception:
        logger.exception("gi:games failed")
        await cq.answer("خطا", show_alert=False)
