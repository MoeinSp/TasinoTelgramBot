"""چالش‌های گروهی — منطق مشترک، پورت‌شده از rubpy/bot/challenges.py برای تلگرام."""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import timedelta

import jdatetime
from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_precise_settle_tasks: set[int] = set()

TYPE_LABELS = {
    "dice": "🎲 چالش تاس",
    "dart": "🎯 چالش دارت",
    "luck": "🍀 چالش شانس",
    "football": "⚽ چالش فوتبال",
    "basketball": "🏀 چالش بسکتبال",
    "max_bet": "💰 بیشترین مبلغ ورودی",
    "max_count": "🎲 بیشترین تعداد",
    "max_increase": "📈 بیشترین افزایش موجودی",
    "sum_increase": "📊 مجموع افزایش موجودی",
}

# بازی‌های سرگرمی = مسابقهٔ «اولین نفر» (بدون مدت)
FUN_TYPES = frozenset({"dice", "dart", "luck", "football", "basketball"})
METRIC_BEST = frozenset({"max_bet", "max_increase"})
METRIC_COUNT = frozenset({"max_count"})
DART_POINTS = {1: 10, 2: 25, 3: 50, 4: 100}

# شرط برد برای چالش‌های race
RACE_RULES = {
    "dice": ("اولین نفری که تاس ۶ بیاورد", lambda s: int(s) == 6),
    "dart": ("اولین نفری که دارت وسط بزند", lambda s: int(s) == 100),
    "luck": ("اولین نفری که شانس بالای ۹۰ بیاورد", lambda s: int(s) > 90),
    "football": ("اولین نفری که گل بزند", lambda s: int(s) == 1),
    "basketball": ("اولین نفری که توپش داخل سبد بیفتد", lambda s: int(s) == 1),
}

# دستور بازی در گروه برای هر نوع چالش race
RACE_HOW_TO = {
    "dice": (
        "📝 نحوه شرکت:\n"
        "• در گروه بنویسید: <code>تاس</code>\n"
        "• اولین نفری که <b>۶</b> بیاورد برنده است."
    ),
    "dart": (
        "📝 نحوه شرکت:\n"
        "• در گروه بنویسید: <code>دارت</code>\n"
        "• اولین نفری که <b>وسط</b> بزند برنده است."
    ),
    "luck": (
        "📝 نحوه شرکت:\n"
        "• در گروه بنویسید: <code>شانس</code>\n"
        "• اولین نفری که شانس <b>بالای ۹۰</b> بیاورد برنده است."
    ),
    "football": (
        "📝 نحوه شرکت:\n"
        "• در گروه بنویسید: <code>پنالتی</code>\n"
        "• اولین نفری که <b>گل</b> بزند برنده است."
    ),
    "basketball": (
        "📝 نحوه شرکت:\n"
        "• در گروه بنویسید: <code>بسکتبال</code>\n"
        "• اولین نفری که توپش <b>داخل سبد</b> بیفتد برنده است."
    ),
}

# پایان ظاهری برای race تا فیلد end_at خالی نماند (تسویه زمانی ندارند)
_RACE_OPEN_DAYS = 3650


def type_label(challenge_type: str) -> str:
    return TYPE_LABELS.get(challenge_type, challenge_type)


def is_race_type(challenge_type: str) -> bool:
    return challenge_type in FUN_TYPES


# دستور گروه → نوع چالش race (برای نادیده گرفتن خاموشی دستور هنگام چالش فعال)
RACE_CMD_TO_TYPE = {
    "تاس": "dice",
    "دارت": "dart",
    "شانس": "luck",
    "پنالتی": "football",
    "بسکتبال": "basketball",
}


def race_type_for_command(cmd: str) -> str | None:
    return RACE_CMD_TO_TYPE.get((cmd or "").strip())


def has_active_race_challenge_sync(chat_id, game_type: str) -> bool:
    """آیا چالش race فعال (شروع‌شده، تسویه‌نشده) برای این بازی در گروه هست؟"""
    if game_type not in FUN_TYPES:
        return False
    from account.models import GroupChallenge

    now = timezone.now()
    return GroupChallenge.objects.filter(
        telegram_chat_id=int(chat_id),
        challenge_type=game_type,
        status="active",
        settled=False,
        start_at__lte=now,
    ).exists()


has_active_race_challenge = sync_to_async(has_active_race_challenge_sync)


def race_rule_text(challenge_type: str) -> str:
    rule = RACE_RULES.get(challenge_type)
    return rule[0] if rule else ""


def race_qualifies(challenge_type: str, score: int) -> bool:
    rule = RACE_RULES.get(challenge_type)
    if not rule:
        return False
    try:
        return bool(rule[1](score))
    except Exception:
        return False


def _today_start():
    now = timezone.localtime()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _fmt_dt(dt) -> str:
    if not dt:
        return "—"
    local = timezone.localtime(dt)
    j = jdatetime.datetime.fromgregorian(datetime=local)
    return j.strftime("%Y/%m/%d  %H:%M")


def race_how_to(challenge_type: str) -> str:
    return RACE_HOW_TO.get(challenge_type, "")


def format_challenge_announce(ch, *, started: bool = False) -> str:
    head = "🚀 چالش شروع شد!" if started else "🏆 چالش جدید"
    lines = [
        head,
        "━━━━━━━━━━━━━━━━━━",
        f"{type_label(ch.challenge_type)}",
        f"🎁 جایزه: {int(ch.prize_amount):,} واحد",
    ]
    if is_race_type(ch.challenge_type):
        lines.append(f"🕐 زمان شروع: {_fmt_dt(ch.start_at)}")
        rule = race_rule_text(ch.challenge_type)
        if rule:
            lines.append(f"🏁 شرط برد: {rule}")
    else:
        lines.append(f"🕐 زمان شروع: {_fmt_dt(ch.start_at)}")
        lines.append(f"🕔 پایان: {_fmt_dt(ch.end_at)}")
    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        "📌 شرایط شرکت:",
    ])
    conds = []
    if int(ch.min_games_today or 0) > 0:
        conds.append(f"• حداقل {int(ch.min_games_today)} مسابقه تاس امروز")
    if int(ch.min_wallet or 0) > 0:
        conds.append(f"• حداقل موجودی کیف پول: {int(ch.min_wallet):,}")
    if not conds:
        conds.append("• بدون محدودیت — همه می‌توانند شرکت کنند")
    lines.extend(conds)
    lines.append("━━━━━━━━━━━━━━━━━━")
    if is_race_type(ch.challenge_type):
        how = race_how_to(ch.challenge_type)
        if how:
            lines.append(how)
            lines.append("━━━━━━━━━━━━━━━━━━")
        lines.extend([
            "⚡ اولین نفری که شرط را انجام دهد برنده است.",
            "🔒 چالش بلافاصله بسته می‌شود و جایزه فقط به یک نفر داده می‌شود.",
        ])
    else:
        if ch.challenge_type == "max_count":
            lines.extend([
                "ℹ️ هر بار در مسابقه تاس با شرط شرکت کنید، ۱ بازی به تعدادتان اضافه می‌شود.",
                "🏅 در پایان، نفر(های) با بیشترین تعداد بازی جایزه را می‌گیرند (تساوی = تقسیم).",
            ])
        elif ch.challenge_type == "max_bet":
            lines.extend([
                "ℹ️ با شرکت در مسابقه تاس با شرط، بالاترین مبلغ ورودی شما ثبت می‌شود "
                "(در حالت فیکس و اضافه، مبلغی که از کیف کم می‌شود ملاک است).",
                "🏅 در پایان، نفر(های) با بیشترین ورودی جایزه را می‌گیرند (تساوی = تقسیم).",
            ])
        else:
            lines.extend([
                "ℹ️ با انجام بازی مربوطه در بازه زمانی، امتیازت ثبت می‌شود.",
                "🏅 در پایان، برنده جایزه را از مالک گروه دریافت می‌کند.",
            ])
    return "\n".join(lines)


