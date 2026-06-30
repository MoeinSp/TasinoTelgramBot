# هندلرهای گروه — این فایل دیگر استفاده نمی‌شود، همه در main_group.py است
from aiogram import Router, F
from aiogram.types import Message

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
