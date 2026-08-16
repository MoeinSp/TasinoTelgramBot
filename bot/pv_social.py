"""قابلیت‌های اجتماعی مسابقه پیوی: چت، واکنش، بلاک، ریمچ، رکورد، آرشیو برای ادمین."""
from __future__ import annotations

import time
import uuid

CHAT_WARN = (
    "⚠️ ادب را رعایت کنید.\n"
    "این گفتگو داخل بازی پیوی است و توسط مدیران گروه قابل بررسی است.\n"
    "━━━━━━━━━━━━━━━━━━━━"
)

CHAT_COOLDOWN_SEC = 10

QUICK_REACTS = [
    ("👏", "آفرین"),
    ("🔥", "حرفه‌ای"),
    ("😮", "شانس آوردی"),
    ("😅", "بد شانسی"),
    ("⏳", "صبر کن"),
    ("💪", "ادامه بده"),
]

# rematch tokens
REMATCH: dict[str, dict] = {}
# streaks: f"{group}:{user}" → int
STREAKS: dict[str, int] = {}
# archive key f"{group}:{user}" → list[dict]
CHAT_ARCHIVE: dict[str, list[dict]] = {}

_ARCHIVE_TTL = 60 * 60 * 24 * 14
_REMATCH_TTL = 600
_MAX_CHAT_PER_GAME = 80
_MAX_ARCHIVE_PER_USER = 8

# Redis keys — TG-prefixed to avoid clash with Rubika
_CACHE_STREAKS = "tg_pv_social:v1:streaks"
_CACHE_ARCHIVE = "tg_pv_social:v1:archive"
_CACHE_REMATCH = "tg_pv_social:v1:rematch"


def _sid(uid) -> str:
    return str(uid).strip()


def _same(a, b) -> bool:
    return _sid(a) == _sid(b)


def _name_of(game: dict, uid) -> str:
    names = game.get("names") or {}
    sid = _sid(uid)
    if sid in names:
        return str(names[sid])
    try:
        i = int(uid)
        if i in names:
            return str(names[i])
    except (TypeError, ValueError):
        pass
    if uid in names:
        return str(names[uid])
    return sid


def _streak_key(group_id, user_id) -> str:
    return f"{str(group_id).strip()}:{_sid(user_id)}"


def _archive_key(group_id, user_id) -> str:
    return _streak_key(group_id, user_id)


def ensure_game_social(game: dict) -> None:
    game.setdefault("chat_log", [])
    game.setdefault("chat_warned", {})
    game.setdefault("chat_blocked", {})  # uid → True : پیام حریف را نمی‌گیرد
    game.setdefault("chat_block_used", {})  # uid → True : یک‌بار بلاک/آنبلاک مصرف شده
    game.setdefault("last_chat_ts", {})


def append_chat(game: dict, sender_id, text: str, *, kind: str = "text") -> dict:
    ensure_game_social(game)
    entry = {
        "ts": time.time(),
        "from": _sid(sender_id),
        "name": _name_of(game, sender_id),
        "text": (text or "").strip()[:400],
        "kind": kind,
    }
    log = game["chat_log"]
    log.append(entry)
    if len(log) > _MAX_CHAT_PER_GAME:
        del log[: len(log) - _MAX_CHAT_PER_GAME]
    return entry


def needs_chat_warning(game: dict, user_id) -> bool:
    ensure_game_social(game)
    return not bool(game["chat_warned"].get(_sid(user_id)))


def mark_chat_warned(game: dict, user_id) -> None:
    ensure_game_social(game)
    game["chat_warned"][_sid(user_id)] = True


def is_chat_blocked_by(game: dict, blocker_id) -> bool:
    ensure_game_social(game)
    return bool(game["chat_blocked"].get(_sid(blocker_id)))


def toggle_chat_block(game: dict, user_id) -> bool:
    """بلاک را عوض می‌کند؛ True = الان بلاک است."""
    ensure_game_social(game)
    uid = _sid(user_id)
    now = not bool(game["chat_blocked"].get(uid))
    if now:
        game["chat_blocked"][uid] = True
    else:
        game["chat_blocked"].pop(uid, None)
    return now


