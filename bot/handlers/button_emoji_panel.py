"""
پنل مالک — تنظیم آیکون ایموجی پرمیوم برای دکمه‌های شیشه‌ای.

فلو:
  «ایموجی دکمه‌ها» → لیست دسته‌ها → لیست دکمه‌های دسته → انتخاب دکمه →
  «حالا ایموجی پرمیوم را تنها بفرست» → هندلر پیامِ بعدی custom_emoji_id را ذخیره می‌کند.
  دکمه «پاک کردن» ردیف را حذف و به فالبک برمی‌گرداند.

فقط برای CREATOR_USER_ID در پیوی.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton as Btn,
)

from bot.constants import CREATOR_USER_ID
from bot import button_emoji as be
from bot.premium_emoji import tg_emoji

logger = logging.getLogger(__name__)

router = Router(name="button_emoji_panel")
router.message.filter(F.chat.type == "private")

# user_id → key در انتظار دریافت ایموجی
PENDING_BUTTON_EMOJI: dict[int, str] = {}


def _is_creator(user_id: int) -> bool:
    return int(user_id) == int(CREATOR_USER_ID)


# ─── نمای دسته‌ها ──────────────────────────────────────────────────────────
def _categories_kb() -> InlineKeyboardMarkup:
    rows = []
    for cat in be.categories():
        keys = be.keys_in_category(cat)
        done = sum(1 for k in keys if be.get_override(k))
        label = be.CATEGORY_LABELS.get(cat, cat)
        rows.append([Btn(
            text=f"{label}  ({done}/{len(keys)})",
            callback_data=f"be:cat:{cat}",
        )])
    rows.append([Btn(text="✖️ بستن", callback_data="be:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _categories_text() -> str:
    total = len(be.BUTTON_EMOJI_DEFS)
    done = sum(1 for k in be.BUTTON_EMOJI_DEFS if be.get_override(k))
    return (
        "🎨 <b>ایموجی دکمه‌ها</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"وضعیت: <b>{done}</b> از <b>{total}</b> دکمه دارای آیکون پرمیوم.\n\n"
        "یک دسته را انتخاب کن تا دکمه‌هایش را ببینی."
    )


# ─── نمای یک دسته ──────────────────────────────────────────────────────────
def _category_kb(cat: str) -> InlineKeyboardMarkup:
    rows = []
    for key in be.keys_in_category(cat):
        st = be.button_status(key)
        mark = "✅" if st["set"] else "▫️"
        rows.append([Btn(
            text=f"{mark} {st['label']}",
            callback_data=f"be:btn:{key}",
        )])
    rows.append([Btn(text="🔙 دسته‌ها", callback_data="be:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _category_text(cat: str) -> str:
    label = be.CATEGORY_LABELS.get(cat, cat)
    lines = [f"{label}\n━━━━━━━━━━━━━━━━━━━━\n"]
    for key in be.keys_in_category(cat):
        st = be.button_status(key)
        if st["set"]:
            preview = tg_emoji(st["id"], st["placeholder"])
            lines.append(f"{preview} <b>{st['label']}</b> — پرمیوم ✅")
        else:
            lines.append(f"{st['fallback']} <b>{st['label']}</b> — فالبک")
    lines.append("\nیک دکمه را برای تنظیم انتخاب کن.")
    return "\n".join(lines)


# ─── نمای یک دکمه ──────────────────────────────────────────────────────────
def _button_kb(key: str) -> InlineKeyboardMarkup:
    st = be.button_status(key)
    cat = be.BUTTON_EMOJI_DEFS[key][2]
    rows = [[Btn(text="✨ تنظیم ایموجی پرمیوم", callback_data=f"be:set:{key}")]]
    if st["set"]:
        rows.append([Btn(text="🧪 تست نمایش", callback_data=f"be:test:{key}")])
        rows.append([Btn(text="🗑 پاک کردن (بازگشت به فالبک)", callback_data=f"be:clear:{key}")])
    rows.append([Btn(text="🔙 بازگشت", callback_data=f"be:cat:{cat}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _button_text(key: str) -> str:
    st = be.button_status(key)
    if st["set"]:
        preview = tg_emoji(st["id"], st["placeholder"])
        status = (
            f"وضعیت: <b>پرمیوم</b> {preview}\n"
            f"شناسه: <code>{st['id']}</code>"
        )
    else:
        status = f"وضعیت: <b>فالبک یونیکد</b> {st['fallback']}"
    return (
        f"🔘 دکمه: <b>{st['label']}</b>\n"
        f"کلید: <code>{st['key']}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{status}"
    )


# ─── ورودی متنی ────────────────────────────────────────────────────────────
@router.message(F.text == "ایموجی دکمه‌ها")
async def open_panel(message: Message):
    if not _is_creator(message.from_user.id):
        return
    PENDING_BUTTON_EMOJI.pop(message.from_user.id, None)
    await message.answer(
        _categories_text(), reply_markup=_categories_kb(), parse_mode="HTML",
    )


# ─── ناوبری callback ───────────────────────────────────────────────────────
@router.callback_query(F.data == "be:close")
async def cb_close(cq: CallbackQuery):
    if not _is_creator(cq.from_user.id):
        return await cq.answer()
    PENDING_BUTTON_EMOJI.pop(cq.from_user.id, None)
    try:
        await cq.message.delete()
    except Exception:
        pass
    await cq.answer()


@router.callback_query(F.data == "be:home")
async def cb_home(cq: CallbackQuery):
    if not _is_creator(cq.from_user.id):
        return await cq.answer()
    await cq.message.edit_text(
        _categories_text(), reply_markup=_categories_kb(), parse_mode="HTML",
    )
    await cq.answer()


@router.callback_query(F.data.startswith("be:cat:"))
async def cb_category(cq: CallbackQuery):
    if not _is_creator(cq.from_user.id):
        return await cq.answer()
    cat = cq.data.split(":", 2)[2]
    await cq.message.edit_text(
        _category_text(cat), reply_markup=_category_kb(cat), parse_mode="HTML",
    )
    await cq.answer()


@router.callback_query(F.data.startswith("be:btn:"))
async def cb_button(cq: CallbackQuery):
    if not _is_creator(cq.from_user.id):
        return await cq.answer()
    key = cq.data.split(":", 2)[2]
    if key not in be.BUTTON_EMOJI_DEFS:
        return await cq.answer("دکمه ناشناخته", show_alert=True)
    PENDING_BUTTON_EMOJI.pop(cq.from_user.id, None)
    await cq.message.edit_text(
        _button_text(key), reply_markup=_button_kb(key), parse_mode="HTML",
    )
    await cq.answer()


@router.callback_query(F.data.startswith("be:set:"))
async def cb_set(cq: CallbackQuery):
    if not _is_creator(cq.from_user.id):
        return await cq.answer()
    key = cq.data.split(":", 2)[2]
    if key not in be.BUTTON_EMOJI_DEFS:
        return await cq.answer("دکمه ناشناخته", show_alert=True)
    PENDING_BUTTON_EMOJI[cq.from_user.id] = key
    label = be.BUTTON_EMOJI_DEFS[key][0]
    await cq.message.answer(
        f"✨ حالا ایموجیِ پرمیومِ موردنظر برای «<b>{label}</b>» را <b>تنها</b> بفرست.\n\n"
        "فقط یک ایموجی پرمیوم (custom emoji) در یک پیام.\n"
        "برای انصراف: <code>لغو ایموجی</code>",
        parse_mode="HTML",
    )
    await cq.answer()


@router.callback_query(F.data.startswith("be:clear:"))
async def cb_clear(cq: CallbackQuery):
    if not _is_creator(cq.from_user.id):
        return await cq.answer()
    key = cq.data.split(":", 2)[2]
    await be.clear_button_emoji(key)
    await cq.answer("به فالبک برگشت ✅", show_alert=False)
    await cq.message.edit_text(
        _button_text(key), reply_markup=_button_kb(key), parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("be:test:"))
async def cb_test(cq: CallbackQuery):
    if not _is_creator(cq.from_user.id):
        return await cq.answer()
    key = cq.data.split(":", 2)[2]
    st = be.button_status(key)
    if not st["set"]:
        return await cq.answer("این دکمه هنوز پرمیوم ندارد.", show_alert=True)
    test_kb = InlineKeyboardMarkup(inline_keyboard=[[
        be.btn(st["label"], key, callback_data="be:noop")
    ]])
    try:
        await cq.message.answer(
            "🧪 نمونهٔ رندرِ دکمه با آیکون پرمیوم:",
            reply_markup=test_kb,
        )
        await cq.answer("ارسال شد ✅")
    except Exception as exc:
        logger.exception("button emoji test send failed")
        await cq.answer(f"خطا در ارسال: {exc}", show_alert=True)


@router.callback_query(F.data == "be:noop")
async def cb_noop(cq: CallbackQuery):
    await cq.answer()


# ─── انصراف از دریافت ──────────────────────────────────────────────────────
@router.message(F.text == "لغو ایموجی")
async def cancel_pending(message: Message):
    if not _is_creator(message.from_user.id):
        return
    if PENDING_BUTTON_EMOJI.pop(message.from_user.id, None):
        await message.reply("لغو شد.")


# ─── دریافت ایموجی پرمیوم ──────────────────────────────────────────────────
@router.message(
    F.entities.func(lambda ents: any(getattr(e, "type", None) == "custom_emoji" for e in (ents or [])))
)
async def capture_emoji(message: Message):
    from aiogram.dispatcher.event.bases import SkipHandler
    uid = message.from_user.id
    key = PENDING_BUTTON_EMOJI.get(uid)
    if not _is_creator(uid) or not key:
        raise SkipHandler  # منتظر ورودی نیستیم — بگذار هندلرهای بعدی رسیدگی کنند

    custom_emoji_id, placeholder = be.extract_first_custom_emoji(message)
    if not custom_emoji_id:
        await message.reply("❌ ایموجی پرمیوم پیدا نشد. یک custom emoji بفرست.")
        return

    ok = await be.set_button_emoji(key, custom_emoji_id, placeholder or be.fallback_of(key))
    PENDING_BUTTON_EMOJI.pop(uid, None)
    if not ok:
        await message.reply("❌ ذخیره نشد (شناسه نامعتبر).")
        return

    st = be.button_status(key)
    preview = tg_emoji(st["id"], st["placeholder"])
    await message.reply(
        f"✅ ذخیره شد.\n\n{preview} <b>{st['label']}</b>\n"
        f"شناسه: <code>{st['id']}</code>",
        reply_markup=_button_kb(key),
        parse_mode="HTML",
    )
