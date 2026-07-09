import os
import random
import string
from datetime import timedelta

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from asgiref.sync import sync_to_async
from django.utils import timezone

from account.models import License, TelegramGroup, TelegramGroupMember
from bot import cache

router = Router()

BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0"))


def _is_owner(user_id: int) -> bool:
    return user_id == BOT_OWNER_ID


def _gen_code(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ─── Generate Code (owner only, private) ─────────────────────────────────────

@router.message(F.chat.type == "private", F.text.lower().startswith("code "))
async def generate_code(message: Message):
    if not _is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("فرمت: code [روز] [user_id اختیاری]")
        return

    try:
        days = int(parts[1])
    except ValueError:
        await message.reply("تعداد روز اشتباه است.")
        return

    code = _gen_code()

    @sync_to_async
    def _save():
        License.objects.create(
            code=code,
            duration_days=days,
            created_by=message.from_user.id,
        )

    await _save()
    await message.reply(
        f"✅ کد ایجاد شد:\n\n`{code}`\n\nمدت: {days} روز",
        parse_mode="Markdown",
    )


# ─── Delete Code (owner only) ────────────────────────────────────────────────

@router.message(F.chat.type == "private", F.text.lower().startswith("delcode "))
async def delete_code(message: Message):
    if not _is_owner(message.from_user.id):
        return

    code = message.text.split(None, 1)[1].strip().upper()

    @sync_to_async
    def _delete():
        return License.objects.filter(code=code).delete()

    deleted, _ = await _delete()
    if deleted:
        await message.reply(f"🗑 کد `{code}` حذف شد.", parse_mode="Markdown")
    else:
        await message.reply(f"❌ کدی با این مقدار پیدا نشد.")


# ─── Check Code (owner only) ─────────────────────────────────────────────────

@router.message(F.chat.type == "private", F.text.lower().func(
    lambda t: t.startswith("checkcode ") or t.startswith("info ")
))
async def check_code(message: Message):
    if not _is_owner(message.from_user.id):
        return

    code = message.text.split(None, 1)[1].strip().upper()

    @sync_to_async
    def _get():
        try:
            return License.objects.select_related("used_by_group").get(code=code)
        except License.DoesNotExist:
            return None

    lic = await _get()
    if not lic:
        await message.reply("❌ کدی پیدا نشد.")
        return

    status = "✅ استفاده شده" if lic.is_used else "⏳ استفاده نشده"
    text = (
        f"🔑 کد: `{lic.code}`\n"
        f"مدت: {lic.duration_days} روز\n"
        f"وضعیت: {status}\n"
        f"ساخته شده: {lic.created_at.strftime('%Y-%m-%d')}"
    )
    if lic.is_used and lic.used_by_group:
        text += f"\nگروه: {lic.used_by_group}"

    await message.reply(text, parse_mode="Markdown")


# ─── Activate Code (in group) ────────────────────────────────────────────────

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.lower().startswith("فعال "))
async def activate_code(message: Message):
    from aiogram.enums import ChatMemberStatus

    sender = message.from_user
    m = await message.bot.get_chat_member(message.chat.id, sender.id)
    if m.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        return

    code = message.text.split(None, 1)[1].strip().upper()
    cid = message.chat.id

    @sync_to_async
    def _activate():
        try:
            lic = License.objects.get(code=code, is_used=False)
        except License.DoesNotExist:
            return None, "کد نامعتبر یا قبلاً استفاده شده."

        group, _ = TelegramGroup.objects.get_or_create(
            telegram_chat_id=cid,
            defaults={"name": message.chat.title},
        )
        until = timezone.now() + timedelta(days=lic.duration_days)
        group.subscription_until = until
        group.is_active = True
        group.save(update_fields=["subscription_until", "is_active"])

        lic.is_used = True
        lic.used_by_group = group
        lic.used_by_owner = sender.id
        lic.used_at = timezone.now()
        lic.save()

        TelegramGroupMember.objects.update_or_create(
            telegram_chat_id=cid,
            telegram_user_id=sender.id,
            defaults={"group": group, "is_admin": True, "role": "admin"},
        )

        return until, None

    until, error = await _activate()
    if error:
        await message.reply(f"❌ {error}")
        return

    from bot.helpers import sync_telegram_roles
    await sync_telegram_roles(message.chat.id, message.bot)

    await message.reply(
        f"✅ گروه فعال شد!\n"
        f"📅 انقضا: {until.strftime('%Y-%m-%d')}",
    )