def try_chat_block_once(game: dict, user_id) -> tuple[str, bool]:
    """فقط یک‌بار در هر بازی اجازه بلاک/آنبلاک.

    خروجی: (status, is_blocked) — status: blocked | unblocked | already_used
    """
    ensure_game_social(game)
    uid = _sid(user_id)
    used = game.setdefault("chat_block_used", {})
    if used.get(uid):
        return "already_used", bool(game["chat_blocked"].get(uid))
    now_blocked = toggle_chat_block(game, uid)
    used[uid] = True
    return ("blocked" if now_blocked else "unblocked"), now_blocked


def chat_block_used(game: dict, user_id) -> bool:
    ensure_game_social(game)
    return bool(game.get("chat_block_used", {}).get(_sid(user_id)))


def chat_cooldown_left(game: dict, user_id) -> int:
    ensure_game_social(game)
    last = float(game["last_chat_ts"].get(_sid(user_id)) or 0)
    left = CHAT_COOLDOWN_SEC - (time.time() - last)
    return max(0, int(left + 0.999))


def mark_chat_activity(game: dict, user_id) -> None:
    ensure_game_social(game)
    game["last_chat_ts"][_sid(user_id)] = time.time()


def format_chat_relay(entry: dict, *, to_self: bool = False) -> str:
    import html as _html
    who = "شما" if to_self else _html.escape(str(entry.get("name") or "حریف"))
    prefix = "💬 پیام شما" if to_self else f"💬 پیام از {who}"
    return f"{prefix}\n━━━━━━━━━━━━━━━━━━━━\n{_html.escape(str(entry.get('text') or ''))}"


def react_label(code: str) -> str | None:
    for emoji, title in QUICK_REACTS:
        if emoji == code or title == code:
            return f"{emoji} {title}"
    return None


def update_streak(group_id, winner_id, loser_id) -> tuple[int, str]:
    """Returns (winner_streak, title_line)."""
    wk = _streak_key(group_id, winner_id)
    lk = _streak_key(group_id, loser_id)
    STREAKS[wk] = int(STREAKS.get(wk) or 0) + 1
    STREAKS[lk] = 0
    n = STREAKS[wk]
    title = ""
    if n >= 5:
        title = f"👑 لقب موقت: سلطان پیوی ({n} برد پیاپی)"
    elif n >= 3:
        title = f"🏅 لقب موقت: آتشین ({n} برد پیاپی)"
    return n, title


def streak_line(group_id, user_id) -> str:
    n = int(STREAKS.get(_streak_key(group_id, user_id)) or 0)
    if n <= 0:
        return ""
    return f"🔥 سری برد فعلی: {n}"


def archive_game_chat(game: dict, *, winner_id=None, is_tie: bool = False) -> None:
    ensure_game_social(game)
    gid = str(game.get("group_id") or "").strip()
    if not gid:
        return
    # normalize names to string keys for archive readability
    raw_names = dict(game.get("names") or {})
    names = {_sid(k): v for k, v in raw_names.items()}
    payload = {
        "game_id": game.get("id"),
        "ended_at": time.time(),
        "players": [_sid(p) for p in (game.get("players") or [])],
        "names": names,
        "winner_id": _sid(winner_id) if winner_id else None,
        "is_tie": bool(is_tie),
        "totals": {_sid(k): v for k, v in (game.get("totals") or {}).items()},
        "chat_log": list(game.get("chat_log") or []),
    }
    for p in game.get("players") or []:
        key = _archive_key(gid, p)
        arr = CHAT_ARCHIVE.setdefault(key, [])
        arr.insert(0, payload)
        del arr[_MAX_ARCHIVE_PER_USER:]
    _persist_social()


