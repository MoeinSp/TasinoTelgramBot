"""ضد اسپم دکمه/پیام پیوی — حداکثر چند پاسخ در پنجرهٔ زمانی."""
from __future__ import annotations

import time
from collections import defaultdict

_DEBOUNCE_SEC = 1.4
_REPLY_WINDOW = 12.0
_REPLY_BUDGET = 3

_last_action: dict[str, float] = {}
_reply_hits: dict[str, list[float]] = defaultdict(list)


def _k(user_id, action: str = "") -> str:
    base = str(user_id or "").strip()
    act = (action or "").strip()
    return f"{base}:{act}" if act else base


def allow_action(user_id, action: str, *, debounce: float = _DEBOUNCE_SEC) -> bool:
    """همان اکشن در فاصلهٔ کوتاه → رد (سایلنت)."""
    key = _k(user_id, action)
    now = time.time()
    last = float(_last_action.get(key) or 0)
    if now - last < float(debounce):
        return False
    _last_action[key] = now
    if len(_last_action) > 4000:
        cutoff = now - 120
        for k in list(_last_action.keys())[:800]:
            if float(_last_action.get(k) or 0) < cutoff:
                _last_action.pop(k, None)
    return True


def allow_reply(user_id, *, window: float = _REPLY_WINDOW, budget: int = _REPLY_BUDGET) -> bool:
    """سقف تعداد پیام خروجی به کاربر در پنجره (پیش‌فرض ۳ در ۱۲ثانیه)."""
    key = _k(user_id)
    now = time.time()
    arr = [t for t in _reply_hits[key] if now - t < float(window)]
    if len(arr) >= int(budget):
        _reply_hits[key] = arr
        return False
    arr.append(now)
    _reply_hits[key] = arr
    return True


def action_bucket(btn_id: str) -> str:
    raw = (btn_id or "").strip()
    if not raw:
        return "x"
    if "|" in raw:
        return raw.split("|", 1)[0]
    if ":" in raw:
        parts = raw.split(":")
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}"
    return raw[:32]
