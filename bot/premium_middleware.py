"""
میدل‌ویرِ سشنِ خروجی — همه‌ی فراخوانی‌های Bot API را قبل از ارسال ارتقا می‌دهد.

روی هر متد که text/caption (با parse_mode=HTML) یا reply_markup اینلاین دارد:
  - متن/کپشنِ HTML → ایموجی پرمیوم
  - دکمه‌های اینلاین → icon_custom_emoji_id

اگر ارسالِ ارتقایافته خطا داد، فیلدها به حالتِ اصلی برمی‌گردند و دوباره ارسال می‌شود،
تا هیچ پیامی به‌خاطرِ ارتقا از دست نرود.
"""
from __future__ import annotations

import logging

from aiogram.client.session.middlewares.base import BaseRequestMiddleware

from bot import premium_text as pt

logger = logging.getLogger(__name__)

# متدهایی که reply_markup اینلاین می‌گیرند و متن/کپشن دارند از طریق getattr کشف می‌شوند.


class PremiumEmojiMiddleware(BaseRequestMiddleware):
    @staticmethod
    def _resolve_mode(bot, method) -> str:
        """parse_mode مؤثر: 'HTML' | 'MARKDOWN'/'MARKDOWNV2' | '' (ساده)."""
        raw = getattr(method, "parse_mode", None)
        # aiogram وقتی parse_mode ست نشده یک sentinel از نوع Default می‌گذارد؛
        # مقدارِ واقعی از bot.default می‌آید (این بات پیش‌فرض None دارد → ساده).
        try:
            from aiogram.client.default import Default
            if isinstance(raw, Default):
                raw = getattr(getattr(bot, "default", None), "parse_mode", None)
        except Exception:
            pass
        if isinstance(raw, str):
            return raw.upper()
        return ""

    async def __call__(self, make_request, bot, method):
        if pt.map_size() == 0:
            return await make_request(bot, method)

        original: dict[str, object] = {}
        changed_markup = False
        try:
            mode = self._resolve_mode(bot, method)  # "HTML" | "MARKDOWN…" | "" (plain)

            # متن/کپشن
            if mode == "HTML":
                for field in ("text", "caption"):
                    val = getattr(method, field, None)
                    if isinstance(val, str) and val:
                        new = pt.upgrade_html_text(val)
                        if new != val:
                            original[field] = val
                            setattr(method, field, new)
            elif mode == "":  # متنِ ساده → escape + HTML + ارتقا
                upgraded_any = False
                for field in ("text", "caption"):
                    val = getattr(method, field, None)
                    if isinstance(val, str) and val:
                        new = pt.upgrade_plain_text(val)
                        if new is not None and new != val:
                            original[field] = val
                            setattr(method, field, new)
                            upgraded_any = True
                if upgraded_any and hasattr(method, "parse_mode"):
                    original["parse_mode"] = getattr(method, "parse_mode", None)
                    method.parse_mode = "HTML"
            # MARKDOWN* → متن دست‌نخورده (فقط دکمه‌ها ارتقا می‌یابند)

            # دکمه‌های اینلاین
            markup = getattr(method, "reply_markup", None)
            if markup is not None and getattr(markup, "inline_keyboard", None):
                # snapshot سبک برای بازگردانی
                snapshot = [
                    [(b, b.text, getattr(b, "icon_custom_emoji_id", None)) for b in row]
                    for row in markup.inline_keyboard
                ]
                if pt.upgrade_inline_markup(markup):
                    changed_markup = True
                    original["_markup_snapshot"] = snapshot
        except Exception as exc:
            logger.debug("premium upgrade skipped: %s", exc)
            original.clear()
            changed_markup = False

        if not original and not changed_markup:
            return await make_request(bot, method)

        try:
            return await make_request(bot, method)
        except Exception as exc:
            # بازگردانی و ارسالِ نسخه‌ی اصلی
            logger.warning("premium-upgraded send failed (%s); retrying original", exc)
            try:
                for field, val in original.items():
                    if field == "_markup_snapshot":
                        for row in val:
                            for btn, txt, icon in row:
                                btn.text = txt
                                btn.icon_custom_emoji_id = icon
                    else:
                        setattr(method, field, val)
            except Exception:
                logger.exception("failed to restore original method; re-raising")
                raise
            return await make_request(bot, method)
