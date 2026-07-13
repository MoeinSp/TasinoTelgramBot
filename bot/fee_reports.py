"""گزارش حق واسطه — متن، کیبورد اینلاین، بازه‌های زمانی (تلگرام)."""
from __future__ import annotations

import jdatetime
from aiogram import Bot
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup

from bot.finance import get_fee_report
from bot.helpers import deliver_private_or_warn, send_private, user_mention_id

_FEE_REPORT_HELP = "\n\n💡 از دکمه‌های زیر دوره گزارش را عوض کنید."

_ADMIN_DENY_TEXT = (
    "⛔️ دسترسی ندارید.\n"
    "این دستور فقط برای ادمین‌های گروه فعال است."
)

ADMIN_DENY_TEXT = _ADMIN_DENY_TEXT

_FEE_PM_SUFFIXES = frozenset({"پیوی", "پیو", "در پیوی"})
_FEE_GROUP_SUFFIXES = frozenset({
    "گروه", "همون گروه", "همین گروه", "در گروه",
})
_FEE_PERIOD_WORDS = {
    "امروز": "0",
    "دیروز": "1",
    "پریروز": "2",
    "هفته": "w",
    "هفت": "w",
    "هفت روز": "w",
    "هفت روز اخیر": "w",
    "هفته اخیر": "w",
    "این هفته": "tw",
}
_FEE_STANDALONE = {
    "هفت روز اخیر": "w",
    "این هفته": "tw",
}


def _fee_strip_delivery(parts: list[str]) -> tuple[list[str], str]:
    delivery = "group"
    if parts and parts[-1] in _FEE_PM_SUFFIXES:
        delivery = "pm"
        parts = parts[:-1]
    elif parts and parts[-1] in _FEE_GROUP_SUFFIXES:
        parts = parts[:-1]
    return parts, delivery


def _fee_period_mode(parts: list[str]) -> str | None:
    if not parts:
        return "0"
    if len(parts) == 1 and parts[0] in _FEE_PERIOD_WORDS:
        return _FEE_PERIOD_WORDS[parts[0]]
    if len(parts) == 2 and parts[0] == "هفت" and parts[1] == "روز":
        return "w"
    if len(parts) == 3 and parts[0] == "هفت" and parts[1] == "روز" and parts[2] == "اخیر":
        return "w"
    if len(parts) == 2 and parts[0] == "این" and parts[1] == "هفته":
        return "tw"
    if len(parts) == 3 and parts[1] == "روز" and parts[2] == "قبل" and parts[0].isdigit():
        off = int(parts[0])
        if 3 <= off <= 6:
            return str(off)
    return None


def parse_fee_report_command(text: str) -> tuple[str, str, int | None] | None:
    """(delivery, report_mode, admin_target) | None — پیش‌فرض گروه."""
    if not text:
        return None
    t = text.strip()
    parts = t.split()
    if not parts:
        return None

    standalone, delivery = _fee_strip_delivery(parts[:])
    standalone_key = " ".join(standalone)
    if standalone_key in _FEE_STANDALONE:
        return delivery, _FEE_STANDALONE[standalone_key], None

    suffix_parts: list[str]
    if len(parts) >= 3 and parts[0] == "گزارش" and parts[1] == "حق" and parts[2] == "واسطه":
        suffix_parts = parts[3:]
    elif len(parts) >= 2 and parts[0] == "حق" and parts[1] == "واسطه":
        suffix_parts = parts[2:]
    elif parts[0] == "کارمزد":
        if len(parts) == 1:
            return None
        suffix_parts = parts[1:]
    else:
        return None

    suffix_parts, delivery = _fee_strip_delivery(suffix_parts)

    if suffix_parts and suffix_parts[0] in ("ادمین", "ادمين", "admin"):
        admin_target = None
        rem = suffix_parts[1:]
        if rem and rem[0].isdigit():
            admin_target = int(rem[0])
        return delivery, "a", admin_target

    if len(suffix_parts) == 1 and suffix_parts[0].isdigit():
        return None

    mode = _fee_period_mode(suffix_parts)
    if mode is None:
        return None
    return delivery, mode, None


_DAY_LABELS = {0: "امروز", 1: "دیروز", 2: "پریروز"}


