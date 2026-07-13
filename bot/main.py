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
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_scheduled_logic,
        "interval",
        minutes=1,
        max_instances=1,
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
    scheduler.start()
    logger.info("Scheduler فعال شد (پیام زمان‌بندی‌شده هر ۱ دقیقه · بکاپ هر ۳ ساعت)")
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
