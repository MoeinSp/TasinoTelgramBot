"""
خودکارسازی آیکون ایموجی پرمیوم دکمه‌ها.

برای هر دکمه‌ای که هنوز آیکون پرمیوم ندارد، یک ایموجیِ مناسب را از *ست‌های پرمیومِ
خودِ مالک* (کشف‌شده از روی overrideهای موجود) پیدا و ست می‌کند.

پیش‌نیاز: مالک باید حداقل یک دکمه را دستی از پنل تنظیم کرده باشد (تا ست‌هایش کشف شوند).

    python manage.py assign_premium_button_emojis          # فقط دکمه‌های بدون پرمیوم
    python manage.py assign_premium_button_emojis --force   # بازنویسی همه

توجه: کش پراسسِ بات جدا از این پراسس است؛ بعد از اجرا بات را ری‌استارت کنید:
    docker compose restart bot
"""
from __future__ import annotations

import os

import requests
from django.core.management.base import BaseCommand

from bot.button_emoji import BUTTON_EMOJI_DEFS, PREFERRED

VS16 = "️"  # variation selector


def _strip_vs(emoji: str) -> str:
    return (emoji or "").replace(VS16, "")


class Command(BaseCommand):
    help = "آیکون ایموجی پرمیوم را برای دکمه‌های بدون‌پرمیوم به‌صورت خودکار ست می‌کند."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="دکمه‌هایی که قبلاً پرمیوم دارند را هم بازنویسی کن.",
        )

    # ─── Bot API ───────────────────────────────────────────────────────────
    def _token(self) -> str:
        token = (os.getenv("BOT_TOKEN", "") or "").strip().strip('"').strip("'")
        if not token:
            raise SystemExit("BOT_TOKEN تنظیم نشده.")
        return token

    def _api(self, method: str, **params):
        url = f"https://api.telegram.org/bot{self._token()}/{method}"
        resp = requests.post(url, json=params, timeout=30)
        data = resp.json()
        if not data.get("ok"):
            raise SystemExit(f"Bot API {method} خطا: {data.get('description')}")
        return data["result"]

    def handle(self, *args, **opts):
        from bot_setting.models import ButtonEmojiOverride

        force = bool(opts.get("force"))
        overrides = {o.key: o for o in ButtonEmojiOverride.objects.all()}
        if not overrides:
            self.stderr.write(
                "هیچ override‌ای وجود ندارد. اول حداقل یک دکمه را از پنل «ایموجی دکمه‌ها» "
                "دستی تنظیم کن تا ست‌های پرمیومِ مالک کشف شوند."
            )
            return

        ids = [o.custom_emoji_id for o in overrides.values()]

        # کشف ست‌ها از روی idهای موجود
        set_names: set[str] = set()
        stickers = self._api("getCustomEmojiStickers", custom_emoji_ids=ids)
        for s in stickers:
            name = s.get("set_name")
            if name:
                set_names.add(name)
        if not set_names:
            self.stderr.write("هیچ ست پرمیومی از روی overrideها کشف نشد.")
            return
        self.stdout.write(f"ست‌های کشف‌شده ({len(set_names)}): {', '.join(sorted(set_names))}")

        # base_emoji → custom_emoji_id
        emoji_map: dict[str, str] = {}
        for name in sorted(set_names):
            result = self._api("getStickerSet", name=name)
            for s in result.get("stickers", []):
                emoji = s.get("emoji") or ""
                cid = s.get("custom_emoji_id")
                if not emoji or not cid:
                    continue
                emoji_map.setdefault(emoji, cid)
                emoji_map.setdefault(_strip_vs(emoji), cid)
        self.stdout.write(f"مجموع ایموجی‌های در دسترس: {len(emoji_map)}")

        assigned, skipped, unmatched = [], [], []
        for key, (label, fallback, _cat) in BUTTON_EMOJI_DEFS.items():
            if key in overrides and not force:
                skipped.append(key)
                continue
            want = PREFERRED.get(key, fallback)
            cid = emoji_map.get(want) or emoji_map.get(_strip_vs(want))
            if not cid:
                unmatched.append((key, want))
                continue
            ButtonEmojiOverride.objects.update_or_create(
                key=key,
                defaults={"custom_emoji_id": cid, "placeholder": want[:16]},
            )
            assigned.append((key, want))

        # ─── گزارش ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(f"\nست‌شده: {len(assigned)}"))
        for key, want in assigned:
            self.stdout.write(f"  ✅ {key} → {want}")
        if skipped:
            self.stdout.write(f"\nرد شد (قبلاً پرمیوم داشت، بدون --force): {len(skipped)}")
        if unmatched:
            self.stdout.write(self.style.WARNING(f"\nبدون تطابق: {len(unmatched)}"))
            for key, want in unmatched:
                self.stdout.write(f"  ⚠️ {key} (دنبال {want} بود؛ در ست‌های مالک نبود)")

        self.stdout.write(self.style.NOTICE(
            "\nبرای اعمال در بات در حال اجرا: docker compose restart bot"
        ))
