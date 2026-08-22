"""
منوی کاربریِ گروه — دو کیبورد:

۱) کیبوردِ زیرِ صفحه (Reply): با لمسِ هر دکمه، همان دستورِ موجودِ ربات با هویتِ خودِ
   کاربر اجرا می‌شود (کاملاً کاربردی). ایموجیِ این دکمه‌ها عادی است (تلگرام روی Reply
   ایموجی پرمیوم نمی‌دهد).
۲) منوی شیشه‌ای (Inline): رنگی و با آیکونِ پرمیوم (میدل‌ویرِ خروجی خودکار ارتقا می‌دهد).
   دکمه‌های اطلاعاتیِ چت‌محور (برترین/مالک/ساعت/لیست بازی) واقعاً اجرا می‌شوند؛ موارد
   نیازمندِ ورودی/ریپلای (افزایش/برداشت/انتقال) راهنمای دقیق نشان می‌دهند.

باز کردن: «منو» یا «کیبورد» یا «پنل کاربری» در گروه.
"""
from __future__ import annotations

import importlib
import logging

from aiogram import F, Router, Bot
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton as Btn,
)

logger = logging.getLogger(__name__)

router = Router(name="group_menu")
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

OPEN_TRIGGERS = {"منو", "منو کاربری", "کیبورد", "پنل کاربری", "دکمه ها", "دکمه‌ها", "دکمه"}
CLOSE_TRIGGERS = {"بستن کیبورد", "❌ بستن کیبورد", "بستن منو", "حذف کیبورد"}


# ─── نگاشتِ لیبلِ دکمه → دستورِ موجود ───────────────────────────────────────
# label → (module, function_name, wants_bot)
_ACTIONS: dict[str, tuple[str, str, bool]] = {
    # اطلاعات شخصی/رقابت
    "📊 آمار من": ("main_group", "cmd_stats", True),
    "🏆 برترین": ("main_group", "cmd_top_users", True),
    "🏅 لیگ من": ("main_group", "cmd_league_me", True),
    # بازی‌ها
    "🎯 دارت": ("games", "cmd_dart", True),
    "🏀 بسکتبال": ("games", "cmd_basketball", True),
    "⚽ پنالتی": ("games", "cmd_penalty", True),
    "🎳 بولینگ": ("games", "cmd_bowling", True),
    "🎰 اسلات": ("games", "cmd_slots", True),
    "🪙 سکه": ("games", "cmd_coin", True),
    "✂️ سنگ کاغذ قیچی": ("games", "cmd_rps", True),
    "🍀 شانس": ("games", "cmd_luck", True),
    "🃏 چالش": ("games", "cmd_challenge", False),
    # سرگرمی
    "😂 جوک": ("games", "cmd_joke", False),
    "🔮 فال": ("games", "cmd_fortune", False),
    "🧠 معما": ("games", "cmd_riddle", False),
    "💡 دانستنی": ("games", "cmd_fact", False),
    "🗣 سخن": ("games", "cmd_wisdom", False),
    "👤 شخصیت": ("games", "cmd_personality", False),
    "⚖️ دو راهی": ("games", "cmd_dilemma", False),
    # ابزار
    "🎮 بازی‌ها": ("main_group", "cmd_games_list", False),
    "👑 مالک": ("main_group", "cmd_owner_info", True),
    "🕐 ساعت": ("main_group", "cmd_time", False),
    "🔒 قفل‌ها": ("main_group", "cmd_locks_inline_panel", False),
}

_MODULES = {
    "games": "bot.handlers.games",
    "main_group": "bot.handlers.main_group",
}

# چیدمانِ کیبوردِ Reply
_REPLY_LAYOUT: list[list[str]] = [
    ["📊 آمار من", "🏆 برترین", "🏅 لیگ من"],
    ["🎯 دارت", "🏀 بسکتبال", "⚽ پنالتی"],
    ["🎳 بولینگ", "🎰 اسلات", "🪙 سکه"],
    ["✂️ سنگ کاغذ قیچی", "🍀 شانس", "🃏 چالش"],
    ["😂 جوک", "🔮 فال", "🧠 معما"],
    ["💡 دانستنی", "🗣 سخن", "👤 شخصیت"],
    ["🎮 بازی‌ها", "👑 مالک", "🕐 ساعت"],
    ["🔒 قفل‌ها", "❌ بستن کیبورد"],
]


def _reply_kb() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=lbl) for lbl in row] for row in _REPLY_LAYOUT]
    return ReplyKeyboardMarkup(
        keyboard=rows, resize_keyboard=True, is_persistent=True,
        input_field_placeholder="یک دکمه را انتخاب کن…",
    )


# ─── منوی شیشه‌ای (inline) — ایموجیِ ابتدایی خودکار پرمیوم می‌شود ─────────────
def _inline_home() -> InlineKeyboardMarkup:
    from bot.site_config import get_link_directory_url, get_support_url
    from bot import cache
    channel = cache.SITE_CONFIG.get("channel_url") or "https://t.me/TasinoBot"
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="🎮 بازی‌ها", callback_data="gm:cat:games"),
         Btn(text="🎉 سرگرمی", callback_data="gm:cat:fun")],
        [Btn(text="💰 مالی", callback_data="gm:cat:money"),
         Btn(text="🏆 برترین", callback_data="gm:act:top")],
        [Btn(text="👑 مالک", callback_data="gm:act:owner"),
         Btn(text="🕐 ساعت", callback_data="gm:act:time"),
         Btn(text="🎮 لیست بازی‌ها", callback_data="gm:act:games")],
        [Btn(text="📣 کانال", url=channel),
         Btn(text="💬 پشتیبانی", url=get_support_url())],
        [Btn(text="✖️ بستن", callback_data="gm:close")],
    ])


