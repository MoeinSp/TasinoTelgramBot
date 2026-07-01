"""
هندلر چرخه‌ی عضویت ربات در گروه
مسیر: افزوده شدن به گروه ← دریافت دسترسی ادمین کامل ← نصب خودکار
"""
import logging

from aiogram import Router, Bot
from aiogram.types import ChatMemberUpdated
from asgiref.sync import sync_to_async

from bot import cache
from bot.helpers import db_set_owner, db_add_admin, db_get_locks, user_mention_id, LOCK_NAMES

router = Router()
_log = logging.getLogger(__name__)

_INACTIVE_STATUSES = {"left", "kicked"}
_ADMIN_STATUSES = {"administrator", "creator"}


@sync_to_async
def _ensure_group_exists(chat_id: int) -> None:
    from account.models import TelegramGroup
    TelegramGroup.objects.get_or_create(telegram_chat_id=chat_id, defaults={"name": ""})


@router.my_chat_member()
async def on_bot_membership_change(event: ChatMemberUpdated, bot: Bot):
    if event.chat.type not in ("group", "supergroup"):
        return

    chat_id = event.chat.id
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    if old_status == new_status:
        return

    # ─── ربات تازه به گروه اضافه شد، ولی هنوز ادمین نیست ───
    if old_status in _INACTIVE_STATUSES and new_status == "member":
        await _ensure_group_exists(chat_id)
        text = (
            "🤖 ربات با موفقیت به گروه شما اضافه شد!\n\n"
            "• حال لازم است ربات را ادمین کامل گروه نمایید\n"
            "• تا فرآیند نصب و پیکربندی انجام شود"
        )
        try:
            msg = await bot.send_message(chat_id, text, parse_mode="HTML")
            cache.PENDING_SETUP_MSG[chat_id] = msg.message_id
        except Exception as e:
            _log.error("خطا در ارسال پیام خوش‌آمد نصب: %s", e)
        return

    # ─── ربات ادمین کامل شد — چه مستقیم و چه بعد از مرحله‌ی عضو ساده ───
    if old_status not in _ADMIN_STATUSES and new_status in _ADMIN_STATUSES:
        await _ensure_group_exists(chat_id)
        pending_id = cache.PENDING_SETUP_MSG.pop(chat_id, None)
        if pending_id:
            try:
                await bot.delete_message(chat_id, pending_id)
            except Exception:
                pass
        await _finish_setup(chat_id, event, bot)
        return

    # ─── ربات از گروه حذف/اخراج شد ───
    if new_status in _INACTIVE_STATUSES:
        cache.PENDING_SETUP_MSG.pop(chat_id, None)


async def _sync_real_admins(chat_id: int, owner_id: int | None, bot: Bot) -> int:
    """ادمین‌های واقعی تلگرام رو (به‌جز مالک و ربات‌ها) در دیتابیس ثبت می‌کنه و تعدادشون رو برمی‌گردونه."""
    try:
        tg_admins = await bot.get_chat_administrators(chat_id)
    except Exception:
        return 0
    count = 0
    for member in tg_admins:
        if member.user.is_bot or member.status == "creator" or member.user.id == owner_id:
            continue
        await db_add_admin(chat_id, member.user.id)
        count += 1
    return count


async def _finish_setup(chat_id: int, event: ChatMemberUpdated, bot: Bot):
    actor_id = event.from_user.id if event.from_user else None
    if actor_id:
        await db_set_owner(chat_id, actor_id)
        owner_mention = await user_mention_id(actor_id, bot, chat_id)
    else:
        owner_mention = "نامشخص"

    admin_count = await _sync_real_admins(chat_id, actor_id, bot)
    if admin_count > 0:
        admin_line = f"👮 {admin_count} ادمین گروه شناسایی و ثبت شد"
    else:
        admin_line = "⚠️ ادمینی در گروه یافت نشد!"

    locks = await db_get_locks(chat_id)
    active_locks = [LOCK_NAMES[key] for key, on in locks.items() if on and key in LOCK_NAMES]
    locks_lines = "\n".join(f"✅ قفل {name} فعال" for name in active_locks)
    locks_lines += "\n✅ خوش‌آمدگویی فعال"

    text = (
        "🔰 ربات با موفقیت در گروه نصب شد\n\n"
        "✚ مالک گروه:\n"
        f"▸ {owner_mention}\n\n"
        f"{admin_line}\n\n"
        "🛠 به‌طور پیش‌فرض قفل‌های زیر در گروه شما فعال شد:\n\n"
        f"{locks_lines}\n\n"
        "📚 برای مشاهده راهنما از دستور  راهنما  استفاده نمایید\n"
        "⚙️ برای دریافت پنل تنظیمات، دستور  پنل  را ارسال نمایید\n\n"
        "⛑ درصورت وجود هرگونه مشکل به پشتیبانی مراجعه کنید:\n"
        "@Spayers"
    )
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        _log.error("خطا در ارسال پیام تکمیل نصب: %s", e)
