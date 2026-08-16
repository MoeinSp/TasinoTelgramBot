"""ارسال تبلیغ زمان‌بندی‌شده بدون قفل کردن event loop ربات."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

GROUP_CONCURRENCY = 12
PV_CONCURRENCY = 6
CHUNK = 16
SEND_PAUSE = 0.02
SEND_TIMEOUT = 8.0

_group_sem: asyncio.Semaphore | None = None
_pv_sem: asyncio.Semaphore | None = None
_bg_tasks: set[asyncio.Task] = set()
_sending: set[int] = set()


def _sems() -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
    global _group_sem, _pv_sem
    if _group_sem is None:
        _group_sem = asyncio.Semaphore(GROUP_CONCURRENCY)
        _pv_sem = asyncio.Semaphore(PV_CONCURRENCY)
    return _group_sem, _pv_sem


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _load_due(now):
    from account.models import TelegramGroup, TelegramUser
    from scheduledmessage.models import ScheduledMessage

    TelegramGroup.objects.filter(
        ad_enabled=False,
        ad_disabled_until__isnull=False,
        ad_disabled_until__lte=now,
    ).update(ad_enabled=True, ad_disabled_until=None)

    fixed = list(
        ScheduledMessage.objects.filter(
            is_active=True,
            type="fixed",
            last_sent__isnull=True,
            run_at__lte=now,
        ).order_by("run_at", "id")
    )
    intervals = []
    for task in ScheduledMessage.objects.filter(
        is_active=True, type="interval", interval_minutes__isnull=False,
    ):
        if not task.last_sent or now >= task.last_sent + timedelta(minutes=task.interval_minutes):
            intervals.append(task)
    tasks = fixed + intervals
    if not tasks:
        return [], [], {}

    group_meta = {
        int(row["telegram_chat_id"]): row
        for row in TelegramGroup.objects.filter(is_active=True).values(
            "telegram_chat_id", "ad_enabled", "ad_disabled_until",
        )
        if row.get("telegram_chat_id")
    }
    pv_ids = []
    if any(t.send_to_pv for t in tasks):
        pv_ids = [
            int(cid)
            for cid in TelegramUser.objects.exclude(telegram_chat_id__isnull=True)
            .values_list("telegram_chat_id", flat=True)
            if cid
        ]
    return tasks, pv_ids, group_meta


def _mark_sent(task, now):
    from scheduledmessage.models import ScheduledMessage

    qs = ScheduledMessage.objects.filter(id=task.id)
    if task.type == "interval":
        qs.update(last_sent=now)
        return
    qs.filter(last_sent__isnull=True).update(last_sent=now, is_active=False)


def _eligible_groups(task, group_meta, now) -> tuple[list[int], int]:
    if task.send_to_all:
        candidates = list(group_meta.keys())
    elif task.chat_id:
        candidates = [int(task.chat_id)]
    else:
        candidates = []

    real = []
    pending = 0
    for cid in dict.fromkeys(candidates):
        meta = group_meta.get(cid)
        if not task.ignore_group_ad_setting:
            if not meta:
                continue
            until = meta.get("ad_disabled_until")
            if until and until > now:
                continue
            if not meta.get("ad_enabled", True):
                continue
        if task.queue_ad_until_message:
            if cache.get(f"sched_pending:{cid}"):
                continue
            if cache.get(f"sched_lastad:{cid}"):
                cache.set(f"sched_pending:{cid}", task.text, timeout=None)
                pending += 1
                continue
        real.append(cid)
    return real, pending


def _pv_targets(task, all_pv: list[int]) -> list[int]:
    if not getattr(task, "send_to_pv", False):
        return []
    if task.send_to_all or not task.chat_id:
        return list(dict.fromkeys(all_pv))
    return [int(task.chat_id)]


async def _send_one(bot: Bot, sem, cid, text) -> bool:
    async with sem:
        try:
            await asyncio.wait_for(bot.send_message(cid, text), timeout=SEND_TIMEOUT)
            return True
        except TelegramRetryAfter as exc:
            try:
                await asyncio.sleep(min(float(exc.retry_after or 1), 5))
                await asyncio.wait_for(bot.send_message(cid, text), timeout=SEND_TIMEOUT)
                return True
            except Exception:
                return False
        except (TelegramForbiddenError, TelegramBadRequest):
            return False
        except Exception as exc:
            logger.debug("ارسال به %s ناموفق: %s", cid, exc)
            return False
        finally:
            await asyncio.sleep(SEND_PAUSE)


async def _send_chunked(bot, sem, cids, text) -> int:
    ok = 0
    for i in range(0, len(cids), CHUNK):
        chunk = cids[i:i + CHUNK]
        results = await asyncio.gather(
            *[_send_one(bot, sem, cid, text) for cid in chunk],
            return_exceptions=True,
        )
        for cid, res in zip(chunk, results):
            if res is True:
                ok += 1
                cache.set(f"sched_lastad:{cid}", True, timeout=86400)
        await asyncio.sleep(0)
    return ok


async def _dispatch_task(bot, task, pv_ids, group_meta, now):
    group_sem, pv_sem = _sems()
    groups, pending = _eligible_groups(task, group_meta, now)
    pvs = _pv_targets(task, pv_ids)
    try:
        ok_groups = await _send_chunked(bot, group_sem, groups, task.text)
        await sync_to_async(_mark_sent)(task, now)
        ok_pv = 0
        if pvs:
            ok_pv = await _send_chunked(bot, pv_sem, pvs, task.text)
        logger.info(
            "📅 '%s' → %d/%d گروه | %d/%d پیوی | %d در صف",
            task.title, ok_groups, len(groups), ok_pv, len(pvs), pending,
        )
    except Exception:
        logger.exception("ad dispatch id=%s", task.id)
    finally:
        _sending.discard(task.id)


async def send_scheduled_logic(bot: Bot):
    now = timezone.now()
    tasks, pv_ids, group_meta = await sync_to_async(_load_due)(now)
    if not tasks:
        return
    for task in tasks:
        if task.id in _sending:
            continue
        _sending.add(task.id)
        _spawn(_dispatch_task(bot, task, pv_ids, group_meta, now))