def _metric_label(challenge_type: str) -> str:
    if challenge_type in ("max_bet", "max_increase", "sum_increase"):
        return "مبلغ"
    if challenge_type == "max_count":
        return "تعداد بازی"
    return "امتیاز"


def _metric_unit(challenge_type: str) -> str:
    return "بازی" if challenge_type == "max_count" else "واحد"


def format_challenge_end_warning(
    ch,
    leader_names: str = "",
    *,
    score: int = 0,
    leader_count: int = 0,
) -> str:
    lines = [
        "⏰ یک دقیقه تا پایان چالش!",
        "━━━━━━━━━━━━━━━━━━",
        f"{type_label(ch.challenge_type)}",
        f"🎁 جایزه: {int(ch.prize_amount or 0):,} واحد",
        "━━━━━━━━━━━━━━━━━━",
        "⏳ فقط ۶۰ ثانیه تا اعلام نتیجه نهایی باقی مانده.",
    ]
    if leader_names and int(score or 0) > 0:
        label = "برندگان تا این لحظه" if int(leader_count or 0) > 1 else "برنده تا این لحظه"
        lines.append(f"🏆 {label}: {leader_names}")
        lines.append(
            f"📊 {_metric_label(ch.challenge_type)} فعلی: "
            f"{int(score):,} {_metric_unit(ch.challenge_type)}"
        )
        lines.append("⚡ هنوز فرصت داری رکورد را جابه‌جا کنی!")
    else:
        lines.append("📭 هنوز رکوردی ثبت نشده — همین الان شرکت کن!")
    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        "🏁 دقیقاً یک دقیقه دیگر چالش تمام می‌شود و جایزه واریز می‌شود.",
    ])
    return "\n".join(lines)


def format_challenge_winner(
    ch,
    winner_name: str,
    *,
    winner_count: int = 1,
    prize_each: int | None = None,
) -> str:
    prize_total = int(ch.prize_amount or 0)
    each = int(prize_each if prize_each is not None else prize_total)
    if is_race_type(ch.challenge_type):
        score_line = ""
        if ch.challenge_type == "luck":
            score_line = f"🍀 شانس: {int(ch.winner_score)}\n"
        elif ch.challenge_type == "dice":
            score_line = f"🎲 تاس: {int(ch.winner_score)}\n"
        elif ch.challenge_type == "dart":
            score_line = f"🎯 امتیاز دارت: {int(ch.winner_score)}\n"
        return (
            "🏁 چالش پایان یافت و برنده مشخص شد!\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{type_label(ch.challenge_type)}\n"
            f"🎉 برنده: {winner_name}\n"
            f"{score_line}"
            f"🎁 جایزه: {prize_total:,} واحد\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ جایزه به کیف پول برنده واریز شد"
        )
    metric = "امتیاز"
    if ch.challenge_type in ("max_bet", "max_increase", "sum_increase"):
        metric = "مبلغ"
    elif ch.challenge_type == "max_count":
        metric = "تعداد بازی"
    if winner_count > 1:
        return (
            "🏅 پایان چالش\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{type_label(ch.challenge_type)}\n"
            f"👤 برندگان ({winner_count}): {winner_name}\n"
            f"📊 {metric}: {int(ch.winner_score):,}\n"
            f"🎁 جایزه کل: {prize_total:,} واحد\n"
            f"💸 سهم هر نفر: {each:,} واحد\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✅ جایزه بین برندگان تقسیم و به کیف پول‌ها اضافه شد"
        )
    return (
        "🏅 پایان چالش\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{type_label(ch.challenge_type)}\n"
        f"👤 برنده: {winner_name}\n"
        f"📊 {metric}: {int(ch.winner_score):,}\n"
        f"🎁 جایزه: {prize_total:,} واحد\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ جایزه به کیف پول برنده اضافه شد"
    )


def format_challenge_no_winner(ch) -> str:
    return (
        "🏁 پایان چالش\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"{type_label(ch.challenge_type)}\n"
        "📭 شرکت‌کننده‌ای ثبت نشد؛ جایزه‌ای پرداخت نشد."
    )


def _plays_today(chat_id, user_id, game_type: str) -> int:
    """تعداد مسابقات تاس امروز — همان مبنای «آمار تاس امروز»."""
    return _dice_matches_today(chat_id, user_id)


def _dice_matches_today(chat_id, user_id) -> int:
    """تعداد رکوردهای DiceGameHistory کاربر در گروه برای امروز."""
    from account.models import DiceGameHistory

    return DiceGameHistory.objects.filter(
        telegram_chat_id=int(chat_id),
        telegram_user_id=int(user_id),
        created_at__gte=_today_start(),
    ).count()


def _wallet_balance(chat_id, user_id) -> int:
    """موجودی کیف پول گروه از TelegramGroupMember.point."""
    from account.models import TelegramGroupMember

    m = TelegramGroupMember.objects.filter(
        telegram_chat_id=int(chat_id), telegram_user_id=int(user_id),
    ).first()
    return int(getattr(m, "point", 0) or 0) if m else 0


