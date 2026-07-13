"""تنظیمات سراسری ربات (لینکدونی، پشتیبانی، …)."""
from __future__ import annotations

from asgiref.sync import sync_to_async

from bot import cache


def apply_site_config_cache(data: dict | None = None) -> None:
    if not data:
        data = {}
    emoji_ids = data.get("premium_emoji_ids") or {}
    if not isinstance(emoji_ids, dict):
        emoji_ids = {}
    cleaned = {}
    for k, v in emoji_ids.items():
        if not k:
            continue
        key = str(k).lower()
        if isinstance(v, dict):
            eid = str(v.get("id") or v.get("emoji_id") or "").strip()
            alt = str(v.get("alt") or v.get("fallback") or "").strip()
            if eid.isdigit():
                cleaned[key] = {"id": eid, **({"alt": alt} if alt else {})}
        else:
            eid = str(v).strip()
            if eid.isdigit():
                cleaned[key] = eid

    dice_themes = data.get("dice_themes") or {}
    if not isinstance(dice_themes, dict):
        dice_themes = {}
    cleaned_themes = {}
    for k, v in dice_themes.items():
        try:
            tid = str(int(k))
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict) and v:
            cleaned_themes[tid] = v

    cache.SITE_CONFIG.update({
        "bot_enabled": bool(data.get("bot_enabled", True)),
        "link_directory_url": data.get("link_directory_url") or "https://t.me/TasinoBot",
        "link_directory_title": data.get("link_directory_title") or "🔥 بزرگترین لینکدونی",
        "support_url": data.get("support_url") or "https://t.me/Spayers",
        "support_title": data.get("support_title") or "گروه پشتیبانی",
        "channel_url": data.get("channel_url") or "https://t.me/TasinoBot",
        "premium_emoji_ids": cleaned,
        "dice_themes": cleaned_themes,
    })


def is_bot_globally_enabled() -> bool:
    return bool(cache.SITE_CONFIG.get("bot_enabled", True))


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
    data = _site_snapshot(cfg)
    apply_site_config_cache(data)
    return data


def _site_snapshot(cfg) -> dict:
    return {
        "bot_enabled": bool(getattr(cfg, "bot_enabled", True)),
        "link_directory_url": cfg.link_directory_url,
        "link_directory_title": cfg.link_directory_title,
        "support_url": cfg.support_url,
        "support_title": cfg.support_title,
        "channel_url": cfg.channel_url or "",
        "premium_emoji_ids": getattr(cfg, "premium_emoji_ids", None) or {},
        "dice_themes": getattr(cfg, "dice_themes", None) or {},
    }


@sync_to_async
def db_set_bot_enabled(enabled: bool) -> dict:
    from bot_setting.models import BotSiteConfig
    cfg = BotSiteConfig.get_singleton()
    cfg.bot_enabled = bool(enabled)
    cfg.save(update_fields=["bot_enabled", "updated_at"])
    data = _site_snapshot(cfg)
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
    data = _site_snapshot(cfg)
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
    data = _site_snapshot(cfg)
    apply_site_config_cache(data)
    return data


@sync_to_async
def db_set_premium_emoji(name: str, emoji_id: str, alt: str | None = None) -> dict:
    from bot_setting.models import BotSiteConfig
    key = (name or "").strip().lower()
    eid = (emoji_id or "").strip()
    cfg = BotSiteConfig.get_singleton()
    ids = dict(cfg.premium_emoji_ids or {})
    if key and eid.isdigit():
        entry: dict = {"id": eid}
        if alt and str(alt).strip() and str(alt).strip() != "?":
            entry["alt"] = str(alt).strip()
        ids[key] = entry
    cfg.premium_emoji_ids = ids
    cfg.save(update_fields=["premium_emoji_ids", "updated_at"])
    data = _site_snapshot(cfg)
    apply_site_config_cache(data)
    return data


@sync_to_async
def db_clear_premium_emoji(name: str) -> dict:
    from bot_setting.models import BotSiteConfig
    key = (name or "").strip().lower()
    cfg = BotSiteConfig.get_singleton()
    ids = dict(cfg.premium_emoji_ids or {})
    ids.pop(key, None)
    cfg.premium_emoji_ids = ids
    cfg.save(update_fields=["premium_emoji_ids", "updated_at"])
    data = _site_snapshot(cfg)
    apply_site_config_cache(data)
    return data


@sync_to_async
def db_import_premium_emojis(entries: dict, replace: bool = False) -> dict:
    """
    entries: {key: {id, alt?} | "id"}
    replace=True → کل دیکشنری DB عوض می‌شود.
    """
    from bot_setting.models import BotSiteConfig
    cfg = BotSiteConfig.get_singleton()
    ids = {} if replace else dict(cfg.premium_emoji_ids or {})
    for k, v in (entries or {}).items():
        key = str(k).strip().lower()
        if not key:
            continue
        if isinstance(v, dict):
            eid = str(v.get("id") or "").strip()
            alt = str(v.get("alt") or "").strip()
            if eid.isdigit():
                item = {"id": eid}
                if alt and alt != "?":
                    item["alt"] = alt
                ids[key] = item
        else:
            eid = str(v).strip()
            if eid.isdigit():
                ids[key] = {"id": eid}
    cfg.premium_emoji_ids = ids
    cfg.save(update_fields=["premium_emoji_ids", "updated_at"])
    data = _site_snapshot(cfg)
    apply_site_config_cache(data)
    return data


