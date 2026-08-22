"""
میدل‌ویرِ سشنِ خروجی — دکمه‌های اینلاینِ زمینه‌ای را به پیام‌های گروه می‌چسباند.

روی هر ارسالِ پیامِ متنی در گروه که reply_markup ندارد، بر اساسِ متن، کیبوردِ
مناسب (کارتِ موجودی / موجودی ناکافی / نتیجه‌ی بازی) را ست می‌کند. هرگز کیبوردِ
موجود را بازنویسی نمی‌کند و در پیوی کاری انجام نمی‌دهد.

باید قبل از PremiumEmojiMiddleware ثبت شود تا ایموجیِ دکمه‌های جدید هم پرمیوم شود.
ایمنی: کلِ منطق در try/except؛ اگر خطایی رخ دهد، پیام دست‌نخورده ارسال می‌شود.
"""
from __future__ import annotations

import logging

from aiogram.client.session.middlewares.base import BaseRequestMiddleware

from bot.group_inline import detect_keyboard

logger = logging.getLogger(__name__)


def _is_group(chat_id) -> bool:
    """گروه/سوپرگروه: شناسه منفی. پیوی/کانالِ عمومی مدنظر نیست."""
    try:
        return int(chat_id) < 0
    except (TypeError, ValueError):
        return False


class GroupContextButtonsMiddleware(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        try:
            self._maybe_attach(method)
        except Exception as exc:  # pragma: no cover
            logger.debug("group buttons attach skipped: %s", exc)
        return await make_request(bot, method)

    @staticmethod
    def _maybe_attach(method) -> None:
        text = getattr(method, "text", None)
        if not isinstance(text, str) or not text:
            return
        # فقط ارسالِ پیامِ جدید (SendMessage). متدهای ادیت/... message_id دارند → رد.
        if getattr(method, "message_id", None) is not None:
            return
        if getattr(method, "reply_markup", None) is not None:
            return  # هرگز کیبوردِ موجود را دست نزن
        if not _is_group(getattr(method, "chat_id", None)):
            return
        kb = detect_keyboard(text)
        if kb is not None:
            method.reply_markup = kb
