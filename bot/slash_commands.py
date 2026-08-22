"""
اسلش‌کامندهای BotFather → هندلرهای موجود.

بات با متنِ فارسی کار می‌کند؛ این روتر همان قابلیت‌ها را زیرِ اسلش‌کامندهای لاتین هم
در دسترس می‌گذارد تا منوی BotFather (دکمه‌ی «≡» و اتوکاملِ «/») واقعاً کار کند.
فقط در گروه/سوپرگروه فعال است و هندلرهای موجود را با «هویتِ خودِ کاربر» صدا می‌زند
(پیامِ اسلش، پیامِ واقعیِ کاربر است — نیازی به پروکسی نیست، جز /balance که به متنِ
«موجودی» نیاز دارد). هیچ فایلِ دیگری تغییر نمی‌کند.
"""
from __future__ import annotations

import importlib
import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)

router = Router(name="slash_commands")
router.message.filter(lambda m: m.chat and m.chat.type in {"group", "supergroup"})

_MODULES = {
    "games": "bot.handlers.games",
    "main_group": "bot.handlers.main_group",
}

# اسلش‌کامند → (module, function, wants_bot)
_MAP: dict[str, tuple[str, str, bool]] = {
    # بازی‌ها
    "games":      ("main_group", "cmd_games_list", False),
    "basketball": ("games", "cmd_basketball", True),
    "penalty":    ("games", "cmd_penalty", True),
    "bowling":    ("games", "cmd_bowling", True),
    "dart":       ("games", "cmd_dart", True),
    "slots":      ("games", "cmd_slots", True),
    "coin":       ("games", "cmd_coin", True),
    "rps":        ("games", "cmd_rps", True),
    "luck":       ("games", "cmd_luck", True),
    # سرگرمی
    "joke":        ("games", "cmd_joke", False),
    "fortune":     ("games", "cmd_fortune", False),
    "riddle":      ("games", "cmd_riddle", False),
    "fact":        ("games", "cmd_fact", False),
    "wisdom":      ("games", "cmd_wisdom", False),
    "personality": ("games", "cmd_personality", False),
    "dilemma":     ("games", "cmd_dilemma", False),
    "challenge":   ("games", "cmd_challenge", False),
    # حساب و رقابت
    "stats":  ("main_group", "cmd_stats", True),
    "top":    ("main_group", "cmd_top_users", True),
    "league": ("main_group", "cmd_league_me", True),
    # ابزار
    "time":  ("main_group", "cmd_time", False),
    "owner": ("main_group", "cmd_owner_info", True),
    "locks": ("main_group", "cmd_locks_inline_panel", False),
    "rules": ("main_group", "cmd_show_rules", False),
    "help":  ("main_group", "cmd_help", False),
}


def _make(module: str, fn_name: str, wants_bot: bool):
    async def _handler(message: Message, bot: Bot):
        try:
            fn = getattr(importlib.import_module(_MODULES[module]), fn_name)
        except Exception:
            logger.exception("slash: import %s.%s failed", module, fn_name)
            return
        try:
            await (fn(message, bot) if wants_bot else fn(message))
        except Exception:
            logger.exception("slash: run %s failed", fn_name)
    return _handler


for _cmd, (_mod, _fn, _wb) in _MAP.items():
    router.message.register(_make(_mod, _fn, _wb), Command(_cmd))


# /balance — هندلر به متنِ «موجودی» نیاز دارد → یک پروکسی با همان متن می‌سازیم
@router.message(Command("balance"))
async def cmd_slash_balance(message: Message, bot: Bot):
    try:
        from bot.handlers.main_group import cmd_balance
        proxy = message.model_copy(update={"text": "موجودی"})
        proxy.as_(bot)
        await cmd_balance(proxy, bot)
    except Exception:
        logger.exception("slash: /balance failed")


# /menu — منوی کاربریِ گروه (Reply + inline)
@router.message(Command("menu"))
async def cmd_slash_menu(message: Message):
    try:
        from bot.group_menu import open_menu
        await open_menu(message)
    except Exception:
        logger.exception("slash: /menu failed")