def format_admin_chats(group_id, user_id, *, limit: int = 3) -> str:
    import html as _html
    key = _archive_key(group_id, user_id)
    rows = CHAT_ARCHIVE.get(key) or []
    if not rows:
        return (
            "📭 چت ثبت‌شده‌ای برای این کاربر در بازی‌های پیوی این گروه نیست.\n"
            "بعد از پایان بازی‌هایی که داخلشان پیام رد و بدل شده، اینجا دیده می‌شود."
        )
    chunks = []
    for i, g in enumerate(rows[:limit], start=1):
        names = g.get("names") or {}
        a, b = (g.get("players") or [None, None])[:2]
        na = _html.escape(str(names.get(_sid(a), a)))
        nb = _html.escape(str(names.get(_sid(b), b)))
        w = g.get("winner_id")
        head = f"🎮 بازی {i}: {na} vs {nb}"
        if g.get("is_tie"):
            head += " — تساوی"
        elif w:
            head += f" — برنده: {_html.escape(str(names.get(_sid(w), w)))}"
        lines = [head, "────────────────────"]
        log = g.get("chat_log") or []
        if not log:
            lines.append("(بدون پیام چت)")
        else:
            for e in log:
                t = time.strftime("%H:%M", time.localtime(float(e.get("ts") or 0)))
                lines.append(
                    f"[{t}] {_html.escape(str(e.get('name') or ''))}: "
                    f"{_html.escape(str(e.get('text') or ''))}"
                )
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def create_rematch_token(game: dict, *, requester_id) -> str:
    token = uuid.uuid4().hex[:10]
    players = list(game.get("players") or [])
    raw_names = dict(game.get("names") or {})
    names = {_sid(k): v for k, v in raw_names.items()}
    REMATCH[token] = {
        "group_id": str(game.get("group_id") or "").strip(),
        "players": [_sid(p) for p in players],
        "names": names,
        "has_bet": bool(game.get("has_bet")),
        "bet_amount": int(game.get("bet_amount") or 0),
        "bet_mode": game.get("bet_mode"),
        "fee_percent": int(game.get("fee_percent") or 0),
        "mode_label": game.get("mode_label") or "",
        "requester": _sid(requester_id),
        "double": False,
        "via_search": bool(game.get("via_search")),
        "expires_at": time.time() + _REMATCH_TTL,
    }
    _persist_social()
    return token


def create_double_token(game: dict, *, requester_id) -> str:
    token = create_rematch_token(game, requester_id=requester_id)
    REMATCH[token]["double"] = True
    REMATCH[token]["bet_amount"] = max(1, int(game.get("bet_amount") or 0) * 2)
    _persist_social()
    return token


def pop_rematch(token: str) -> dict | None:
    data = REMATCH.pop(token, None)
    _persist_social()
    if not data:
        return None
    if time.time() > float(data.get("expires_at") or 0):
        return None
    return data


def enrich_end_text(
    base: str,
    game: dict,
    *,
    winner_id=None,
    is_tie: bool = False,
) -> str:
    extra = []
    if winner_id and not is_tie:
        loser = next(
            (_sid(p) for p in (game.get("players") or []) if not _same(p, winner_id)),
            None,
        )
        if loser is not None:
            # سری برد فقط داخلی ثبت می‌شود؛ در متن نتیجه نشان داده نمی‌شود
            update_streak(game.get("group_id"), winner_id, loser)
    elif is_tie:
        for p in game.get("players") or []:
            STREAKS[_streak_key(game.get("group_id"), p)] = 0
    totals = game.get("totals") or {}
    if len(game.get("players") or []) == 2:
        a, b = game["players"]
        ta = totals.get(a, totals.get(_sid(a), 0))
        tb = totals.get(b, totals.get(_sid(b), 0))
        diff = abs(int(ta or 0) - int(tb or 0))
        extra.append(f"📉 اختلاف امتیاز: {diff}")
    if not extra:
        return base
    return base.rstrip() + "\n\n" + "\n".join(extra)


def _persist_social() -> None:
    try:
        from django.core.cache import cache
        cache.set(_CACHE_STREAKS, dict(STREAKS), timeout=_ARCHIVE_TTL)
        cache.set(_CACHE_ARCHIVE, dict(CHAT_ARCHIVE), timeout=_ARCHIVE_TTL)
        cache.set(_CACHE_REMATCH, dict(REMATCH), timeout=_REMATCH_TTL)
    except Exception:
        pass


def persist_social() -> None:
    _persist_social()


def load_social() -> None:
    try:
        from django.core.cache import cache
        s = cache.get(_CACHE_STREAKS)
        a = cache.get(_CACHE_ARCHIVE)
        r = cache.get(_CACHE_REMATCH)
        if isinstance(s, dict):
            STREAKS.clear()
            STREAKS.update(s)
        if isinstance(a, dict):
            CHAT_ARCHIVE.clear()
            CHAT_ARCHIVE.update(a)
        if isinstance(r, dict):
            REMATCH.clear()
            REMATCH.update(r)
    except Exception:
        pass