def _inline_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[Btn(text="🔙 بازگشت", callback_data="gm:home")]])


_CAT_TEXT = {
    "games": (
        "🎮 <b>بازی‌ها</b>\n━━━━━━━━━━━━━━━━━━\n"
        "برای بازی، از دکمه‌های زیرِ کیبورد استفاده کن یا نامش را بفرست:\n\n"
        "🎯 دارت · 🏀 بسکتبال · ⚽ پنالتی · 🎳 بولینگ\n"
        "🎰 اسلات · 🪙 سکه · ✂️ سنگ کاغذ قیچی · 🍀 شانس · 🃏 چالش"
    ),
    "fun": (
        "🎉 <b>سرگرمی</b>\n━━━━━━━━━━━━━━━━━━\n"
        "😂 جوک · 🔮 فال · 🧠 معما · 💡 دانستنی\n🗣 سخن · 👤 شخصیت · ⚖️ دو راهی"
    ),
    "money": (
        "💰 <b>مالی</b>\n━━━━━━━━━━━━━━━━━━\n"
        "📊 «آمار من» → موجودی و آمار تو\n"
        "🏅 «لیگ من» → رتبه و شرط‌بندیِ لیگ\n\n"
        "دستورهای مدیریتی (روی پیامِ کاربر ریپلای کن):\n"
        "<code>افزایش 1000</code> · <code>کاهش 1000</code>\n"
        "<code>انتقال 1000</code> (ریپلای) → انتقال موجودی"
    ),
}


# ─── باز/بستن ──────────────────────────────────────────────────────────────
@router.message(F.text.func(lambda t: t and t.strip() in OPEN_TRIGGERS))
async def open_menu(message: Message):
    await message.answer(
        "🎛 <b>منوی کاربری</b>\n"
        "از دکمه‌های زیرِ کیبورد برای اجرای سریعِ دستورها استفاده کن.\n"
        "منوی رنگیِ زیر هم برای دسترسیِ سریع است.",
        reply_markup=_reply_kb(), parse_mode="HTML",
    )
    await message.answer("📋 دسترسی سریع:", reply_markup=_inline_home(), parse_mode="HTML")


@router.message(F.text.func(lambda t: t and t.strip() in CLOSE_TRIGGERS))
async def close_menu(message: Message):
    await message.answer("کیبورد بسته شد.", reply_markup=ReplyKeyboardRemove())


# ─── اجرای دستور از دکمه‌ی Reply ────────────────────────────────────────────
@router.message(F.text.func(lambda t: t and t.strip() in _ACTIONS))
async def run_action(message: Message, bot: Bot):
    module, fn_name, wants_bot = _ACTIONS[message.text.strip()]
    try:
        mod = importlib.import_module(_MODULES[module])
        fn = getattr(mod, fn_name)
    except Exception:
        logger.exception("group_menu: import %s.%s failed", module, fn_name)
        return
    try:
        if wants_bot:
            await fn(message, bot)
        else:
            await fn(message)
    except Exception:
        logger.exception("group_menu: run %s failed", fn_name)


# ─── callbackهای منوی شیشه‌ای ───────────────────────────────────────────────
@router.callback_query(F.data == "gm:home")
async def cb_home(cq: CallbackQuery):
    try:
        await cq.message.edit_text("📋 دسترسی سریع:", reply_markup=_inline_home(), parse_mode="HTML")
    except Exception:
        pass
    await cq.answer()


@router.callback_query(F.data == "gm:close")
async def cb_close(cq: CallbackQuery):
    try:
        await cq.message.delete()
    except Exception:
        pass
    await cq.answer()


@router.callback_query(F.data.startswith("gm:cat:"))
async def cb_cat(cq: CallbackQuery):
    cat = cq.data.split(":", 2)[2]
    text = _CAT_TEXT.get(cat, "…")
    try:
        await cq.message.edit_text(text, reply_markup=_inline_back(), parse_mode="HTML")
    except Exception:
        pass
    await cq.answer()


# اکشن‌های چت‌محورِ امن (بدون نیاز به هویتِ کاربر) → دستورِ واقعی اجرا می‌شود
_CB_ACTIONS = {
    "top": ("main_group", "cmd_top_users", True),
    "owner": ("main_group", "cmd_owner_info", True),
    "time": ("main_group", "cmd_time", False),
    "games": ("main_group", "cmd_games_list", False),
}


@router.callback_query(F.data.startswith("gm:act:"))
async def cb_act(cq: CallbackQuery, bot: Bot):
    act = cq.data.split(":", 2)[2]
    spec = _CB_ACTIONS.get(act)
    if not spec:
        return await cq.answer()
    module, fn_name, wants_bot = spec
    try:
        mod = importlib.import_module(_MODULES[module])
        fn = getattr(mod, fn_name)
        if wants_bot:
            await fn(cq.message, bot)
        else:
            await fn(cq.message)
        await cq.answer()
    except Exception:
        logger.exception("group_menu cb_act %s failed", act)
        await cq.answer("خطا در اجرا", show_alert=False)
