"""
دکمه‌های اینلاینِ زمینه‌ای برای گروه — بدونِ دست‌زدن به هندلرهای موجود.

منطق:
  • کیبوردها اینجا ساخته می‌شوند (balance_kb / insufficient_kb / game_end_kb).
  • میدل‌ویرِ `group_buttons_middleware` این کیبوردها را — بر اساسِ متنِ پیامِ خروجی و
    فقط وقتی پیام دکمه ندارد — به کارتِ موجودی / پیامِ «موجودی ناکافی» / نتیجه‌ی
    بازی می‌چسباند.
  • callbackهای `gi:*` اینجا هندل می‌شوند و با «هویتِ کاربرِ لمس‌کننده» کار می‌کنند
    (از طریقِ یک Message پروکسی که هندلرهای موجود را دوباره استفاده می‌کند).

ایموجیِ ابتداییِ هر دکمه را میدل‌ویرِ پرمیوم به آیکونِ پرمیوم تبدیل می‌کند.
"""
from __future__ import annotations

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


# ─── کمک‌کار: اجرای یک هندلرِ موجود با هویتِ کاربرِ لمس‌کننده ──────────────────
async def _run_as_user(cq: CallbackQuery, bot: Bot, module: str, fn_name: str, wants_bot: bool) -> None:
    """
    هندلرِ موجود را با یک Message پروکسی صدا می‌زند که from_user آن = لمس‌کننده و
    chat آن = همان گروه است؛ پس خروجی برای «خودِ کاربر» و در گروه ارسال می‌شود.
    """
    import importlib
    mod = importlib.import_module(module)
    fn = getattr(mod, fn_name)
    try:
        proxy = cq.message.model_copy(update={"from_user": cq.from_user})
        proxy.as_(bot)
    except Exception:
        proxy = cq.message  # fallback: chat-scoped فقط
    if wants_bot:
        await fn(proxy, bot)
    else:
        await fn(proxy)


# ─── callbackها ──────────────────────────────────────────────────────────────
@router.callback_query(F.data == "gi:bal")
async def cb_balance(cq: CallbackQuery, bot: Bot):
    try:
        from bot.finance import get_playable_balance, format_balance_card
        import html as _html
        import jdatetime
        chat_id = cq.message.chat.id
        uid = cq.from_user.id
        total, playable, pending = await get_playable_balance(chat_id, uid)
        name = cq.from_user.full_name or cq.from_user.first_name or "کاربر"
        time_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
        text = format_balance_card(
            playable=playable, pending=pending, total=total,
            time_str=time_str, viewer_name=_html.escape(name),
            viewing_other=False, html=True,
        )
        await bot.send_message(
            chat_id, text, reply_to_message_id=cq.message.message_id, parse_mode="HTML",
        )
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
        await _run_as_user(cq, bot, "bot.handlers.main_group", "cmd_stats", True)
        await cq.answer()
    except Exception:
        logger.exception("gi:stats failed")
        await cq.answer("خطا", show_alert=False)


@router.callback_query(F.data == "gi:league")
async def cb_league(cq: CallbackQuery, bot: Bot):
    try:
        await _run_as_user(cq, bot, "bot.handlers.main_group", "cmd_league_me", True)
        await cq.answer()
    except Exception:
        logger.exception("gi:league failed")
        await cq.answer("خطا", show_alert=False)


@router.callback_query(F.data == "gi:top")
async def cb_top(cq: CallbackQuery, bot: Bot):
    try:
        from bot.handlers.main_group import cmd_top_users
        await cmd_top_users(cq.message, bot)  # chat-scoped
        await cq.answer()
    except Exception:
        logger.exception("gi:top failed")
        await cq.answer("خطا", show_alert=False)


@router.callback_query(F.data == "gi:games")
async def cb_games(cq: CallbackQuery):
    try:
        from bot.handlers.main_group import cmd_games_list
        await cmd_games_list(cq.message)  # chat-scoped
        await cq.answer()
    except Exception:
        logger.exception("gi:games failed")
        await cq.answer("خطا", show_alert=False)
