import asyncio
import logging
import os

import django
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNotFound
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TasinoAiogram3.settings")
django.setup()

from bot.routers import setup_routers
from bot.cache_manager import load_all_caches
from bot.scheduler import send_scheduled_logic
from bot.backup import send_auto_backup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TOKEN       = (os.getenv("BOT_TOKEN", "") or "").strip().strip('"').strip("'")
PROXY       = (os.getenv("PROXY", "") or "").strip()
USE_POLLING = os.getenv("USE_POLLING", "false").lower() in ("1", "true", "yes")

# وبهوک
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://tasino.spayerx.ir")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")  # مسیر endpoint
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


async def _build_bot_dp():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده.")

    session_kwargs = {}
    if PROXY:
        session_kwargs["proxy"] = PROXY

    bot = Bot(token=TOKEN, session=AiohttpSession(**session_kwargs))
    dp = Dispatcher()
    setup_routers(dp)
    await load_all_caches()

    # دکمه‌های اینلاینِ زمینه‌ای برای گروه (موجودی/موجودی ناکافی/نتیجه‌ی بازی).
    # قبل از Premium ثبت می‌شود (بیرونی‌تر) تا ایموجیِ دکمه‌های جدید هم پرمیوم شود.
    from bot.group_buttons_middleware import GroupContextButtonsMiddleware
    bot.session.middleware(GroupContextButtonsMiddleware())

    # ارتقای خودکارِ ایموجیِ خروجی به پرمیوم (متن HTML + دکمه‌های اینلاین)
    from bot.premium_middleware import PremiumEmojiMiddleware
    from bot.premium_text import load_emoji_map
    bot.session.middleware(PremiumEmojiMiddleware())
    try:
        await load_emoji_map(bot)
    except Exception:
        logger.exception("load premium emoji map failed (متن‌ها بدون ارتقا ادامه می‌دهند)")

    try:
        me = await bot.get_me()
    except TelegramNotFound as exc:
        hint = (
            "BOT_TOKEN نامعتبر است (Telegram 404). "
            "توکن را از @BotFather بگیر، در .env.prod فقط یک خط BOT_TOKEN= بگذار، "
            "بدون کوتیشن و فاصله اضافه. PROXY را خالی کن اگر لازم نیست."
        )
        raise RuntimeError(hint) from exc
    logger.info("بات آماده است: @%s", me.username)

    # ─── Scheduler ──────────────────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="Asia/Tehran")
    scheduler.add_job(
        send_scheduled_logic,
        "cron",
        minute="*",
        second=0,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=50,
        args=[bot],
        id="scheduled_messages",
    )
    scheduler.add_job(
        send_auto_backup,
        "interval",
        hours=3,
        max_instances=1,
        args=[bot],
        id="db_backup_3h",
        coalesce=True,
        misfire_grace_time=3600,
    )

    async def _settle_challenges_job():
        from bot.challenges import settle_due_challenges
        try:
            await settle_due_challenges(bot)
        except Exception as exc:
            logger.exception("challenge settle job: %s", exc)

    async def _challenge_start_job():
        from bot.challenges import notify_due_challenge_starts
        try:
            await notify_due_challenge_starts(bot)
        except Exception as exc:
            logger.exception("challenge start job: %s", exc)

    async def _challenge_end_warning_job():
        from bot.challenges import notify_challenge_end_warnings
        try:
            await notify_challenge_end_warnings(bot)
        except Exception as exc:
            logger.exception("challenge end warning job: %s", exc)

    scheduler.add_job(
        _settle_challenges_job,
        "interval",
        minutes=1,
        max_instances=1,
        id="challenge_settle",
    )
    scheduler.add_job(
        _challenge_start_job,
        "interval",
        seconds=5,
        max_instances=1,
        id="challenge_start_announce",
    )
    scheduler.add_job(
        _challenge_end_warning_job,
        "interval",
        seconds=5,
        max_instances=1,
        id="challenge_end_warning",
    )

    from bot.midnight_stats import broadcast_midnight_stats, broadcast_midnight_warning

    # هشدار ۲۳:۵۹ — بدون sleep (آمار job جداست)
    scheduler.add_job(
        broadcast_midnight_warning,
        "cron",
        hour=23,
        minute=59,
        second=0,
        args=[bot],
        id="midnight_warn",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=90,
    )
    # آمار + جوایز دقیقاً ۰۰:۰۰
    scheduler.add_job(
        broadcast_midnight_stats,
        "cron",
        hour=0,
        minute=0,
        second=0,
        args=[bot],
        id="midnight_stats",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )
    # اگر ۰۰:۰۰ از دست رفت
    scheduler.add_job(
        broadcast_midnight_stats,
        "cron",
        hour=0,
        minute=1,
        second=0,
        args=[bot],
        id="midnight_stats_fallback",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=600,
    )

    async def _weekly_league_reset_job():
        from bot.league import weekly_league_reset_job
        try:
            await weekly_league_reset_job(bot)
        except Exception as exc:
            logger.exception("weekly league reset job: %s", exc)

    scheduler.add_job(
        _weekly_league_reset_job,
        "cron",
        day_of_week="sat",
        hour=0,
        minute=0,
        second=20,
        id="weekly_league_reset",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    from bot.backup_schedule import set_scheduler
    set_scheduler(scheduler)
    try:
        from bot.challenges import resume_precise_challenge_settles
        await resume_precise_challenge_settles(bot)
    except Exception:
        logger.exception("resume precise challenge settles failed")
    logger.info(
        "Scheduler فعال شد (پیام زمان‌بندی‌شده هر ۱ دقیقه · بکاپ هر ۳ ساعت · "
        "هشدار پایان چالش · آمار نیمه‌شب)"
    )
    # ────────────────────────────────────────────────────────────────────────

    return bot, dp


async def run_polling():
    bot, dp = await _build_bot_dp()
    logger.info("حالت: Polling")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


async def run_webhook():
    if not WEBHOOK_HOST:
        raise RuntimeError("WEBHOOK_HOST تنظیم نشده.")

    bot, dp = await _build_bot_dp()
    webhook_url = f"{WEBHOOK_HOST.rstrip('/')}{WEBHOOK_PATH}"
    logger.info("حالت: Webhook → %s", webhook_url)

    await bot.set_webhook(
        url=webhook_url,
        secret_token=WEBHOOK_SECRET or None,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )

    app = web.Application()
    handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET or None,
    )
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=WEBHOOK_PORT)
    await site.start()
    logger.info("Webhook server در حال اجرا: 0.0.0.0:%d%s", WEBHOOK_PORT, WEBHOOK_PATH)

    try:
        await asyncio.Event().wait()
    finally:
        await bot.delete_webhook()
        await runner.cleanup()
        await bot.session.close()


async def main():
    if USE_POLLING:
        await run_polling()
    else:
        await run_webhook()


if __name__ == "__main__":
    asyncio.run(main())