def jalali_date_str(greg_iso: str | None = None, day_offset: int = 0) -> str:
    if greg_iso:
        from datetime import date as _date
        y, m, d = map(int, str(greg_iso).split("-")[:3])
        return jdatetime.date.fromgregorian(date=_date(y, m, d)).strftime("%Y/%m/%d")
    return (jdatetime.date.today() - jdatetime.timedelta(days=day_offset)).strftime("%Y/%m/%d")


def _weekday_name(greg_iso: str) -> str:
    from datetime import date as _date
    y, m, d = map(int, str(greg_iso).split("-")[:3])
    names = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
    return names[_date(y, m, d).weekday()]


def _range_footer(report: dict, explanation: str) -> str:
    s = jalali_date_str(report["start_date"])
    e = jalali_date_str(report["end_date"])
    return (
        f"\n📅 بازه گزارش: {s} ({_weekday_name(report['start_date'])})"
        f" تا {e} ({_weekday_name(report['end_date'])})"
        f"\nℹ️ {explanation}"
    )


def fee_report_kb(chat_id: int) -> InlineKeyboardMarkup:
    rows = []
    for off_a, off_b in ((0, 1), (2, 3), (4, 5)):
        rows.append([
            IKB(
                text=f"{_DAY_LABELS.get(off_a, str(off_a))} {jalali_date_str(day_offset=off_a)}",
                callback_data=f"feer:{chat_id}:{off_a}",
            ),
            IKB(
                text=f"{off_b}روز قبل {jalali_date_str(day_offset=off_b)}",
                callback_data=f"feer:{chat_id}:{off_b}",
            ),
        ])
    rows.append([
        IKB(
            text=f"۶روز قبل {jalali_date_str(day_offset=6)}",
            callback_data=f"feer:{chat_id}:6",
        ),
    ])
    rows.append([
        IKB(text="📊 هفت روز اخیر", callback_data=f"feer:{chat_id}:w"),
        IKB(text="📅 این هفته", callback_data=f"feer:{chat_id}:tw"),
    ])
    rows.append([IKB(text="👮 ادمین‌ها", callback_data=f"feer:{chat_id}:a")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def fee_admin_lines(per_admin: dict, bot: Bot, chat_id: int) -> list[str]:
    if not per_admin:
        return ["• موردی ثبت نشده."]
    lines = []
    for aid, amt in sorted(per_admin.items(), key=lambda x: x[1], reverse=True):
        tag = await user_mention_id(int(aid), bot, chat_id)
        lines.append(f"• {tag}: {amt:,} واحد")
    return lines


async def build_fee_day_text(chat_id: int, bot: Bot, day_offset: int) -> str:
    report = await get_fee_report(chat_id, day_offset=day_offset)
    period = _DAY_LABELS.get(day_offset, f"{day_offset} روز قبل")
    jdate = jalali_date_str(day_offset=day_offset)
    lines = [
        f"💹 گزارش حق واسطه — {period}",
        f"📅 تاریخ شمسی: {jdate} ({_weekday_name(report['start_date'])})",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 مجموع: {report['total_fee']:,} واحد",
        "",
        "👮 سهم ادمین‌ها:",
    ]
    lines.extend(await fee_admin_lines(report["per_admin"], bot, chat_id))
    lines.append(_FEE_REPORT_HELP)
    lines.append(f"\nℹ️ فقط تراکنش‌های حق واسطه همین روز ({jdate}) در این گروه.")
    return "\n".join(lines)


async def build_fee_rolling_week_text(chat_id: int, bot: Bot) -> str:
    report = await get_fee_report(chat_id, days=7)
    lines = [
        "📊 گزارش حق واسطه — هفت روز اخیر",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 مجموع: {report['total_fee']:,} واحد",
        "",
        "📅 روز به روز (شمسی):",
    ]
    if report["per_day"]:
        for d, amt in sorted(report["per_day"].items()):
            lines.append(f"• {jalali_date_str(d)} ({_weekday_name(d)}): {amt:,} واحد")
    else:
        lines.append("• داده‌ای ثبت نشده.")
    lines.extend(["", "👮 سهم ادمین‌ها:"])
    lines.extend(await fee_admin_lines(report["per_admin"], bot, chat_id))
    lines.append(_FEE_REPORT_HELP)
    lines.append(_range_footer(
        report, "هفت روز اخیر = امروز به‌علاوه ۶ روز گذشته (۷ روز متوالی).",
    ))
    return "\n".join(lines)


async def build_fee_this_week_text(chat_id: int, bot: Bot) -> str:
    report = await get_fee_report(chat_id, this_week=True)
    lines = [
        "📅 گزارش حق واسطه — این هفته",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 مجموع این هفته: {report['total_fee']:,} واحد",
        "",
        "📅 روز به روز از شنبه:",
    ]
    if report["per_day"]:
        for d, amt in sorted(report["per_day"].items()):
            lines.append(f"• {jalali_date_str(d)} ({_weekday_name(d)}): {amt:,} واحد")
    else:
        lines.append("• از شنبه این هفته تاکنون ثبت نشده.")
    lines.extend(["", "👮 سهم ادمین‌ها:"])
    lines.extend(await fee_admin_lines(report["per_admin"], bot, chat_id))
    lines.append(_FEE_REPORT_HELP)
    lines.append(_range_footer(
        report, "این هفته از شنبه (اول هفته) شروع شده و تا همین لحظه محاسبه می‌شود.",
    ))
    return "\n".join(lines)


async def build_fee_admin_text(chat_id: int, bot: Bot, target_id: int | None = None) -> str:
    report = await get_fee_report(chat_id, days=7, target_user_id=target_id)
    if target_id:
        tag = await user_mention_id(target_id, bot, chat_id)
        lines = [
            "👮 گزارش حق واسطه ادمین",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🧑‍💼 ادمین: {tag}",
            f"💰 مجموع ۷ روز اخیر: {report['total_fee']:,} واحد",
            "",
            "📅 تفکیک تاریخ (شمسی):",
        ]
    else:
        lines = [
            "👮 گزارش حق واسطه ادمین‌ها",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💰 مجموع ۷ روز اخیر: {report['total_fee']:,} واحد",
            "",
            "👮 سهم ادمین‌ها:",
        ]
        lines.extend(await fee_admin_lines(report["per_admin"], bot, chat_id))
        lines.extend(["", "📅 تفکیک تاریخ (شمسی):"])
    if report["per_day"]:
        for d, amt in sorted(report["per_day"].items()):
            lines.append(f"• {jalali_date_str(d)}: {amt:,} واحد")
    else:
        lines.append("• داده‌ای ثبت نشده.")
    lines.append(_FEE_REPORT_HELP)
    return "\n".join(lines)


async def build_fee_text_by_mode(chat_id: int, bot: Bot, mode: str) -> str | None:
    if mode in ("0", "1", "2", "3", "4", "5", "6"):
        return await build_fee_day_text(chat_id, bot, int(mode))
    if mode == "w":
        return await build_fee_rolling_week_text(chat_id, bot)
    if mode == "tw":
        return await build_fee_this_week_text(chat_id, bot)
    if mode == "a":
        return await build_fee_admin_text(chat_id, bot)
    return None


async def send_fee_report(
    bot: Bot,
    group_chat_id: int,
    user_id: int,
    group_msg_id: int,
    mode: str,
    *,
    delivery: str = "group",
    admin_target: int | None = None,
) -> bool:
    from bot.cache_manager import is_admin, is_owner
    from bot.helpers import safe_send

    if not is_admin(group_chat_id, user_id) and not is_owner(group_chat_id, user_id):
        await safe_send(bot, group_chat_id, ADMIN_DENY_TEXT, reply_to=group_msg_id)
        return False

    if mode == "a":
        text = await build_fee_admin_text(group_chat_id, bot, admin_target)
    else:
        text = await build_fee_text_by_mode(group_chat_id, bot, mode)
    if not text:
        return False

    kb = fee_report_kb(group_chat_id)
    if delivery == "pm":
        return await deliver_private_or_warn(
            bot, group_chat_id, user_id, group_msg_id, text,
            reply_markup=kb,
        )
    await safe_send(
        bot, group_chat_id, text,
        reply_to=group_msg_id,
        reply_markup=kb,
    )
    return True


async def send_fee_report_pm(
    bot: Bot, group_chat_id: int, user_id: int, group_msg_id: int, mode: str,
) -> bool:
    return await send_fee_report(
        bot, group_chat_id, user_id, group_msg_id, mode, delivery="pm",
    )
