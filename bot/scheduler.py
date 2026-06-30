import asyncio
import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─── کمکی‌ها ──────────────────────────────────────────────────────────────────

@sync_to_async
def _get_active_tasks():
    from scheduledmessage.models import ScheduledMessage
    return list(ScheduledMessage.objects.filter(is_active=True))


@sync_to_async
def _get_all_group_ids():
    from account.models import TelegramGroup
    return list(TelegramGroup.objects.filter(is_active=True).values_list("telegram_chat_id", flat=True))


@sync_to_async
def _get_group(chat_id):
    from account.models import TelegramGroup
    try:
        return TelegramGroup.objects.get(telegram_chat_id=chat_id)
    except TelegramGroup.DoesNotExist:
        return None


@sync_to_async
def _mark_task(task_id, last_sent, is_active):
    from scheduledmessage.models import ScheduledMessage
    ScheduledMessage.objects.filter(id=task_id).update(last_sent=last_sent, is_active=is_active)


async def _safe_send(bot: Bot, chat_id: int, text: str, parse_mode: str = None):
    try:
        await bot.send_message(chat_id, text, parse_mode=parse_mode)
        return True
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        logger.debug("ارسال به %s ناموفق: %s", chat_id, e)
        return False
    except Exception as e:
        logger.warning("خطا در ارسال به %s: %s", chat_id, e)
        return False


# ─── منطق اصلی ────────────────────────────────────────────────────────────────

async def send_scheduled_logic(bot: Bot):
    now = timezone.now().replace(second=0, microsecond=0)

    tasks = await _get_active_tasks()
    if not tasks:
        return

    # گروه‌های همه رو یکبار بگیر اگر هر task نیاز داشت
    all_group_ids = None

    for task in tasks:
        should_send = False
        remain_active = True

        if task.type == "fixed":
            if task.run_at and task.run_at <= now and not task.last_sent:
                should_send = True
                remain_active = False

        elif task.type == "interval":
            if task.interval_minutes:
                if not task.last_sent or now >= task.last_sent + timedelta(minutes=task.interval_minutes):
                    should_send = True

        if not should_send:
            continue

        # هدف‌ها
        group_targets = []

        if task.send_to_all:
            if all_group_ids is None:
                all_group_ids = await _get_all_group_ids()
            group_targets = list(all_group_ids)
        elif task.chat_id:
            group_targets = [task.chat_id]

        # فیلتر تبلیغاتی
        final_groups = []
        pending_count = 0

        for cid in group_targets:
            if task.ignore_group_ad_setting:
                final_groups.append(cid)
                continue

            group = await _get_group(cid)
            if not group:
                continue

            # چک خاموشی موقت
            if group.ad_disabled_until and group.ad_disabled_until > timezone.now():
                continue

            if not group.ad_enabled:
                continue

            # صف تبلیغ تا ارسال پیام بعدی
            if task.queue_ad_until_message:
                pending_key = f"sched_pending:{cid}"
                last_ad_key = f"sched_lastad:{cid}"

                if cache.get(pending_key):
                    continue

                if cache.get(last_ad_key):
                    cache.set(pending_key, task.text, timeout=None)
                    pending_count += 1
                    continue

                final_groups.append(cid)
            else:
                final_groups.append(cid)

        # ارسال موازی به گروه‌ها
        sent_count = 0
        if final_groups:
            results = await asyncio.gather(
                *[_safe_send(bot, cid, task.text, parse_mode=task.parse_mode if hasattr(task, "parse_mode") else None)
                  for cid in final_groups],
                return_exceptions=True
            )
            sent_count = sum(1 for r in results if r is True)

            for cid in final_groups:
                cache.set(f"sched_lastad:{cid}", True, timeout=86400)

        await _mark_task(task.id, now, remain_active)

        logger.info(
            "📅 '%s' → %d گروه ارسال شد | %d در صف | باقی‌مانده فعال: %s",
            task.title, sent_count, pending_count, remain_active
        )
