from aiogram import Dispatcher

from bot.handlers.private import router as private_router
from bot.handlers.panel import router as panel_router
from bot.handlers.vip import router as vip_router
from bot.handlers.games import router as games_router
from bot.handlers.main_group import router as main_group_router
from bot.handlers.admin import router as admin_router
from bot.handlers.group import router as group_router
from bot.handlers.message_filter import router as filter_router
from bot.handlers.group_lifecycle import router as group_lifecycle_router
from bot.middleware import MessageTrackingMiddleware


def setup_routers(dp: Dispatcher):
    # outer middleware: دقیقاً یک بار به ازای هر پیام اجرا می‌شه
    # (inner middleware با skip() در روتر فیلتر، دو بار اجرا می‌شد و آمار دوبرابر ثبت می‌شد)
    dp.message.outer_middleware(MessageTrackingMiddleware())

    dp.include_router(private_router)
    dp.include_router(panel_router)   # callback پنل — گروه و پیوی
    dp.include_router(group_lifecycle_router)  # افزودن به گروه / ارتقا به ادمین
    # فیلترها باید قبل از بقیه اجرا بشن؛ پیام سالم با skip() به هندلرهای بعدی می‌رسه
    dp.include_router(filter_router)
    dp.include_router(vip_router)
    dp.include_router(games_router)
    dp.include_router(main_group_router)
    dp.include_router(admin_router)
    dp.include_router(group_router)