def _game_cmd_label(challenge_type: str) -> str:
    return {
        "dice": "تاس",
        "dart": "دارت",
        "luck": "شانس",
        "football": "پنالتی",
        "basketball": "بسکتبال",
    }.get(challenge_type, "بازی")


def check_eligibility(ch, user_id, *, exclude_latest_play: bool = False) -> tuple[bool, str]:
    """
    بررسی محدودیت‌های چالش.
    حداقل بازی = تعداد مسابقات تاس امروز (DiceGameHistory)،
    همان چیزی که در «آمار تاس امروز» شمرده می‌شود — حتی برای چالش دارت/فوتبال/...
    """
    uid = int(user_id)
    chat_id = int(ch.telegram_chat_id)

    if int(ch.min_wallet or 0) > 0:
        bal = _wallet_balance(chat_id, uid)
        need = int(ch.min_wallet)
        if bal < need:
            return False, (
                "⛔️ شرایط شرکت در چالش برقرار نیست\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"💳 موجودی شما: {bal:,}\n"
                f"📌 حداقل موجودی لازم: {need:,}\n\n"
                "محدودیت موجودی کیف پول برای این چالش فعال است."
            )

    if int(ch.min_games_today or 0) > 0:
        need = int(ch.min_games_today)
        plays = _dice_matches_today(chat_id, uid)
        # exclude_latest_play فقط وقتی خود مسابقه تاس همین لحظه ثبت شده معنا دارد؛
        # برای بازی‌های سرگرمی (دارت/فوتبال/...) نباید کم شود.
        if exclude_latest_play and not is_race_type(getattr(ch, "challenge_type", "") or ""):
            plays = max(0, plays - 1)
        if plays < need:
            return False, (
                "⛔️ شرایط شرکت در چالش برقرار نیست\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"🎲 مسابقات تاس امروز شما: {plays}\n"
                f"📌 حداقل لازم: {need}\n\n"
                f"اول باید حداقل {need} مسابقه تاس امروز بازی کرده باشید "
                f"(همان آمار «تاس امروز»)، بعد در چالش شرکت کنید."
            )
    return True, ""


def _winner_metric(ch, entry) -> int:
    if ch.challenge_type in METRIC_BEST:
        return int(entry.best_score or 0)
    if ch.challenge_type in METRIC_COUNT:
        return int(entry.total_score or 0)
    return int(entry.total_score or 0)


@sync_to_async
def create_challenge(
    chat_id,
    created_by,
    challenge_type: str,
    prize_amount: int,
    duration_hours: int = 24,
    min_games_today: int = 0,
    min_wallet: int = 0,
    publish_delay_minutes: int = 0,
    publish_clock: str | None = None,
):
    from account.models import GroupChallenge

    start = resolve_publish_start(
        publish_delay_minutes=publish_delay_minutes,
        publish_clock=publish_clock,
    )
    if is_race_type(challenge_type):
        end = start + timedelta(days=_RACE_OPEN_DAYS)
    else:
        end = start + timedelta(hours=max(1, int(duration_hours or 24)))
    # فقط وقتی زمان‌بندی شده (ساعت یا تأخیر)، پیام جداگانه «شروع شد» لازم است
    scheduled = bool(normalize_publish_clock(publish_clock)) or int(publish_delay_minutes or 0) > 0
    ch = GroupChallenge.objects.create(
        telegram_chat_id=int(chat_id),
        created_by=int(created_by),
        challenge_type=challenge_type,
        prize_amount=max(0, int(prize_amount)),
        min_games_today=max(0, int(min_games_today)),
        min_wallet=max(0, int(min_wallet)),
        start_at=start,
        end_at=end,
        status="active",
        announce_message_id=None if scheduled else 1,
    )
    return ch


def resolve_publish_start(*, publish_delay_minutes: int = 0, publish_clock: str | None = None):
    """شروع چالش: الان / تأخیر دقیقه‌ای / ساعت دلخواه مثل 13:30."""
    clock = normalize_publish_clock(publish_clock)
    if clock:
        hour, minute = map(int, clock.split(":"))
        now_local = timezone.localtime()
        start_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if start_local <= now_local:
            start_local = start_local + timedelta(days=1)
        return start_local
    delay = max(0, int(publish_delay_minutes or 0))
    return timezone.now() + timedelta(minutes=delay)


