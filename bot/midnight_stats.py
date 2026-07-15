"""آمار نیمه‌شب — هشدار ۱ دقیقه قبل و ارسال دقیق ۶۰ ثانیه بعد."""
from __future__ import annotations

import asyncio
import datetime
import html
import logging

import jdatetime
from asgiref.sync import sync_to_async
from django.core.cache import cache as django_cache
from django.utils.timezone import localtime

logger = logging.getLogger(__name__)


async def _name_map_for_chat(bot, chat_id: int, user_ids: list[int]) -> dict:
    out = {}
    for uid in user_ids:
        try:
            member = await bot.get_chat_member(chat_id, uid)
            out[uid] = html.escape(
                member.user.full_name or member.user.first_name or str(uid)
            )
        except Exception:
            out[uid] = f'<a href="tg://user?id={uid}">کاربر</a>'
    return out


async def broadcast_midnight_warning(bot) -> int:
    from account.models import DiceGameHistory, TelegramGroup

    now_time = localtime()
    day_key = now_time.strftime("%Y-%m-%d")
    cache_key = f"tg_midnight_stats_warn:{day_key}"
    if django_cache.get(cache_key):
        return 0
    django_cache.set(cache_key, 1, timeout=7200)

    today_start = now_time.replace(hour=0, minute=0, second=0, microsecond=0)
    active_groups = await sync_to_async(list)(
        TelegramGroup.objects.filter(is_active=True).values_list("telegram_chat_id", flat=True)
    )

    text = (
        "⏰ یک دقیقه تا پایان روز!\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 آمار روزانه تا ۶۰ ثانیه دیگر ارسال می‌شود.\n"
        "🔄 بعد از نیمه‌شب، آمار امروز ریست می‌شود و روز جدید شروع می‌گردد.\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⏳ دقیقاً یک دقیقه دیگر آمار نهایی امروز را می‌فرستم."
    )
    sent = 0
    for chat_id in active_groups:
        try:
            has_today = await sync_to_async(
                DiceGameHistory.objects.filter(
                    telegram_chat_id=int(chat_id),
                    created_at__gte=today_start,
                ).exists
            )()
            if not has_today:
                continue
            await bot.send_message(int(chat_id), text)
            sent += 1
        except Exception:
            logger.exception("midnight warning error for %s", chat_id)
    return sent


async def broadcast_midnight_stats(bot) -> None:
    from account.models import DiceGameHistory, TelegramGroup
    from bot.dice_stats_fmt import format_dice_game_stats

    now_time = localtime()
    finished_day = (now_time - datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    day_end = now_time.replace(hour=0, minute=0, second=0, microsecond=0)
    stats_key = f"tg_midnight_stats_sent:{finished_day.strftime('%Y-%m-%d')}"
    if django_cache.get(stats_key):
        return
    django_cache.set(stats_key, 1, timeout=86400)

    active_groups = await sync_to_async(list)(
        TelegramGroup.objects.filter(is_active=True).values_list("telegram_chat_id", flat=True)
    )

    for chat_id in active_groups:
        try:
            records = await sync_to_async(list)(
                DiceGameHistory.objects.filter(
                    telegram_chat_id=int(chat_id),
                    created_at__gte=finished_day,
                    created_at__lt=day_end,
                )
            )
            if not records:
                continue
            all_ids = list({int(rec.telegram_user_id) for rec in records})
            name_map = await _name_map_for_chat(bot, int(chat_id), all_ids) if all_ids else {}
            date_j = jdatetime.datetime.fromgregorian(datetime=finished_day).strftime("%Y/%m/%d")
            title = f"🌙 آمار روزانه تاسینو · 📅 {date_j}"
            text = format_dice_game_stats(records, title, name_map)
            text += "\n📊 برای جزئیات بیشتر: «آمار تاس»"
            await bot.send_message(int(chat_id), text, parse_mode="HTML")
        except Exception:
            logger.exception("midnight stats error for %s", chat_id)


async def midnight_warn_then_stats(bot) -> None:
    lock_key = "tg_midnight_warn_then_stats_running"
    if django_cache.get(lock_key):
        return
    django_cache.set(lock_key, 1, timeout=180)
    try:
        await broadcast_midnight_warning(bot)
        await asyncio.sleep(60)
        await broadcast_midnight_stats(bot)
    except Exception:
        logger.exception("midnight_warn_then_stats error")
    finally:
        django_cache.delete(lock_key)
