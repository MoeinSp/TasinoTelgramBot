from aiogram import Dispatcher

from bot.handlers.private import router as private_router
from bot.handlers.panel import router as panel_router
from bot.handlers.vip import router as vip_router
from bot.handlers.games import router as games_router
from bot.handlers.main_group import router as main_group_router
from bot.handlers.admin import router as admin_router
from bot.handlers.group import router as group_router
from bot.handlers.message_filter import router as filter_router
from bot.middleware import MessageTrackingMiddleware


def setup_routers(dp: Dispatcher):
    # middleware روی همه پیام‌های ورودی — قبل از هر handler
    dp.message.middleware(MessageTrackingMiddleware())

    dp.include_router(private_router)
    dp.include_router(panel_router)   # callback پنل — گروه و پیوی
    dp.include_router(vip_router)
    dp.include_router(games_router)
    dp.include_router(main_group_router)
    dp.include_router(admin_router)
    dp.include_router(group_router)
    dp.include_router(filter_router)
