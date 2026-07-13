"""
تم‌های تاس قابل تنظیم — ۱۵ تم پیش‌فرض + override/تم جدید از دیتابیس.

پلیس‌هولدرها در متن تم:
  {value}  — عدد تاس تکی
  {count}  — تعداد تاس جمعی
  {total}  — مجموع
  {pe:dice} / {pe:rose} / … — ایموجی پرمیوم از اسلات‌ها
"""
from __future__ import annotations

import copy
import json
from html import escape
from typing import Any

from aiogram.types import Message

# ─── ۱۵ تم پیش‌فرض (منبع حقیقت) ─────────────────────────────────────────────

BUILTIN_THEMES: dict[int, dict] = {
    1: {
        "name": "classic",
        "single_header": "<blockquote>تـاس انداخته شـد عدد ↻  : {value} {pe:dice}</blockquote>",
        "multi_header": "<blockquote>{pe:dice} تاس × {count}</blockquote>",
        "separator": "•─────✧─────•",
        "footer": "\n<blockquote>محاسبـه کـل ↻ : {total} {pe:dice}</blockquote>",
        "faces": {1: "⬤", 2: "⬤ ⬤", 3: "⬤ ⬤\n  ⬤", 4: "⬤ ⬤\n⬤ ⬤", 5: "⬤ ⬤\n  ⬤\n⬤ ⬤", 6: "⬤ ⬤\n⬤ ⬤\n⬤ ⬤"},
    },
    2: {
        "name": "cinema",
        "single_header": "🎬 عدد شانس: {value}",
        "multi_header": "🎬 DICE × {count}",
        "separator": "🎞️━━━━━━━━━━━━━━🎞️",
        "footer": "\n🎬 TOTAL = {total}",
        "faces": {1: "■", 2: "■     ■", 3: "■     ■\n    ■", 4: "■     ■\n■     ■", 5: "■     ■\n    ■\n■     ■", 6: "■     ■\n■     ■\n■     ■"},
    },
    3: {
        "name": "kingdom",
        "single_header": "<blockquote>𒆙 ↻  عدد : {value} 🎲</blockquote>",
        "multi_header": "<blockquote>🎲 𒆜 DICES × {count}</blockquote>",
        "separator": "⌬⌬⌬⌬⌬⌬⌬⌬",
        "footer": "\n<blockquote>⌬ ﹝{total}﹞;</blockquote>",
        "faces": {1: "𒊹", 2: "𒊹 𒊹", 3: "𒊹 𒊹\n  𒊹", 4: "𒊹 𒊹\n𒊹 𒊹", 5: "𒊹 𒊹\n  𒊹\n𒊹 𒊹", 6: "𒊹 𒊹\n𒊹 𒊹\n𒊹 𒊹"},
    },
    4: {
        "name": "soft_emoji",
        "single_header": "🌈 نتیجه: {value}",
        "multi_header": "🌈 {count} تاس رنگی",
        "separator": "🌸🌸🌸🌸🌸",
        "footer": "\n🌈 مجموع: {total}",
        "faces": {1: "✨", 2: "✨ ✨", 3: "✨ ✨\n   ✨", 4: "✨ ✨\n✨ ✨", 5: "✨ ✨\n   ✨\n✨ ✨", 6: "✨ ✨\n✨ ✨\n✨ ✨"},
    },
    5: {
        "name": "minimal_dot",
        "single_header": "⌬ تـاس انداخته شـد عدد ↻  : {value} ",
        "multi_header": "⌬ تاس × {count}",
        "separator": "⌬⌬⌬⌬⌬⌬⌬⌬",
        "footer": "⌬\nمحاسبـه کـل ↻ : {total} ",
        "faces": {1: "▰", 2: "▰   ▰", 3: "▰   ▰\n  ▰", 4: "▰   ▰\n▰   ▰", 5: "▰   ▰\n  ▰\n▰   ▰", 6: "▰   ▰\n▰   ▰\n▰   ▰"},
    },
    6: {
        "name": "crystal",
        "single_header": "💎 کریستال ↻ {value}",
        "multi_header": "💎 CRYSTAL × {count}",
        "separator": "◆◇◆◇◆◇◆◇◆",
        "footer": "\n💎 مجموع: {total}",
        "faces": {1: "◆", 2: "◆     ◆", 3: "◆     ◆\n    ◆", 4: "◆     ◆\n◆     ◆", 5: "◆     ◆\n    ◆\n◆     ◆", 6: "◆     ◆\n◆     ◆\n◆     ◆"},
    },
    7: {
        "name": "samurai",
        "single_header": "⚔️ ضربه: {value}",
        "multi_header": "⚔️ ضربه‌ها × {count}",
        "separator": "⛩️⛩️⛩️⛩️⛩️",
        "footer": "\n⛩️ مجموع: {total}",
        "faces": {1: "卍", 2: "卍 卍", 3: "卍 卍\n  卍", 4: "卍 卍\n卍 卍", 5: "卍 卍\n  卍\n卍 卍", 6: "卍 卍\n卍 卍\n卍 卍"},
    },
    8: {
        "name": "grid",
        "single_header": "□ تاس: {value}",
        "multi_header": "□ × {count}",
        "separator": "□□□□□□□□□□",
        "footer": "\n□ مجموع: {total}",
        "faces": {1: "●", 2: "●   ●", 3: "●   ●\n   ●", 4: "●   ●\n●   ●", 5: "●   ●\n   ●\n●   ●", 6: "●   ●\n●   ●\n●   ●"},
    },
    9: {
        "name": "thunder",
        "single_header": "⚡ رعد ↻ {value}",
        "multi_header": "⚡ THUNDER × {count}",
        "separator": "•─────⚡─────•",
        "footer": "\n⚡ قدرت: {total}",
        "faces": {1: "⚡", 2: "⚡     ⚡", 3: "⚡     ⚡\n    ⚡", 4: "⚡     ⚡\n⚡     ⚡", 5: "⚡     ⚡\n    ⚡\n⚡     ⚡", 6: "⚡     ⚡\n⚡     ⚡\n⚡     ⚡"},
    },
    10: {
        "name": "alchemy",
        "single_header": "⚗️ کیمیا ↻ {value}",
        "multi_header": "⚗️ ALCHEMY × {count}",
        "separator": "•─────✧─────•",
        "footer": "\n⚗️ نتیجه نهایی: {total}",
        "faces": {1: "⟠", 2: "⟠     ⟠", 3: "⟠     ⟠\n    ⟠", 4: "⟠     ⟠\n⟠     ⟠", 5: "⟠     ⟠\n    ⟠\n⟠     ⟠", 6: "⟠     ⟠\n⟠     ⟠\n⟠     ⟠"},
    },
    11: {
        "name": "rose",
        "single_header": "🌹 رز ↻ {value} 🎲",
        "multi_header": "🌹 ROSE × {count}",
        "separator": "•─────🌹─────•",
        "footer": "\n🌹 مجموع: {total}",
        "faces": {1: "   ✿", 2: "✿   ✿", 3: "✿   ✿\n   ✿", 4: "✿   ✿\n✿   ✿", 5: "✿   ✿\n   ✿\n✿   ✿", 6: "✿   ✿\n✿   ✿\n✿   ✿"},
    },
    12: {
        "name": "forest",
        "single_header": "🌿 جنگل ↻ {value}",
        "multi_header": "🌿 FOREST × {count}",
        "separator": "•─────🌿─────•",
        "footer": "\n🌿 مجموع: {total}",
        "faces": {1: "❇", 2: "❇   ❇", 3: "❇   ❇\n    ❇", 4: "❇   ❇\n❇   ❇", 5: "❇   ❇\n    ❇\n❇   ❇", 6: "❇   ❇\n❇   ❇\n❇   ❇"},
    },
    13: {
        "name": "gold",
        "single_header": "👑 طلایی ↻ {value}",
        "multi_header": "👑 GOLD × {count}",
        "separator": "•─────👑─────•",
        "footer": "\n👑 مجموع: {total}",
        "faces": {1: "✦", 2: "✦   ✦", 3: "✦   ✦\n    ✦", 4: "✦   ✦\n✦   ✦", 5: "✦   ✦\n    ✦\n✦   ✦", 6: "✦   ✦\n✦   ✦\n✦   ✦"},
    },
    14: {
        "name": "skull",
        "single_header": "☠️ جمجمه ↻ {value}",
        "multi_header": "☠️ SKULL × {count}",
        "separator": "•─────🏴‍☠️─────•",
        "footer": "\n☠️ کــــیــــل ⟪{total}⟫",
        "faces": {1: "☠️", 2: "☠️   ☠️", 3: "☠️   ☠️\n    ☠️", 4: "☠️   ☠️\n☠️   ☠️", 5: "☠️   ☠️\n    ☠️\n☠️   ☠️", 6: "☠️   ☠️\n☠️   ☠️\n☠️   ☠️"},
    },
    15: {
        "name": "dragon_gate",
        "single_header": "<blockquote>🐉 دروازه اژدها: {value}</blockquote>",
        "multi_header": "<blockquote>🐉 عبور از دروازه × {count}</blockquote>",
        "separator": "•─────✧─────•",
        "footer": "\n<blockquote>🐲 نیروی کل: {total}</blockquote>",
        "faces": {1: "龙", 2: "龙  龙", 3: "龙  龙\n   龙", 4: "龙  龙\n龙  龙", 5: "龙  龙\n   龙\n龙  龙", 6: "龙  龙\n龙  龙\n龙  龙"},
    },
}