def normalize_publish_clock(value) -> str:
    """خروجی استاندارد HH:MM یا رشته خالی."""
    raw = str(value or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if not raw:
        return ""
    raw = raw.replace(".", ":").replace("-", ":").replace(" ", "")
    import re
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if not m:
        m = re.fullmatch(r"(\d{2})(\d{2})", raw)
    if not m:
        return ""
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def parse_publish_clock_input(text: str) -> str | None:
    """اگر معتبر باشد HH:MM برمی‌گرداند؛ وگرنه None."""
    clock = normalize_publish_clock(text)
    return clock or None


@sync_to_async
def list_active_challenges(chat_id, limit: int = 10):
    from account.models import GroupChallenge

    return list(
        GroupChallenge.objects.filter(
            telegram_chat_id=int(chat_id), status="active",
        ).order_by("-created_at")[:limit]
    )


@sync_to_async
def get_challenge(challenge_id: int):
    from account.models import GroupChallenge

    return GroupChallenge.objects.filter(id=int(challenge_id)).first()


@sync_to_async
def cancel_challenge(challenge_id: int, by_user, *, as_owner: bool = False) -> bool:
    from account.models import GroupChallenge

    ch = GroupChallenge.objects.filter(id=int(challenge_id), status="active").first()
    if not ch:
        return False
    if not as_owner and int(ch.created_by) != int(by_user):
        return False
    ch.status = "cancelled"
    ch.save(update_fields=["status"])
    return True


def _record_score_sync(ch, user_id, points: int, *, mode: str):
    """برمی‌گرداند: (entry|None, error, break_info|None)"""
    from django.db.models import Max
    from account.models import ChallengeEntry, GroupChallenge

    points = int(points)
    if points < 0:
        return None, "امتیاز نامعتبر", None
    ok, reason = check_eligibility(ch, user_id)
    if not ok:
        return None, reason, None

    break_info = None
    with transaction.atomic():
        locked_ch = (
            GroupChallenge.objects.select_for_update()
            .filter(id=ch.id, status="active", settled=False)
            .first()
        )
        if not locked_ch:
            return None, "چالش فعال نیست", None

        global_best = 0
        if mode == "best":
            global_best = int(
                ChallengeEntry.objects.filter(challenge=locked_ch)
                .aggregate(m=Max("best_score"))["m"]
                or 0
            )
        elif mode == "count":
            global_best = int(
                ChallengeEntry.objects.filter(challenge=locked_ch)
                .aggregate(m=Max("total_score"))["m"]
                or 0
            )

        entry, _ = ChallengeEntry.objects.select_for_update().get_or_create(
            challenge=locked_ch, telegram_user_id=int(user_id),
            defaults={"best_score": 0, "total_score": 0, "plays": 0},
        )
        if mode == "best":
            prev_personal = int(entry.best_score or 0)
            if points > prev_personal:
                entry.best_score = points
            entry.plays = int(entry.plays or 0) + 1
            if points > global_best:
                break_info = {
                    "challenge_id": locked_ch.id,
                    "chat_id": int(locked_ch.telegram_chat_id),
                    "challenge_type": locked_ch.challenge_type,
                    "user_id": int(user_id),
                    "new_score": points,
                    "prev_score": global_best,
                    "prize": int(locked_ch.prize_amount or 0),
                    "end_at": locked_ch.end_at,
                    "tied": False,
                }
            elif (
                points > 0
                and points == global_best
                and points > prev_personal
                and locked_ch.challenge_type == "max_bet"
            ):
                # ورودی برابر رکورد فعلی — رکورددار جدید هم‌سطح
                break_info = {
                    "challenge_id": locked_ch.id,
                    "chat_id": int(locked_ch.telegram_chat_id),
                    "challenge_type": locked_ch.challenge_type,
                    "user_id": int(user_id),
                    "new_score": points,
                    "prev_score": global_best,
                    "prize": int(locked_ch.prize_amount or 0),
                    "end_at": locked_ch.end_at,
                    "tied": True,
                }
        elif mode == "count":
            new_total = int(entry.total_score or 0) + max(1, points)
            entry.total_score = new_total
            entry.plays = int(entry.plays or 0) + 1
            if new_total > global_best:
                break_info = {
                    "challenge_id": locked_ch.id,
                    "chat_id": int(locked_ch.telegram_chat_id),
                    "challenge_type": locked_ch.challenge_type,
                    "user_id": int(user_id),
                    "new_score": new_total,
                    "prev_score": global_best,
                    "prize": int(locked_ch.prize_amount or 0),
                    "end_at": locked_ch.end_at,
                }
        elif mode == "sum":
            entry.total_score = int(entry.total_score or 0) + points
            if points > int(entry.best_score or 0):
                entry.best_score = points
            entry.plays = int(entry.plays or 0) + 1
        else:
            entry.total_score = int(entry.total_score or 0) + points
            if points > int(entry.best_score or 0):
                entry.best_score = points
            entry.plays = int(entry.plays or 0) + 1
        entry.save(update_fields=["best_score", "total_score", "plays", "updated_at"])
    return entry, "", break_info


_PENDING_BREAKS: list[dict] = []


def _queue_break(info: dict | None) -> None:
    if not info:
        return
    # یک اعلام برای هر رکورد؛ بازیکن دوم همان بازی دوباره صف نشود
    cid = info.get("challenge_id")
    score = int(info.get("new_score") or 0)
    for i, b in enumerate(_PENDING_BREAKS):
        if b.get("challenge_id") == cid and int(b.get("new_score") or 0) == score:
            if info.get("tied"):
                return
            _PENDING_BREAKS[i] = info
            return
    _PENDING_BREAKS.append(info)


def drain_record_breaks(chat_id=None) -> list[dict]:
    global _PENDING_BREAKS
    if chat_id is None:
        out = list(_PENDING_BREAKS)
        _PENDING_BREAKS.clear()
        return out
    cid = str(chat_id)
    kept, out = [], []
    for b in _PENDING_BREAKS:
        if str(b.get("chat_id")) == cid:
            out.append(b)
        else:
            kept.append(b)
    _PENDING_BREAKS = kept
    return out


def format_record_break(info: dict, holder_name: str) -> str:
    prev = int(info.get("prev_score") or 0)
    new = int(info.get("new_score") or 0)
    ctype = info.get("challenge_type") or ""
    prize = int(info.get("prize") or 0)
    end_at = info.get("end_at")
    holder_count = max(1, int(info.get("holder_count") or 1))
    if prev <= 0:
        head = "🆕 رکورد جدید ثبت شد!"
    elif info.get("tied") or (prev > 0 and prev == new):
        head = "🤝 این بازی با رکورد فعلی برابر شد!"
    else:
        head = "🔥 رکورد چالش شکسته شد!"
    if ctype == "max_bet":
        metric = "ورودی"
        unit = "واحد"
    elif ctype == "max_count":
        metric = "تعداد"
        unit = "بازی"
    else:
        metric = "افزایش"
        unit = "واحد"
    holder_label = f"رکوردداران ({holder_count})" if holder_count > 1 else "رکورددار"
    lines = [
        head,
        "━━━━━━━━━━━━━━━━━━",
        type_label(ctype),
        f"👤 {holder_label}: {holder_name}",
        f"📊 رکورد جدید: {new:,} {unit}",
    ]
    if prev > 0 and not (info.get("tied") or prev == new):
        lines.append(f"📉 رکورد قبلی: {prev:,} {unit}")
    elif info.get("tied") or (prev > 0 and prev == new):
        lines.append(f"📌 رکورد فعلی گروه: {new:,} {unit}")
    lines.append(f"🏷 نوع رکورد: بیشترین {metric}")
    if prize > 0:
        lines.append(f"🎁 جایزه نهایی: {prize:,} واحد")
        if holder_count > 1:
            lines.append(
                f"💸 در پایان، جایزه بین {holder_count} نفر با همین رکورد تقسیم می‌شود"
            )
    if end_at:
        lines.append(f"🕔 پایان چالش: {_fmt_dt(end_at)}")
    lines.extend([
        "━━━━━━━━━━━━━━━━━━",
        "🏆 چه کسی می‌تواند این رکورد را بشکند؟",
    ])
    return "\n".join(lines)


def try_claim_race_win_sync(ch, user_id, score: int):
    """
    قفل روی خود چالش — فقط یک نفر می‌تواند برنده شود حتی با ۱۰۰ پیام هم‌زمان.
    برمی‌گرداند: (challenge|None, status)
    status: won | miss | closed | not_started | <پیام خطای شرایط>
    """
    from account.models import ChallengeEntry, GroupChallenge

    score = int(score)
    with transaction.atomic():
        locked = (
            GroupChallenge.objects.select_for_update()
            .filter(id=ch.id)
            .first()
        )
        if not locked or locked.settled or locked.status != "active":
            return None, "closed"
        now = timezone.now()
        if now < locked.start_at:
            return None, "not_started"

        ok, reason = check_eligibility(locked, user_id, exclude_latest_play=False)
        if not ok:
            return None, reason

        entry, _ = ChallengeEntry.objects.select_for_update().get_or_create(
            challenge=locked,
            telegram_user_id=int(user_id),
            defaults={"best_score": 0, "total_score": 0, "plays": 0},
        )
        entry.plays = int(entry.plays or 0) + 1
        if score > int(entry.best_score or 0):
            entry.best_score = score
        entry.save(update_fields=["best_score", "plays", "updated_at"])

        if not race_qualifies(locked.challenge_type, score):
            return None, "miss"

        # فقط همین تراکنش برنده را ثبت می‌کند
        locked.winner_id = int(user_id)
        locked.winner_score = score
        locked.status = "ended"
        locked.settled = True
        locked.end_at = now
        locked.save(update_fields=[
            "winner_id", "winner_score", "status", "settled", "end_at",
        ])
        entry.total_score = score
        entry.save(update_fields=["total_score", "updated_at"])
        return locked, "won"


@sync_to_async
def log_fun_play(chat_id, user_id, game_type: str, score: int):
    """ثبت بازی سرگرمی. خروجی: {messages, wins}"""
    from account.models import GamePlayLog, GroupChallenge

    GamePlayLog.objects.create(
        telegram_chat_id=int(chat_id),
        telegram_user_id=int(user_id),
        game_type=game_type,
        score=int(score),
    )
    now = timezone.now()
    challenges = list(
        GroupChallenge.objects.filter(
            telegram_chat_id=int(chat_id),
            challenge_type=game_type,
            status="active",
            settled=False,
            start_at__lte=now,
        )
    )
    messages = []
    wins = []
    for ch in challenges:
        if is_race_type(ch.challenge_type):
            won_ch, status = try_claim_race_win_sync(ch, user_id, score)
            if status == "won" and won_ch:
                wins.append(won_ch)
            elif status not in ("miss", "closed", "not_started", "won") and status:
                messages.append(status)
            continue
        entry, err, _ = _record_score_sync(ch, user_id, score, mode="fun")
        if err:
            messages.append(err)
        elif entry:
            messages.append(
                f"✅ امتیاز چالش ثبت شد\n"
                f"{type_label(ch.challenge_type)}\n"
                f"🎯 این بازی: {int(score):,}\n"
                f"Σ مجموع: {int(entry.total_score):,}  |  🔝 بهترین: {int(entry.best_score):,}"
            )
    return {"messages": messages, "wins": wins}


def record_increase_silent(chat_id, user_id, amount: int) -> None:
    """فراخوانی از داخل increase_wallet (sync)."""
    from account.models import GroupChallenge

    now = timezone.now()
    amount = int(amount or 0)
    if amount <= 0:
        return
    for ch in GroupChallenge.objects.filter(
        telegram_chat_id=int(chat_id), status="active",
        start_at__lte=now, end_at__gte=now,
        challenge_type__in=("max_increase", "sum_increase"),
    ):
        mode = "best" if ch.challenge_type == "max_increase" else "sum"
        try:
            _entry, _err, break_info = _record_score_sync(ch, user_id, amount, mode=mode)
            if break_info and ch.challenge_type == "max_increase":
                _queue_break(break_info)
        except Exception:
            logger.exception("record_increase_silent failed")


def record_bet_silent(chat_id, user_id, bet_amount: int) -> None:
    """فراخوانی از داخل record_game_bet (sync) — شرط و تعداد بازی."""
    from account.models import GroupChallenge

    now = timezone.now()
    bet_amount = int(bet_amount or 0)
    if bet_amount <= 0:
        return
    for ch in GroupChallenge.objects.filter(
        telegram_chat_id=int(chat_id), challenge_type="max_bet", status="active",
        start_at__lte=now, end_at__gte=now,
    ):
        try:
            _entry, _err, break_info = _record_score_sync(ch, user_id, bet_amount, mode="best")
            if break_info:
                _queue_break(break_info)
        except Exception:
            logger.exception("record_bet_silent failed")

    for ch in GroupChallenge.objects.filter(
        telegram_chat_id=int(chat_id), challenge_type="max_count", status="active",
        start_at__lte=now, end_at__gte=now,
    ):
        try:
            _entry, _err, break_info = _record_score_sync(ch, user_id, 1, mode="count")
            if break_info:
                _queue_break(break_info)
        except Exception:
            logger.exception("record_count_silent failed")


def _entry_user_id(entry) -> int:
    return int(getattr(entry, "telegram_user_id", None) or getattr(entry, "user_id", 0) or 0)


def _pick_winners(ch) -> tuple[list, int]:
    """همهٔ نفرات با بهترین امتیاز مساوی (بدون تکرار شناسه)."""
    entries = list(ch.entries.all())
    if not entries:
        return [], 0
    best_val = max(_winner_metric(ch, e) for e in entries)
    if best_val <= 0:
        return [], 0
    winners = []
    seen: set[int] = set()
    for e in entries:
        if _winner_metric(ch, e) != best_val:
            continue
        uid = _entry_user_id(e)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        winners.append(e)
    return winners, best_val


def _pick_winner(ch):
    """سازگاری قدیمی: اولین برنده از بین مساوی‌ها."""
    winners, score = _pick_winners(ch)
    if not winners:
        return None, 0
    return winners[0], score


def get_tied_winner_ids_sync(ch) -> list[int]:
    """شناسه برندگان با امتیاز برابر winner_score (یا بهترین فعلی)."""
    score = int(getattr(ch, "winner_score", 0) or 0)
    winners, best = _pick_winners(ch)
    if score > 0 and best != score:
        # بعد از تسویه، فقط کسانی که دقیقاً همان امتیاز ثبت‌شده را دارند
        out: list[int] = []
        seen: set[int] = set()
        for e in ch.entries.all():
            if _winner_metric(ch, e) != score:
                continue
            uid = _entry_user_id(e)
            if uid and uid not in seen:
                seen.add(uid)
                out.append(uid)
        return out
    return [_entry_user_id(e) for e in winners]


def get_score_holder_ids_sync(challenge_id: int, score: int, challenge_type: str = "") -> list[int]:
    """همهٔ دارندگان یک رکورد بدون تکرار."""
    from account.models import ChallengeEntry

    score = int(score)
    if score <= 0:
        return []
    qs = ChallengeEntry.objects.filter(challenge_id=int(challenge_id))
    if challenge_type in METRIC_COUNT:
        qs = qs.filter(total_score=score)
    else:
        qs = qs.filter(best_score=score)
    ids: list[int] = []
    seen: set[int] = set()
    for uid in qs.order_by("id").values_list("telegram_user_id", flat=True):
        uid = int(uid)
        if uid not in seen:
            seen.add(uid)
            ids.append(uid)
    return ids


def settle_challenge_sync(ch, *, force: bool = False):
    """چالش زمان‌دار را می‌بندد. چالش‌های race اینجا تسویه نمی‌شوند."""
    from account.models import GroupChallenge

    with transaction.atomic():
        locked = GroupChallenge.objects.select_for_update().filter(id=ch.id).first()
        winners = []
        if not locked or locked.settled or locked.status != "active":
            return locked, False
        if is_race_type(locked.challenge_type):
            return locked, False
        if not force:
            warn_at = getattr(locked, "end_warning_sent_at", None)
            if warn_at:
                if timezone.now() < warn_at + timedelta(seconds=60):
                    return locked, False
            elif timezone.now() < locked.end_at:
                return locked, False

        winners, score = _pick_winners(locked)
        locked.status = "ended"
        locked.settled = True
        if winners:
            locked.winner_id = _entry_user_id(winners[0])
            locked.winner_score = int(score)
        locked.save(update_fields=["status", "settled", "winner_id", "winner_score"])
    return locked, bool(winners and int(locked.prize_amount or 0) > 0)


@sync_to_async
def settle_challenge(challenge_id: int, *, force: bool = False):
    from account.models import GroupChallenge

    ch = GroupChallenge.objects.filter(id=int(challenge_id)).first()
    if not ch:
        return None, False
    return settle_challenge_sync(ch, force=force)


@sync_to_async
def list_force_settle_ids(chat_id) -> list[int]:
    """چالش‌های زمان‌دار فعال گروه (برای تست/اجبار پایان)."""
    from account.models import GroupChallenge

    return list(
        GroupChallenge.objects.filter(
            telegram_chat_id=int(chat_id),
            status="active",
            settled=False,
        ).exclude(
            challenge_type__in=list(FUN_TYPES),
        ).values_list("id", flat=True)
    )


@sync_to_async
def due_challenge_ids(limit: int = 50):
    from account.models import GroupChallenge

    now = timezone.now()
    return list(
        GroupChallenge.objects.filter(
            status="active", settled=False, end_at__lte=now,
        ).exclude(
            challenge_type__in=list(FUN_TYPES),
        ).values_list("id", flat=True)[:limit]
    )


async def _mention(bot, user_id) -> str:
    try:
        chat = await bot.get_chat(int(user_id))
        name = chat.full_name or getattr(chat, "first_name", None) or str(user_id)
    except Exception:
        name = str(user_id)
    return f'<a href="tg://user?id={int(user_id)}">{html.escape(name)}</a>'


async def announce_record_breaks(bot, chat_id, breaks: list[dict] | None = None) -> int:
    breaks = breaks if breaks is not None else drain_record_breaks(chat_id)
    sent = 0
    for info in breaks:
        try:
            ctype = info.get("challenge_type") or ""
            holder_ids: list[int] = []
            if (
                ctype in METRIC_BEST or ctype in METRIC_COUNT
            ) and info.get("challenge_id") and info.get("new_score"):
                holder_ids = await sync_to_async(get_score_holder_ids_sync)(
                    int(info["challenge_id"]),
                    int(info["new_score"]),
                    ctype,
                )
            if not holder_ids:
                uid = info.get("user_id")
                if uid:
                    holder_ids = [int(uid)]
            # بدون تکرار
            uniq: list[int] = []
            seen: set[int] = set()
            for uid in holder_ids:
                uid = int(uid)
                if uid not in seen:
                    seen.add(uid)
                    uniq.append(uid)
            names = [await _mention(bot, uid) for uid in uniq]
            info = dict(info)
            info["holder_count"] = len(uniq) or 1
            text = format_record_break(info, " و ".join(names) if names else "—")
            await bot.send_message(int(chat_id), text, parse_mode="HTML")
            sent += 1
        except Exception:
            logger.exception("record break announce failed")
    return sent


async def flush_challenge_breaks(bot, chat_id) -> int:
    return await announce_record_breaks(bot, chat_id)


async def pay_and_announce_challenge(
    bot, ch, *, prepend_text: str | None = None, reply_to=None,
) -> None:
    """پرداخت جایزه + اعلام برنده در گروه (برای race و تسویه زمان‌دار)."""
    from bot import cache
    from bot.finance import increase_wallet

    if is_race_type(ch.challenge_type):
        winner_ids = [int(ch.winner_id)] if ch.winner_id else []
    else:
        winner_ids = await sync_to_async(get_tied_winner_ids_sync)(ch)
        if not winner_ids and ch.winner_id:
            winner_ids = [int(ch.winner_id)]

    prize_total = int(ch.prize_amount or 0)
    n = len(winner_ids)
    share = (prize_total // n) if n else 0
    remainder = (prize_total - share * n) if n else 0

    if n and prize_total > 0:
        payer_id = ch.created_by or cache.OWNER_CACHE.get(int(ch.telegram_chat_id))
        for i, uid in enumerate(winner_ids):
            amount = share + (remainder if i == 0 else 0)
            if amount <= 0:
                continue
            try:
                await increase_wallet(
                    ch.telegram_chat_id,
                    uid,
                    amount,
                    admin_id=payer_id,
                    description=f"جایزه چالش {type_label(ch.challenge_type)}",
                )
            except Exception:
                logger.exception("challenge prize pay failed")
    try:
        if winner_ids:
            names = [await _mention(bot, uid) for uid in winner_ids]
            text = format_challenge_winner(
                ch,
                " و ".join(names),
                winner_count=len(winner_ids),
                prize_each=share,
            )
        else:
            text = format_challenge_no_winner(ch)
        if prepend_text:
            text = f"{prepend_text.rstrip()}\n\n{text}"
        kwargs = {"parse_mode": "HTML"}
        if reply_to is not None:
            kwargs["reply_to_message_id"] = reply_to
        await bot.send_message(ch.telegram_chat_id, text, **kwargs)
    except Exception:
        logger.exception("challenge announce failed")


async def settle_due_challenges(bot) -> int:
    await notify_due_challenge_starts(bot)
    ids = await due_challenge_ids()
    done = 0
    for cid in ids:
        ch, should_pay = await settle_challenge(cid)
        if not ch:
            continue
        done += 1
        if should_pay or ch.winner_id or ch.status == "ended":
            await pay_and_announce_challenge(bot, ch)
    return done


@sync_to_async
def due_start_challenge_ids(limit: int = 50):
    """چالش‌هایی که زمان شروعشان رسیده و هنوز پیام «شروع شد» نخورده‌اند."""
    from account.models import GroupChallenge

    now = timezone.now()
    return list(
        GroupChallenge.objects.filter(
            status="active",
            settled=False,
            start_at__lte=now,
            announce_message_id__isnull=True,
        )
        .order_by("start_at")
        .values_list("id", flat=True)[:limit]
    )


@sync_to_async
def mark_challenge_start_notified(challenge_id: int) -> None:
    from account.models import GroupChallenge

    GroupChallenge.objects.filter(id=int(challenge_id)).update(announce_message_id=1)


async def notify_due_challenge_starts(bot) -> int:
    """وقتی زمان شروع برسد، پیام «چالش شروع شد» + توضیحات را می‌فرستد."""
    ids = await due_start_challenge_ids()
    done = 0
    for cid in ids:
        ch = await get_challenge(cid)
        if not ch or ch.settled or ch.status != "active":
            continue
        if ch.announce_message_id is not None:
            continue
        try:
            text = format_challenge_announce(ch, started=True)
            await bot.send_message(int(ch.telegram_chat_id), text, parse_mode="HTML")
            await mark_challenge_start_notified(cid)
            done += 1
        except Exception:
            logger.exception("challenge start announce failed id=%s", cid)
    return done


@sync_to_async
def due_end_warning_ids(limit: int = 50):
    from account.models import GroupChallenge

    now = timezone.now()
    return list(
        GroupChallenge.objects.filter(
            status="active",
            settled=False,
            end_warning_sent_at__isnull=True,
            start_at__lte=now,
            end_at__lte=now + timedelta(seconds=60),
            end_at__gt=now - timedelta(seconds=30),
        )
        .exclude(challenge_type__in=list(FUN_TYPES))
        .order_by("end_at")
        .values_list("id", flat=True)[:limit]
    )


@sync_to_async
def mark_challenge_end_warning(challenge_id: int):
    from account.models import GroupChallenge

    now = timezone.now()
    with transaction.atomic():
        locked = (
            GroupChallenge.objects.select_for_update()
            .filter(id=int(challenge_id), status="active", settled=False)
            .first()
        )
        if not locked or is_race_type(locked.challenge_type):
            return False, None
        if locked.end_warning_sent_at:
            return False, locked.end_warning_sent_at
        locked.end_warning_sent_at = now
        locked.save(update_fields=["end_warning_sent_at"])
        return True, now


@sync_to_async
def pending_precise_settle_ids(limit: int = 50):
    from account.models import GroupChallenge

    return list(
        GroupChallenge.objects.filter(
            status="active",
            settled=False,
            end_warning_sent_at__isnull=False,
        )
        .exclude(challenge_type__in=list(FUN_TYPES))
        .order_by("end_warning_sent_at")
        .values_list("id", flat=True)[:limit]
    )


@sync_to_async
def get_challenge_warning_payload(challenge_id: int):
    from account.models import GroupChallenge

    ch = GroupChallenge.objects.filter(id=int(challenge_id)).first()
    if not ch:
        return None
    leaders = []
    score = 0
    if not is_race_type(ch.challenge_type):
        winners, score = _pick_winners(ch)
        if score > 0:
            leaders = [_entry_user_id(e) for e in winners]
    return {
        "challenge": ch,
        "leaders": leaders,
        "score": int(score or 0),
    }


async def _settle_challenge_after_warning(bot, challenge_id: int, warn_at) -> None:
    try:
        if warn_at is not None:
            remaining = 60.0 - (timezone.now() - warn_at).total_seconds()
            if remaining > 0:
                await asyncio.sleep(remaining)
        else:
            await asyncio.sleep(60)
        ch, should_pay = await settle_challenge(challenge_id, force=True)
        if not ch:
            return
        if should_pay or ch.winner_id or ch.status == "ended":
            await pay_and_announce_challenge(bot, ch)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("precise challenge settle failed id=%s", challenge_id)
    finally:
        _precise_settle_tasks.discard(int(challenge_id))


def _schedule_precise_settle(bot, challenge_id: int, warn_at) -> None:
    cid = int(challenge_id)
    if cid in _precise_settle_tasks:
        return
    _precise_settle_tasks.add(cid)
    asyncio.create_task(
        _settle_challenge_after_warning(bot, cid, warn_at),
        name=f"challenge_precise_settle_{cid}",
    )


async def notify_challenge_end_warnings(bot) -> int:
    ids = await due_end_warning_ids()
    done = 0
    for cid in ids:
        marked, warn_at = await mark_challenge_end_warning(cid)
        if not marked:
            if warn_at:
                _schedule_precise_settle(bot, cid, warn_at)
            continue
        payload = await get_challenge_warning_payload(cid)
        if not payload:
            continue
        ch = payload["challenge"]
        leaders = payload["leaders"]
        score = payload["score"]
        try:
            names = ""
            if leaders:
                name_list = [await _mention(bot, uid) for uid in leaders]
                names = " و ".join(name_list)
            text = format_challenge_end_warning(
                ch,
                names,
                score=score,
                leader_count=len(leaders),
            )
            await bot.send_message(int(ch.telegram_chat_id), text, parse_mode="HTML")
            done += 1
        except Exception:
            logger.exception("challenge end warning failed id=%s", cid)
        _schedule_precise_settle(bot, cid, warn_at)
    return done


async def resume_precise_challenge_settles(bot) -> int:
    ids = await pending_precise_settle_ids()
    resumed = 0
    for cid in ids:
        payload = await get_challenge_warning_payload(cid)
        if not payload:
            continue
        warn_at = getattr(payload["challenge"], "end_warning_sent_at", None)
        _schedule_precise_settle(bot, cid, warn_at)
        resumed += 1
    return resumed


async def force_settle_chat_challenges(bot, chat_id) -> int:
    """پایان فوری همه چالش‌های زمان‌دار گروه و پرداخت جایزه."""
    ids = await list_force_settle_ids(chat_id)
    done = 0
    for cid in ids:
        ch, should_pay = await settle_challenge(cid, force=True)
        if not ch:
            continue
        done += 1
        if should_pay or ch.winner_id or getattr(ch, "status", None) == "ended":
            await pay_and_announce_challenge(bot, ch)
    return done


@sync_to_async
def challenge_fun_block_reason(chat_id, user_id, game_type: str) -> str:
    """
    اگر برای این بازی چالش فعال باشد و کاربر شرایط را نداشته باشد،
    پیام خطا برمی‌گرداند؛ وگرنه رشته خالی.
    """
    from account.models import GroupChallenge

    if game_type not in FUN_TYPES:
        return ""
    now = timezone.now()
    challenges = list(
        GroupChallenge.objects.filter(
            telegram_chat_id=int(chat_id),
            challenge_type=game_type,
            status="active",
            settled=False,
            start_at__lte=now,
        )
    )
    if not challenges:
        return ""
    for ch in challenges:
        ok, reason = check_eligibility(ch, user_id)
        if not ok:
            return reason
    return ""


async def assert_can_play_fun(bot, chat_id, user_id, game_type: str, reply_to=None) -> bool:
    """قبل از اجرای شانس/پنالتی/دارت/بسکتبال — False یعنی بازی نباید اجرا شود."""
    try:
        reason = await challenge_fun_block_reason(chat_id, user_id, game_type)
    except Exception:
        logger.exception("challenge_fun_block_reason failed")
        return True
    if not reason:
        return True
    try:
        from bot.helpers import safe_send
        await safe_send(bot, chat_id, reason, reply_to=reply_to)
    except Exception:
        try:
            await bot.send_message(chat_id, reason, reply_to_message_id=reply_to, parse_mode="HTML")
        except Exception:
            pass
    return False


async def notify_fun_game(
    bot, chat_id, user_id, game_type: str, score: int,
    reply_to=None, result_text: str | None = None,
    *, attach_result_only_on_win: bool = False,
) -> None:
    """ثبت بازی سرگرمی + اعلام فوری برندهٔ race (ادغام با نتیجه بازی در یک پیام)."""
    from bot.helpers import safe_send

    try:
        result = await log_fun_play(chat_id, user_id, game_type, score)
    except Exception:
        logger.exception("log_fun_play failed")
        if result_text and not attach_result_only_on_win:
            try:
                await safe_send(bot, chat_id, result_text, reply_to=reply_to)
            except Exception:
                pass
        return

    if isinstance(result, dict):
        messages = result.get("messages") or []
        wins = result.get("wins") or []
    else:
        messages = result or []
        wins = []

    for msg in messages:
        if not msg:
            continue
        try:
            await safe_send(bot, chat_id, msg, reply_to=reply_to)
        except Exception:
            pass

    if wins:
        first = True
        for won in wins:
            try:
                await pay_and_announce_challenge(
                    bot,
                    won,
                    prepend_text=result_text if first else None,
                    reply_to=reply_to,
                )
                first = False
            except Exception:
                logger.exception("race win announce failed")
        return

    if result_text and not attach_result_only_on_win:
        try:
            await safe_send(bot, chat_id, result_text, reply_to=reply_to)
        except Exception:
            pass


def _fmt_remaining(end_at) -> str:
    if not end_at:
        return "—"
    now = timezone.now()
    if end_at <= now:
        return "⏰ زمان تمام شده (در صف تسویه)"
    total = int((end_at - now).total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    parts = []
    if days:
        parts.append(f"{days} روز")
    if hours:
        parts.append(f"{hours} ساعت")
    if mins or not parts:
        parts.append(f"{mins} دقیقه")
    return "⏳ باقی‌مانده: " + " و ".join(parts)


@sync_to_async
def get_challenge_status_rows(chat_id) -> list[dict]:
    """چالش‌های فعال/ناتمام گروه برای دستور وضعیت."""
    from account.models import GroupChallenge

    now = timezone.now()
    challenges = list(
        GroupChallenge.objects.filter(
            telegram_chat_id=int(chat_id),
            status="active",
            settled=False,
        ).order_by("end_at", "id")
    )
    rows = []
    for ch in challenges:
        leaders: list[tuple[int, int]] = []
        if not is_race_type(ch.challenge_type):
            winners, score = _pick_winners(ch)
            if score > 0:
                leaders = [(_entry_user_id(e), score) for e in winners]
        rows.append({
            "id": ch.id,
            "type": ch.challenge_type,
            "prize": int(ch.prize_amount or 0),
            "start_at": ch.start_at,
            "end_at": ch.end_at,
            "is_race": is_race_type(ch.challenge_type),
            "started": now >= ch.start_at,
            "leaders": leaders,
            "rule": race_rule_text(ch.challenge_type) if is_race_type(ch.challenge_type) else "",
        })
    return rows


async def build_challenges_status_text(bot, chat_id) -> str:
    rows = await get_challenge_status_rows(chat_id)
    if not rows:
        return (
            "ℹ️ چالش فعالی در این گروه وجود ندارد.\n"
            "چالش‌های زمان‌دار (بیشترین شرط، افزایش، ...) و چالش‌های "
            "«اولین نفر» که هنوز برنده‌ای ندارند اینجا نمایش داده می‌شوند."
        )
    lines = [
        "📊 وضعیت چالش‌های فعال",
        "━━━━━━━━━━━━━━━━━━",
    ]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}) {type_label(row['type'])}")
        lines.append(f"🎁 جایزه: {int(row['prize']):,} واحد")
        if row["is_race"]:
            lines.append(f"🕐 شروع: {_fmt_dt(row['start_at'])}")
            if row.get("rule"):
                lines.append(f"🏁 شرط برد: {row['rule']}")
            if not row["started"]:
                lines.append("⌛ هنوز شروع نشده")
            else:
                lines.append("⚡ در جریان — منتظر اولین برنده")
        else:
            lines.append(f"🕐 شروع: {_fmt_dt(row['start_at'])}")
            lines.append(f"🕔 پایان: {_fmt_dt(row['end_at'])}")
            lines.append(_fmt_remaining(row["end_at"]))
            if not row["started"]:
                lines.append("⌛ هنوز شروع نشده")
            else:
                leaders = row.get("leaders") or []
                if not leaders:
                    lines.append("📭 هنوز رکوردی ثبت نشده")
                else:
                    score = leaders[0][1]
                    names = []
                    seen: set[int] = set()
                    for uid, _ in leaders:
                        uid = int(uid)
                        if uid in seen:
                            continue
                        seen.add(uid)
                        names.append(await _mention(bot, uid))
                    label = "رکوردداران" if len(names) > 1 else "رکورددار"
                    lines.append(f"👤 {label}: {' و '.join(names)}")
                    unit = "بازی" if row["type"] == "max_count" else "واحد"
                    lines.append(f"📊 رکورد فعلی: {int(score):,} {unit}")
                    if len(names) > 1:
                        lines.append(
                            f"💸 در پایان جایزه بین {len(names)} نفر تقسیم می‌شود"
                        )
        lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
