"""تنظیمات سراسری ربات (لینکدونی، پشتیبانی، …)."""
from __future__ import annotations

from asgiref.sync import sync_to_async

from bot import cache


def apply_site_config_cache(data: dict | None = None) -> None:
    if not data:
        data = {}
    cache.SITE_CONFIG.update({
        "link_directory_url": data.get("link_directory_url") or "https://t.me/TasinoBot",
        "link_directory_title": data.get("link_directory_title") or "🔥 بزرگترین لینکدونی",
        "support_url": data.get("support_url") or "https://t.me/Spayers",
        "support_title": data.get("support_title") or "گروه پشتیبانی",
        "channel_url": data.get("channel_url") or "https://t.me/TasinoBot",
    })


def get_link_directory_url() -> str:
    return cache.SITE_CONFIG.get("link_directory_url") or "https://t.me/TasinoBot"


def get_link_directory_title() -> str:
    return cache.SITE_CONFIG.get("link_directory_title") or "🔥 بزرگترین لینکدونی"


def get_support_url() -> str:
    return cache.SITE_CONFIG.get("support_url") or "https://t.me/Spayers"


def get_support_title() -> str:
    return cache.SITE_CONFIG.get("support_title") or "گروه پشتیبانی"


@sync_to_async
def load_site_config_from_db() -> dict:
    from bot_setting.models import BotSiteConfig
    cfg = BotSiteConfig.get_singleton()
    data = {
        "link_directory_url": cfg.link_directory_url,
        "link_directory_title": cfg.link_directory_title,
        "support_url": cfg.support_url,
        "support_title": cfg.support_title,
        "channel_url": cfg.channel_url or "",
    }
    apply_site_config_cache(data)
    return data


@sync_to_async
def db_set_link_directory(url: str, title: str | None = None) -> dict:
    from bot_setting.models import BotSiteConfig
    cfg = BotSiteConfig.get_singleton()
    cfg.link_directory_url = url.strip()
    if title is not None and title.strip():
        cfg.link_directory_title = title.strip()[:64]
    cfg.save()
    data = {
        "link_directory_url": cfg.link_directory_url,
        "link_directory_title": cfg.link_directory_title,
        "support_url": cfg.support_url,
        "support_title": cfg.support_title,
        "channel_url": cfg.channel_url or "",
    }
    apply_site_config_cache(data)
    return data


@sync_to_async
def db_set_support_url(url: str, title: str | None = None) -> dict:
    from bot_setting.models import BotSiteConfig
    cfg = BotSiteConfig.get_singleton()
    cfg.support_url = url.strip()
    if title is not None and title.strip():
        cfg.support_title = title.strip()[:64]
    cfg.save()
    data = {
        "link_directory_url": cfg.link_directory_url,
        "link_directory_title": cfg.link_directory_title,
        "support_url": cfg.support_url,
        "support_title": cfg.support_title,
        "channel_url": cfg.channel_url or "",
    }
    apply_site_config_cache(data)
    return data


def site_config_status_text() -> str:
    c = cache.SITE_CONFIG
    return (
        "🔗 <b>تنظیمات لینک‌های پیوی</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔥 لینکدونی:\n<code>{c.get('link_directory_url')}</code>\n"
        f"متن دکمه: <b>{c.get('link_directory_title')}</b>\n\n"
        f"💬 پشتیبانی:\n<code>{c.get('support_url')}</code>\n"
        f"عنوان: <b>{c.get('support_title')}</b>\n\n"
        "📌 تغییر لینکدونی:\n"
        "<code>تنظیم لینکدونی https://t.me/xxx</code>\n"
        "یا دکمه زیر را بزنید."
    )
