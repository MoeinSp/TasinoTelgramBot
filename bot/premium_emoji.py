"""
ایموجی پرمیوم (custom emoji) برای متن‌های HTML ربات.

پیش‌نیاز تلگرام:
  صاحب ربات باید Premium داشته باشد (Bot API 9.4+).

منبع ID:
  ۱) دیتابیس / پنل سازنده (اولویت بالاتر)
  ۲) env: PREMIUM_EMOJI_IDS=rose:5287...,dice:123...

گرفتن ID:
  در پیوی فقط ایموجی پرمیوم بفرست، یا /emoji_id
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

from aiogram.types import Message


DEFAULTS: dict[str, str] = {
    "rose": "🌹",
    "star": "⭐",
    "dice": "🎲",
    "check": "✅",
    "shield": "🛡",
    "fire": "🔥",
    "crown": "👑",
    "money": "💰",
    "gear": "⚙️",
    "lock": "🔐",
    "users": "👥",
    "spark": "✨",
    "rocket": "🚀",
    "pin": "📌",
    "bulb": "💡",
    "wave": "👋",
    "heart": "❤️",
}

# اسلات‌های مهم پنل — فقط محل استفاده؛ خود ایموجی کاملاً دلخواه است
EMOJI_SLOTS: list[tuple[str, str]] = [
    ("dice", "تاس / بازی (دلخواه)"),
    ("rose", "خوش‌آمد (دلخواه)"),
    ("wave", "سلام (دلخواه)"),
    ("heart", "حمایت (دلخواه)"),
    ("spark", "ویژگی‌ها (دلخواه)"),
    ("check", "لیست / تیک (دلخواه)"),
    ("gear", "تنظیمات (دلخواه)"),
    ("money", "مالی (دلخواه)"),
    ("rocket", "نصب (دلخواه)"),
    ("pin", "نکته (دلخواه)"),
    ("star", "منو (دلخواه)"),
    ("shield", "امنیت (دلخواه)"),
    ("users", "اعضا (دلخواه)"),
    ("bulb", "راهنما (دلخواه)"),
    ("crown", "مالک (دلخواه)"),
    ("fire", "ویژه (دلخواه)"),
    ("lock", "قفل (دلخواه)"),
]

PAGE_SIZE = 5


def _clean_eid(value: str) -> str:
    return (value or "").strip().strip("\"'").strip()


@lru_cache(maxsize=1)
def _env_map() -> dict[str, str]:
    raw = (os.getenv("PREMIUM_EMOJI_IDS") or "").strip().strip("\"'")
    out: dict[str, str] = {}
    if not raw or raw in (".", "...", "…"):
        return out
    if raw.startswith("{"):
        try:
            import json
            data = json.loads(raw)
            for k, v in (data or {}).items():
                eid = _clean_eid(str(v))
                if k and eid.isdigit():
                    out[str(k).strip().lower()] = eid
        except Exception:
            return out
        return out
    for part in raw.replace(";", ",").split(","):
        part = part.strip().strip("\"'")
        if not part or part in (".", "...", "…") or ":" not in part:
            continue
        key, eid = part.split(":", 1)
        key, eid = key.strip().lower(), _clean_eid(eid)
        if key and eid.isdigit():
            out[key] = eid
    return out


def _parse_entry(value) -> tuple[str | None, str | None]:
    """مقدار DB/env → (id, alt). alt اختیاری."""
    if value is None:
        return None, None
    if isinstance(value, dict):
        eid = _clean_eid(str(value.get("id") or value.get("emoji_id") or ""))
        alt = (value.get("alt") or value.get("fallback") or "").strip() or None
        return (eid if eid.isdigit() else None), alt
    eid = _clean_eid(str(value))
    return (eid if eid.isdigit() else None), None


def _db_entries() -> dict[str, dict]:
    try:
        from bot import cache
        raw = cache.SITE_CONFIG.get("premium_emoji_ids") or {}
    except Exception:
        return {}
    out: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        eid, alt = _parse_entry(v)
        if k and eid:
            item = {"id": eid}
            if alt:
                item["alt"] = alt
            out[str(k).strip().lower()] = item
    return out


def _db_map() -> dict[str, str]:
    return {k: v["id"] for k, v in _db_entries().items()}


def reload_ids() -> None:
    _env_map.cache_clear()


def _id_map() -> dict[str, str]:
    """env پایه + دیتابیس روی آن (DB اولویت دارد)."""
    out = dict(_env_map())
    out.update(_db_map())
    return out


def get_id(name: str) -> str | None:
    return _id_map().get((name or "").strip().lower())


def get_alt(name: str, fallback: str | None = None) -> str:
    key = (name or "").strip().lower()
    entry = _db_entries().get(key) or {}
    alt = (entry.get("alt") or "").strip()
    if alt:
        return alt
    if fallback is not None:
        return fallback
    return DEFAULTS.get(key, "⭐")


def pe(name: str, fallback: str | None = None) -> str:
    key = (name or "").strip().lower()
    fb = get_alt(key, fallback if fallback is not None else DEFAULTS.get(key, "⭐"))
    eid = get_id(key)
    if not eid:
        return fallback if fallback is not None else DEFAULTS.get(key, "⭐")
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'


def tg_emoji(emoji_id: str, alt: str = "⭐") -> str:
    eid = _clean_eid(str(emoji_id))
    fb = alt or "⭐"
    if not eid.isdigit():
        return fb
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'


_PLACEHOLDER_RE = re.compile(r"\{pe:([a-zA-Z0-9_]+)\}")


def render(text: str) -> str:
    if not text or "{pe:" not in text:
        return text

    def _sub(m: re.Match) -> str:
        return pe(m.group(1))

    return _PLACEHOLDER_RE.sub(_sub, text)


def configured_names() -> list[str]:
    return sorted(_id_map().keys())


def export_settings(include_env: bool = True) -> dict:
    """خروجی قابل ایمپورت (JSON)."""
    data: dict[str, dict] = {}
    if include_env:
        for k, eid in _env_map().items():
            data[k] = {"id": eid, "alt": DEFAULTS.get(k, "⭐")}
    # DB روی env می‌نشیند
    for k, entry in _db_entries().items():
        item = {"id": entry["id"]}
        if entry.get("alt"):
            item["alt"] = entry["alt"]
        else:
            item["alt"] = DEFAULTS.get(k, "⭐")
        data[k] = item
    return {
        "version": 1,
        "type": "tasino_premium_emoji",
        "premium_emoji_ids": data,
    }


def export_settings_json(pretty: bool = True) -> str:
    import json
    data = export_settings(include_env=True)
    if pretty:
        return json.dumps(data, ensure_ascii=False, indent=2)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def export_settings_env_line() -> str:
    """فرمت فشرده شبیه env (بدون alt)."""
    data = export_settings(include_env=True)["premium_emoji_ids"]
    parts = [f"{k}:{v['id']}" for k, v in sorted(data.items())]
    return "PREMIUM_EMOJI_IDS=" + ",".join(parts) if parts else "PREMIUM_EMOJI_IDS="


def parse_import_payload(text: str) -> tuple[dict[str, dict], str | None]:
    """
    پارس متن ایمپورت → ({key: {id, alt?}}, error).
    پشتیبانی: JSON کامل، دیکت ساده، rose:id,dice:id، خط PREMIUM_EMOJI_IDS=...
    """
    import json

    raw = (text or "").strip()
    if not raw:
        return {}, "متن خالی است."

    # حذف code fence
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    if raw.upper().startswith("PREMIUM_EMOJI_IDS="):
        raw = raw.split("=", 1)[1].strip().strip("\"'")

    out: dict[str, dict] = {}

    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except Exception as e:
            return {}, f"JSON نامعتبر: {e}"
        if isinstance(data, dict) and "premium_emoji_ids" in data:
            data = data.get("premium_emoji_ids") or {}
        if not isinstance(data, dict):
            return {}, "فرمت JSON باید دیکشنری باشد."
        for k, v in data.items():
            eid, alt = _parse_entry(v)
            if not k or not eid:
                continue
            item = {"id": eid}
            if alt:
                item["alt"] = alt
            out[str(k).strip().lower()] = item
        if not out:
            return {}, "هیچ ایموجی معتبری در JSON نبود."
        return out, None

    # CSV / key:id
    for part in raw.replace(";", ",").split(","):
        part = part.strip().strip("\"'")
        if not part or ":" not in part:
            continue
        key, eid = part.split(":", 1)
        key, eid = key.strip().lower(), _clean_eid(eid)
        if key and eid.isdigit():
            out[key] = {"id": eid, "alt": DEFAULTS.get(key, "⭐")}
    if not out:
        return {}, "فرمت شناخته نشد. JSON یا rose:123,dice:456 بفرست."
    return out, None


def slot_status(name: str) -> dict:
    """وضعیت یک اسلات برای پنل."""
    key = (name or "").strip().lower()
    default_fb = DEFAULTS.get(key, "⭐")
    fb = get_alt(key, default_fb)
    label = next((lbl for k, lbl in EMOJI_SLOTS if k == key), key)
    eid = get_id(key)
    in_db = key in _db_map()
    in_env = key in _env_map() and not in_db
    if eid:
        source = "db" if in_db else ("env" if in_env else "db")
        return {
            "key": key,
            "label": label,
            "fallback": fb,
            "id": eid,
            "set": True,
            "source": source,
            "preview": tg_emoji(eid, fb),
        }
    return {
        "key": key,
        "label": label,
        "fallback": default_fb,
        "id": None,
        "set": False,
        "source": None,
        "preview": default_fb,
    }


def page_count() -> int:
    n = len(EMOJI_SLOTS)
    return max(1, (n + PAGE_SIZE - 1) // PAGE_SIZE)


def slots_page(page: int) -> list[dict]:
    page = max(0, min(int(page), page_count() - 1))
    start = page * PAGE_SIZE
    chunk = EMOJI_SLOTS[start:start + PAGE_SIZE]
    return [slot_status(k) for k, _ in chunk]


def extract_custom_emoji_ids(message: Message) -> list[dict]:
    found = []
    entities = list(message.entities or []) + list(message.caption_entities or [])
    text = message.text or message.caption or ""
    for ent in entities:
        if getattr(ent, "type", None) != "custom_emoji":
            continue
        eid = getattr(ent, "custom_emoji_id", None)
        if not eid:
            continue
        try:
            chunk = text.encode("utf-16-le")
            start = ent.offset * 2
            end = (ent.offset + ent.length) * 2
            alt = chunk[start:end].decode("utf-16-le")
        except Exception:
            alt = "?"
        found.append({"id": str(eid), "alt": alt, "offset": ent.offset})
    return found


def is_custom_emoji_only_message(message: Message) -> bool:
    text = message.text or ""
    entities = [
        e for e in (message.entities or [])
        if getattr(e, "type", None) == "custom_emoji"
    ]
    if not text or not entities:
        return False
    try:
        chunk = bytearray(text.encode("utf-16-le"))
        for ent in sorted(entities, key=lambda e: e.offset, reverse=True):
            start = ent.offset * 2
            end = (ent.offset + ent.length) * 2
            del chunk[start:end]
        leftover = chunk.decode("utf-16-le")
    except Exception:
        return False
    return not leftover.strip()
