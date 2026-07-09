"""
هندلر چرخه‌ی عضویت ربات در گروه
مسیر: افزوده شدن به گروه ← دریافت دسترسی ادمین کامل ← نصب خودکار
"""
import logging

from aiogram import Router, Bot
from aiogram.types import ChatMemberUpdated
from asgiref.sync import sync_to_async

from bot import cache
from bot.helpers import (
    db_get_locks, user_mention_id, LOCK_NAMES,
    sync_telegram_roles, sync_bot_admins_from_telegram,
)

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
        await _finish_setup(chat_id, bot)
        return

    # ─── ربات از گروه حذف/اخراج شد ───
    if new_status in _INACTIVE_STATUSES:
        cache.PENDING_SETUP_MSG.pop(chat_id, None)


@router.chat_member()
async def on_group_member_role_change(event: ChatMemberUpdated, bot: Bot):
    """وقتی مالک یا ادمین تلگرام عوض شد، کش ربات به‌روز می‌شود."""
    if event.chat.type not in ("group", "supergroup"):
        return
    if event.new_chat_member.user.is_bot:
        return

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    if old_status == new_status:
        return

    if old_status not in ("creator", "administrator") and new_status not in ("creator", "administrator"):
        return

    chat_id = event.chat.id
    if chat_id not in cache.OWNER_CACHE and new_status != "creator":
        return

    result = await sync_telegram_roles(chat_id, bot)
    if not result.get("ok"):
        return

    if result.get("creator_changed") and result.get("creator_id"):
        try:
            mention = await user_mention_id(result["creator_id"], bot, chat_id)
            await bot.send_message(
                chat_id,
                "👑 مالک گروه به‌روز شد\n"
                "━━━━━━━━━━━━━━━━\n\n"
                f"• {mention}\n\n"
                "📌 مالک ربات همیشه با creator تلگرام یکسان است.",
                parse_mode="HTML",
            )
        except Exception as e:
            _log.error("خطا در اعلان تغییر مالک: %s", e)


async def _finish_setup(chat_id: int, bot: Bot):
    result = await sync_telegram_roles(chat_id, bot)
    creator_id = result.get("creator_id") if result.get("ok") else None

    if creator_id:
        owner_mention = await user_mention_id(creator_id, bot, chat_id)
    else:
        owner_mention = "⚠️ creator گروه یافت نشد — «همگام‌سازی» بزنید"

    admin_count = await sync_bot_admins_from_telegram(chat_id, bot, creator_id)
    if admin_count > 0:
        admin_line = f"👮 {admin_count} ادمین تلگرام در ربات ثبت شد"
    else:
        admin_line = "⚠️ ادمین تلگرامی یافت نشد"

    locks = await db_get_locks(chat_id)
    active_locks = [LOCK_NAMES[key] for key, on in locks.items() if on and key in LOCK_NAMES]
    locks_lines = "\n".join(f"✅ قفل {name} فعال" for name in active_locks)
    locks_lines += "\n✅ خوش‌آمدگویی فعال"

    text = (
        "🔰 ربات با موفقیت در گروه نصب شد\n\n"
        "✚ مالک گروه (creator تلگرام):\n"
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