# سازگاری با کد قدیمی
THEMES = BUILTIN_THEMES

THEME_FIELDS = (
    "name",
    "single_header",
    "multi_header",
    "separator",
    "footer",
)
FACE_KEYS = (1, 2, 3, 4, 5, 6)
PAGE_SIZE = 5

FIELD_LABELS = {
    "name": "نام تم",
    "single_header": "هدر تاس تکی",
    "multi_header": "هدر تاس جمعی",
    "separator": "جداکننده",
    "footer": "فوتر (مجموع)",
    "face_1": "وجه ۱",
    "face_2": "وجه ۲",
    "face_3": "وجه ۳",
    "face_4": "وجه ۴",
    "face_5": "وجه ۵",
    "face_6": "وجه ۶",
}


def _custom_raw() -> dict:
    try:
        from bot import cache
        raw = cache.SITE_CONFIG.get("dice_themes") or {}
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _norm_faces(faces: Any) -> dict[int, str]:
    out: dict[int, str] = {}
    if not isinstance(faces, dict):
        return out
    for k, v in faces.items():
        try:
            n = int(k)
        except (TypeError, ValueError):
            continue
        if n in FACE_KEYS and v is not None:
            out[n] = str(v)
    return out


def _clean_theme_patch(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    if "name" in raw and raw["name"] is not None:
        out["name"] = str(raw["name"]).strip()[:64] or "custom"
    for key in ("single_header", "multi_header", "separator", "footer"):
        if key in raw and raw[key] is not None:
            out[key] = str(raw[key])
    if "faces" in raw:
        faces = _norm_faces(raw["faces"])
        if faces:
            out["faces"] = {str(k): v for k, v in faces.items()}
    return out


def list_theme_ids() -> list[int]:
    ids = set(int(k) for k in BUILTIN_THEMES.keys())
    for k in _custom_raw().keys():
        try:
            ids.add(int(k))
        except (TypeError, ValueError):
            continue
    return sorted(ids)


def max_theme_id() -> int:
    ids = list_theme_ids()
    return max(ids) if ids else 15


def theme_exists(theme_id: int) -> bool:
    tid = int(theme_id)
    return tid in BUILTIN_THEMES or str(tid) in _custom_raw()


def is_custom_only(theme_id: int) -> bool:
    return theme_id not in BUILTIN_THEMES and str(theme_id) in _custom_raw()


def has_override(theme_id: int) -> bool:
    return str(theme_id) in _custom_raw()


def page_count() -> int:
    n = len(list_theme_ids())
    return max(1, (n + PAGE_SIZE - 1) // PAGE_SIZE)


def themes_page(page: int) -> list[int]:
    ids = list_theme_ids()
    page = max(0, min(int(page), page_count() - 1))
    start = page * PAGE_SIZE
    return ids[start:start + PAGE_SIZE]


def get_theme(theme_id: int | None = None) -> dict:
    """تم نهایی (builtin ⊕ override) با {pe:...} رندر‌شده."""
    tid = int(theme_id or 1)
    base = copy.deepcopy(BUILTIN_THEMES.get(tid))
    patch = _clean_theme_patch(_custom_raw().get(str(tid)) or {})

    if not base and not patch:
        base = copy.deepcopy(BUILTIN_THEMES[1])

    if not base:
        faces = {i: "⬤" for i in FACE_KEYS}
        faces.update(_norm_faces(patch.get("faces") or {}))
        theme = {
            "name": patch.get("name") or f"custom_{tid}",
            "single_header": patch.get("single_header") or "تاس: {value}",
            "multi_header": patch.get("multi_header") or "تاس × {count}",
            "separator": patch.get("separator") or "•─────✧─────•",
            "footer": patch.get("footer") or "\nمجموع: {total}",
            "faces": faces,
        }
    else:
        theme = base
        if "name" in patch:
            theme["name"] = patch["name"]
        for key in ("single_header", "multi_header", "separator", "footer"):
            if key in patch:
                theme[key] = patch[key]
        if "faces" in patch:
            theme["faces"] = {**theme.get("faces", {}), **_norm_faces(patch["faces"])}

    return render_theme(theme)


def render_theme(theme: dict) -> dict:
    from bot.premium_emoji import render as pe_render

    out = dict(theme)
    for key in ("single_header", "multi_header", "separator", "footer"):
        if key in out and isinstance(out[key], str):
            out[key] = pe_render(out[key])
    faces = dict(out.get("faces") or {})
    out["faces"] = {
        int(k): pe_render(str(v)) if isinstance(v, str) else v
        for k, v in faces.items()
    }
    return out


def build_single_dice_message(r: int, theme: dict) -> str:
    header = theme["single_header"].replace("{value}", str(r))
    return header + "\n" + theme["faces"][r]


def build_multi_dice_message(results: list, total: int, count: int, theme: dict) -> str:
    separator = theme["separator"]
    header = theme["multi_header"].replace("{count}", str(count))
    lines = [header, ""]
    for i, r in enumerate(results):
        lines.append(theme["faces"][r])
        if i != count - 1:
            lines.append(separator)
    lines.append(theme["footer"].replace("{total}", str(total)))
    return "\n".join(lines)


def get_field_value(theme_id: int, field: str) -> str:
    """مقدار خام فیلد (قبل از pe render) برای نمایش در ادیتور."""
    tid = int(theme_id)
    patch = _clean_theme_patch(_custom_raw().get(str(tid)) or {})
    base = copy.deepcopy(BUILTIN_THEMES.get(tid)) or default_new_theme(tid)

    if field.startswith("face_"):
        n = int(field.split("_", 1)[1])
        if "faces" in patch and str(n) in patch["faces"]:
            return patch["faces"][str(n)]
        return str((base.get("faces") or {}).get(n, ""))

    if field in patch:
        return str(patch[field])
    return str(base.get(field, ""))


def theme_status_line(theme_id: int) -> str:
    theme = get_theme(theme_id)
    name = theme.get("name") or f"#{theme_id}"
    if theme_id in BUILTIN_THEMES and has_override(theme_id):
        mark = "✏️"
    elif is_custom_only(theme_id):
        mark = "🆕"
    else:
        mark = "📦"
    return f"{mark} <b>{theme_id}</b> — {escape(str(name))}"


def preview_theme(theme_id: int, sample_value: int = 5, sample_count: int = 3) -> str:
    theme = get_theme(theme_id)
    single = build_single_dice_message(sample_value, theme)
    results = [sample_value, max(1, sample_value - 1), min(6, sample_value + 1)][:sample_count]
    total = sum(results)
    multi = build_multi_dice_message(results, total, len(results), theme)
    name = escape(str(theme.get("name") or f"#{theme_id}"))
    return (
        f"👁 <b>پیش‌نمایش تم {theme_id}</b> — {name}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>تکی:</b>\n{single}\n\n"
        f"<b>جمعی (×{len(results)}):</b>\n{multi}"
    )


def message_to_theme_html(message: Message) -> str:
    """متن پیام (با ایموجی پرمیوم) → HTML با <tg-emoji>."""
    text = message.text or message.caption or ""
    entities = list(message.entities or []) + list(message.caption_entities or [])
    if not text:
        return ""

    custom = [
        e for e in entities
        if getattr(e, "type", None) == "custom_emoji" and getattr(e, "custom_emoji_id", None)
    ]
    if not custom:
        return text

    encoded = text.encode("utf-16-le")
    parts: list[str] = []
    cursor = 0

    for ent in sorted(custom, key=lambda e: e.offset):
        if ent.offset > cursor:
            chunk = encoded[cursor * 2: ent.offset * 2].decode("utf-16-le")
            parts.append(escape(chunk))
        eid = str(ent.custom_emoji_id)
        alt_chunk = encoded[ent.offset * 2: (ent.offset + ent.length) * 2].decode("utf-16-le")
        alt = escape(alt_chunk) or "⭐"
        parts.append(f'<tg-emoji emoji-id="{eid}">{alt}</tg-emoji>')
        cursor = ent.offset + ent.length

    if cursor * 2 < len(encoded):
        parts.append(escape(encoded[cursor * 2:].decode("utf-16-le")))
    return "".join(parts)


def parse_theme_import(text: str) -> tuple[dict[str, dict], str | None]:
    raw = (text or "").strip()
    if not raw:
        return {}, "متن خالی است."
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        data = json.loads(raw)
    except Exception as e:
        return {}, f"JSON نامعتبر: {e}"

    if isinstance(data, dict) and "dice_themes" in data:
        data = data.get("dice_themes") or {}
    if not isinstance(data, dict):
        return {}, "فرمت باید دیکشنری تم‌ها باشد."

    out: dict[str, dict] = {}
    for k, v in data.items():
        try:
            tid = str(int(k))
        except (TypeError, ValueError):
            continue
        patch = _clean_theme_patch(v if isinstance(v, dict) else {})
        if patch:
            out[tid] = patch
    if not out:
        return {}, "هیچ تم معتبری پیدا نشد."
    return out, None


def export_themes(include_builtins: bool = False) -> dict:
    custom: dict[str, dict] = {}
    for k, v in _custom_raw().items():
        patch = _clean_theme_patch(v if isinstance(v, dict) else {})
        if patch:
            custom[str(k)] = patch
    if include_builtins:
        merged: dict[str, dict] = {}
        for tid in list_theme_ids():
            t = get_theme(tid)
            faces = {str(i): t["faces"][i] for i in FACE_KEYS if i in t.get("faces", {})}
            merged[str(tid)] = {
                "name": t.get("name"),
                "single_header": t.get("single_header"),
                "multi_header": t.get("multi_header"),
                "separator": t.get("separator"),
                "footer": t.get("footer"),
                "faces": faces,
            }
        for k, v in custom.items():
            merged[k] = {**merged.get(k, {}), **v}
            if "faces" in v:
                base_f = dict(merged.get(k, {}).get("faces") or {})
                base_f.update(v["faces"])
                merged[k]["faces"] = base_f
        payload = merged
    else:
        payload = custom
    return {
        "version": 1,
        "type": "tasino_dice_themes",
        "dice_themes": payload,
    }


def export_themes_json(pretty: bool = True, include_builtins: bool = False) -> str:
    data = export_themes(include_builtins=include_builtins)
    if pretty:
        return json.dumps(data, ensure_ascii=False, indent=2)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def next_custom_theme_id() -> int:
    return max(max_theme_id() + 1, 16)


def default_new_theme(theme_id: int) -> dict:
    return {
        "name": f"custom_{theme_id}",
        "single_header": "{pe:dice} تاس: {value}",
        "multi_header": "{pe:dice} تاس × {count}",
        "separator": "•─────✧─────•",
        "footer": "\n{pe:dice} مجموع: {total}",
        "faces": {
            "1": "⬤",
            "2": "⬤ ⬤",
            "3": "⬤ ⬤\n  ⬤",
            "4": "⬤ ⬤\n⬤ ⬤",
            "5": "⬤ ⬤\n  ⬤\n⬤ ⬤",
            "6": "⬤ ⬤\n⬤ ⬤\n⬤ ⬤",
        },
    }