@sync_to_async
def db_set_dice_theme_field(theme_id: int, field: str, value: str) -> dict:
    """تنظیم یک فیلد تم (name/single_header/.../face_N)."""
    from bot_setting.models import BotSiteConfig
    from bot.dice_themes import FACE_KEYS, default_new_theme, BUILTIN_THEMES

    tid = str(int(theme_id))
    cfg = BotSiteConfig.get_singleton()
    themes = dict(cfg.dice_themes or {})
    patch = dict(themes.get(tid) or {})

    # اگر تم builtin نیست و پچ خالی است، پایه کامل بساز
    if int(theme_id) not in BUILTIN_THEMES and not patch:
        patch = default_new_theme(int(theme_id))

    if field.startswith("face_"):
        n = int(field.split("_", 1)[1])
        if n not in FACE_KEYS:
            raise ValueError("face invalid")
        faces = dict(patch.get("faces") or {})
        faces[str(n)] = value
        patch["faces"] = faces
    else:
        patch[field] = value

    themes[tid] = patch
    cfg.dice_themes = themes
    cfg.save(update_fields=["dice_themes", "updated_at"])
    data = _site_snapshot(cfg)
    apply_site_config_cache(data)
    return data


@sync_to_async
def db_reset_dice_theme(theme_id: int) -> dict:
    """حذف override تم (برگشت به پیش‌فرض builtin یا حذف تم سفارشی)."""
    from bot_setting.models import BotSiteConfig
    tid = str(int(theme_id))
    cfg = BotSiteConfig.get_singleton()
    themes = dict(cfg.dice_themes or {})
    themes.pop(tid, None)
    cfg.dice_themes = themes
    cfg.save(update_fields=["dice_themes", "updated_at"])
    data = _site_snapshot(cfg)
    apply_site_config_cache(data)
    return data


@sync_to_async
def db_create_dice_theme(theme_id: int | None = None, patch: dict | None = None) -> dict:
    from bot_setting.models import BotSiteConfig
    from bot.dice_themes import default_new_theme, next_custom_theme_id

    tid_int = int(theme_id) if theme_id else next_custom_theme_id()
    tid = str(tid_int)
    cfg = BotSiteConfig.get_singleton()
    themes = dict(cfg.dice_themes or {})
    themes[tid] = patch or default_new_theme(tid_int)
    cfg.dice_themes = themes
    cfg.save(update_fields=["dice_themes", "updated_at"])
    data = _site_snapshot(cfg)
    apply_site_config_cache(data)
    data["_created_theme_id"] = tid_int
    return data


@sync_to_async
def db_import_dice_themes(entries: dict, replace: bool = False) -> dict:
    from bot_setting.models import BotSiteConfig
    from bot.dice_themes import _clean_theme_patch

    cfg = BotSiteConfig.get_singleton()
    themes = {} if replace else dict(cfg.dice_themes or {})
    for k, v in (entries or {}).items():
        try:
            tid = str(int(k))
        except (TypeError, ValueError):
            continue
        patch = _clean_theme_patch(v if isinstance(v, dict) else {})
        if not patch:
            continue
        if tid in themes and not replace:
            merged = dict(themes[tid])
            faces = dict(merged.get("faces") or {})
            faces.update(patch.get("faces") or {})
            merged.update({kk: vv for kk, vv in patch.items() if kk != "faces"})
            if faces:
                merged["faces"] = faces
            themes[tid] = merged
        else:
            themes[tid] = patch
    cfg.dice_themes = themes
    cfg.save(update_fields=["dice_themes", "updated_at"])
    data = _site_snapshot(cfg)
    apply_site_config_cache(data)
    return data


def site_config_status_text() -> str:
    c = cache.SITE_CONFIG
    bot_state = "🟢 روشن" if c.get("bot_enabled", True) else "⚫ خاموش"
    return (
        "🔗 <b>تنظیمات لینک‌های پیوی</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ ربات سراسری: <b>{bot_state}</b>\n\n"
        f"🔥 لینکدونی:\n<code>{c.get('link_directory_url')}</code>\n"
        f"متن دکمه: <b>{c.get('link_directory_title')}</b>\n\n"
        f"💬 پشتیبانی:\n<code>{c.get('support_url')}</code>\n"
        f"عنوان: <b>{c.get('support_title')}</b>\n\n"
        "📌 تغییر لینکدونی:\n"
        "<code>تنظیم لینکدونی https://t.me/xxx</code>\n"
        "یا دکمه زیر را بزنید."
    )
