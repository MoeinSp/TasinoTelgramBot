"""آمار نیمه‌شب — هشدار ۲۳:۵۹ و ارسال آمار دقیقاً ۰۰:۰۰ (بدون sleep وابسته)."""
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

_SEND_CONCURRENCY = 8


async def _name_map_for_chat(bot, chat_id: int, user_ids: list[int]) -> dict:
    """نام از DB؛ بدون get_chat_member تا نیمه‌شب گیر نکند."""
    from account.models import TelegramGroupMember

    out: dict = {}
    if not user_ids:
        return out
    rows = await sync_to_async(list)(
        TelegramGroupMember.objects.filter(
            telegram_chat_id=int(chat_id),
            telegram_user_id__in=[int(u) for u in user_ids],
        ).values_list("telegram_user_id", "alias")
    )
    for uid, alias in rows:
        name = (alias or "").strip()
        if name:
            out[int(uid)] = html.escape(name)
    for uid in user_ids:
        uid = int(uid)
        if uid not in out:
            out[uid] = f'<a href="tg://user?id={uid}">کاربر</a>'
    return out


async def _active_chat_ids() -> list[int]:
    from account.models import TelegramGroup

    return await sync_to_async(list)(
        TelegramGroup.objects.filter(is_active=True).values_list("telegram_chat_id", flat=True)
    )


async def _chats_with_games_since(since) -> set[int]:
    from account.models import DiceGameHistory

    ids = await sync_to_async(list)(
        DiceGameHistory.objects.filter(created_at__gte=since)
        .values_list("telegram_chat_id", flat=True)
        .distinct()
    )
    return {int(x) for x in ids if x is not None}


async def broadcast_midnight_warning(bot) -> int:
    now_time = localtime()
    day_key = now_time.strftime("%Y-%m-%d")
    cache_key = f"tg_midnight_stats_warn:{day_key}"
    if django_cache.get(cache_key):
        return 0
    django_cache.set(cache_key, 1, timeout=7200)

    today_start = now_time.replace(hour=0, minute=0, second=0, microsecond=0)
    active = set(await _active_chat_ids())
    with_games = await _chats_with_games_since(today_start)
    targets = [cid for cid in active if cid in with_games]

    text = (
        "⏰ یک دقیقه تا پایان روز!\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 آمار روزانه تا لحظهٔ ۱۲ شب ارسال می‌شود.\n"
        "🔄 بعد از نیمه‌شب، آمار امروز ریست می‌شود و روز جدید شروع می‌گردد."
    )
    sem = asyncio.Semaphore(_SEND_CONCURRENCY)
    sent = 0

    async def _one(chat_id: int):
        nonlocal sent
        async with sem:
            try:
                await bot.send_message(int(chat_id), text)
                sent += 1
            except Exception:
                logger.exception("midnight warning error for %s", chat_id)

    if targets:
        await asyncio.gather(*[_one(cid) for cid in targets])
    return sent


async def send_midnight_stats_for_chat(
    bot,
    chat_id: int,
    *,
    day_start,
    day_end,
    force: bool = False,
    test: bool = False,
) -> bool:
    """ارسال آمار + جوایز برای یک گپ. True اگر پیام ارسال شد."""
    from account.models import DiceGameHistory
    from bot.dice_stats_fmt import format_dice_game_stats
    from bot.stat_prizes import get_group_prizes, pay_and_format_daily_prizes

    chat_id = int(chat_id)
    day_key = localtime(day_start).strftime("%Y-%m-%d")
    cache_key = f"tg_midnight_stats_chat:{chat_id}:{day_key}"
    if not force and not test:
        if not django_cache.add(cache_key, 1, timeout=86400):
            return False

    records = await sync_to_async(list)(
        DiceGameHistory.objects.filter(
            telegram_chat_id=chat_id,
            created_at__gte=day_start,
            created_at__lt=day_end,
        )
    )
    if not records:
        if not test and not force:
            django_cache.set(cache_key, 1, timeout=86400)
        return False

    all_ids = list({int(rec.telegram_user_id) for rec in records})
    name_map = await _name_map_for_chat(bot, chat_id, all_ids)
    date_j = jdatetime.datetime.fromgregorian(datetime=localtime(day_start)).strftime("%Y/%m/%d")
    title = f"🌙 آمار روزانه تاسینو · 📅 {date_j}"
    if test:
        title = f"🧪 تست نیمه‌شب · {title}"

    prizes = await get_group_prizes(chat_id)
    text = format_dice_game_stats(records, title, name_map, prizes=prizes)
    payout = await pay_and_format_daily_prizes(
        bot, chat_id, records, name_map,
        day_key=day_key, pay=not test,
    )
    if payout:
        text += payout
    if test:
        text += "\n⚠️ این یک تست است (فرض: الان ۱۲ شب)."
    else:
        text += "\n📊 برای جزئیات بیشتر: «آمار تاس»"

    await bot.send_message(chat_id, text, parse_mode="HTML")
    if not test:
        django_cache.set(cache_key, 1, timeout=86400)
    return True


def _midnight_window(now_time=None, *, simulate_now: bool = False):
    """بازهٔ روز تمام‌شده برای آمار نیمه‌شب یا تست."""
    now_time = now_time or localtime()
    if simulate_now:
        day_start = now_time.replace(hour=0, minute=0, second=0, microsecond=0)
        return day_start, now_time
    day_end = now_time.replace(hour=0, minute=0, second=0, microsecond=0)
    # اگر دقیقاً بعد از نیمه‌شب هستیم day_end≈now؛ اگر دیر شد هم همان روز تقویمی تمام‌شده
    if now_time.hour == 0 and now_time.minute < 30:
        finished_day = day_end - datetime.timedelta(days=1)
        return finished_day, day_end
    # fallback دیرهنگام همان روز قبل
    finished_day = (now_time - datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    day_end = finished_day + datetime.timedelta(days=1)
    return finished_day, day_end


async def broadcast_midnight_stats(bot, *, only_chat_id: int | None = None) -> int:
    """ارسال آمار روزانه همهٔ گروه‌ها دقیقاً بعد از ۱۲ شب."""
    now_time = localtime()
    day_start, day_end = _midnight_window(now_time, simulate_now=False)
    day_key = localtime(day_start).strftime("%Y-%m-%d")
    global_key = f"tg_midnight_stats_sent:{day_key}"
    # قفل سراسری کوتاه فقط برای جلوگیری از دو job همزمان — ارسال per-chat جداگانه است
    lock_key = f"tg_midnight_stats_lock:{day_key}"
    if only_chat_id is None:
        if django_cache.get(lock_key):
            return 0
        django_cache.set(lock_key, 1, timeout=120)

    try:
        if only_chat_id is not None:
            targets = [int(only_chat_id)]
        else:
            active = set(await _active_chat_ids())
            with_games = await _chats_with_games_since(day_start)
            targets = [cid for cid in active if cid in with_games]

        sem = asyncio.Semaphore(_SEND_CONCURRENCY)
        sent = 0

        async def _one(cid: int):
            nonlocal sent
            async with sem:
                try:
                    ok = await send_midnight_stats_for_chat(
                        bot, cid, day_start=day_start, day_end=day_end
                    )
                    if ok:
                        sent += 1
                except Exception:
                    logger.exception("midnight stats error for %s", cid)

        if targets:
            await asyncio.gather(*[_one(cid) for cid in targets])
        if only_chat_id is None:
            django_cache.set(global_key, 1, timeout=86400)
        return sent
    finally:
        if only_chat_id is None:
            django_cache.delete(lock_key)


async def run_midnight_stats_test(bot, chat_id: int) -> str:
    """فرض می‌کند الان ۱۲ شب است — آمار امروز تا الان + جوایز برای همین گپ."""
    now_time = localtime()
    day_start, day_end = _midnight_window(now_time, simulate_now=True)
    try:
        ok = await send_midnight_stats_for_chat(
            bot,
            int(chat_id),
            day_start=day_start,
            day_end=day_end,
            force=True,
            test=True,
        )
    except Exception:
        logger.exception("midnight stats test error for %s", chat_id)
        return "❌ خطا در تست آمار نیمه‌شب."
    if not ok:
        return "📭 برای امروز مسابقه‌ای ثبت نشده؛ چیزی برای ارسال نبود."
    return "✅ تست آمار نیمه‌شب برای این گروه ارسال شد."


# سازگاری با importهای قدیمی
async def midnight_warn_then_stats(bot) -> None:
    """دیگر sleep نمی‌کند — فقط هشدار؛ آمار job جداگانه ۰۰:۰۰ است."""
    try:
        await broadcast_midnight_warning(bot)
    except Exception:
        logger.exception("midnight_warn_then_stats error")
