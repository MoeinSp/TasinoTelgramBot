"""
سرویس‌های پنل /ad — فقط CRUD روی ScheduledMessage / JoinMessage.
هر تبلیغ = دقیقاً یک ارسال یک‌باره (type=fixed).
جوین اجباری: ۱۲:۰۰ امروز → ۱۲:۰۰ فردا (Asia/Tehran).
"""
from __future__ import annotations

from datetime import datetime, timedelta, time as dtime, date

from django.db import transaction
from django.utils import timezone

from scheduledmessage.models import ScheduledMessage
from bot_setting.models import JoinMessage


TITLE_PREFIX = {
    "group": "[AD][گروه]",
    "pv": "[AD][ربات]",
    "bomb": "[AD][بمب]",
    "super": "[AD][سوپربمب]",
}
TITLE_PREFIX_CUSTOM = {
    "group": "[AD][خارج][گروه]",
    "pv": "[AD][خارج][ربات]",
    "bomb": "[AD][خارج][بمب]",
    "super": "[AD][خارج][سوپربمب]",
}
MODE_LABEL = {
    "group": "تبلیغ گروه",
    "pv": "تبلیغ ربات",
    "bomb": "بمب",
    "super": "سوپر بمب",
}
JOIN_PREFIX = "[JOIN]"
AD_PREFIX = "[AD]"
CUSTOM_MARK = "[خارج]"
# ساعت‌های ۰۰:۰۰ تا ۰۵:۵۹ روی «فردای روز برنامه» می‌نشینند (۱ شب و …)
OVERNIGHT_BEFORE_HOUR = 6
# ۲۵:۰۰ = ۱ شب فردا → فردا ساعت ۰۱:۰۰
HOUR_25 = "25:00"

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _tz():
    return timezone.get_current_timezone()


def _aware(dt: datetime):
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, _tz())
    return dt


def today_local() -> date:
    return timezone.localdate()


def parse_time(raw: str) -> str | None:
    """Accept 00:00..47:59; hours 24+ are mapped to the following day."""
    s = str(raw or "").strip().translate(_PERSIAN_DIGITS).replace(".", ":")
    if not s:
        return None
    parts = s.split(":")
    if len(parts) == 1 and parts[0].isdigit():
        h = int(parts[0])
        if 0 <= h <= 47:
            return f"{h:02d}:00"
        return None
    if len(parts) != 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
        if 0 <= h <= 47 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    except ValueError:
        return None
    return None


def parse_slots(raw: str | list) -> list[str]:
    if isinstance(raw, list):
        items = raw
    else:
        items = []
        for part in str(raw).replace(",", "\n").replace("،", "\n").splitlines():
            part = part.strip()
            if part:
                items.append(part)
    out = []
    for s in items:
        t = parse_time(s if not isinstance(s, dict) else s.get("time", ""))
        if t:
            out.append(t)
    return sorted(set(out), key=_slot_sort_key)


def parse_entries(raw) -> list[dict]:
    """ورودی آزاد → [{time, mode}]"""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else []
    out = []
    seen = set()
    for item in items:
        if isinstance(item, dict):
            t = parse_time(item.get("time") or item.get("slot") or "")
            mode = str(item.get("mode") or "bomb").strip()
        else:
            t = parse_time(item)
            mode = "bomb"
        if not t:
            continue
        if mode not in TITLE_PREFIX:
            mode = "bomb"
        key = (t, mode)
        if key in seen:
            continue
        seen.add(key)
        out.append({"time": t, "mode": mode})
    return sorted(out, key=lambda e: _slot_sort_key(e["time"]))


def _slot_sort_key(slot: str) -> int:
    t = parse_time(slot) or "99:99"
    h, m = map(int, t.split(":"))
    if h >= 24:
        return h * 60 + m
    order = h * 60 + m
    if h < OVERNIGHT_BEFORE_HOUR:
        order += 24 * 60
    return order


def clock_parts(slot: str) -> tuple[int, int, int]:
    """Return real hour/minute plus explicit day offset for extended hours."""
    h, m = map(int, slot.split(":"))
    return h % 24, m, h // 24


def is_hour25(slot: str) -> bool:
    return parse_time(slot) == HOUR_25


def is_overnight_slot(slot: str) -> bool:
    t = parse_time(slot)
    if not t:
        return False
    if int(t.split(":")[0]) >= 24:
        return True
    return int(t.split(":")[0]) < OVERNIGHT_BEFORE_HOUR


def slot_display(slot: str) -> str:
    t = parse_time(slot) or slot
    if t == HOUR_25:
        return "25:00"
    return t


def slot_to_run_at(day: date, slot: str, day_mode: str = "auto") -> datetime:
    """
    day = روز ثبت برنامه (معمولاً امروز صبح).

    ۲۵:۰۰ = ۱ شب فردا → همیشه day+1 ساعت ۰۱:۰۰
    day_mode برای بقیه:
      auto / tomorrow_am / today
    """
    slot = parse_time(slot) or slot
    h, m, day_offset = clock_parts(slot)

    if day_offset:
        target = day + timedelta(days=day_offset)
    elif day_mode == "tomorrow_am":
        target = day + timedelta(days=1)
    elif day_mode == "today":
        target = day
    else:
        target = day + timedelta(days=1) if h < OVERNIGHT_BEFORE_HOUR else day

    return _aware(datetime.combine(target, dtime(hour=h, minute=m)))


def run_at_label(run_at: datetime, plan_day: date | None = None, slot: str | None = None) -> str:
    local = timezone.localtime(run_at)
    plan_day = plan_day or today_local()
    if slot and int((parse_time(slot) or "0:0").split(":")[0]) >= 24:
        return f"فردا {local.strftime('%H:%M')} ({local.strftime('%m/%d')})"
    if local.date() == plan_day:
        return f"امروز {local.strftime('%H:%M')}"
    if local.date() == plan_day + timedelta(days=1):
        return f"امشب / بامداد فردا {local.strftime('%H:%M')}"
    return local.strftime("%Y/%m/%d %H:%M")


def join_window_for_day(day=None) -> tuple[datetime, datetime]:
    """
    جوین اجباری: از ۱۲:۰۰ همان روز تا ۱۲:۰۰ فردا (تهران).
    """
    day = day or today_local()
    start = _aware(datetime.combine(day, dtime(hour=12, minute=0)))
    end = _aware(datetime.combine(day + timedelta(days=1), dtime(hour=12, minute=0)))
    return start, end


def _flags_for_mode(mode: str) -> tuple[bool, bool]:
    if mode == "group":
        return True, False
    if mode == "pv":
        return False, True
    if mode in ("bomb", "super"):
        return True, True
    raise ValueError("نوع تبلیغ نامعتبر است.")


@transaction.atomic
def clear_today_panel_ads(day=None) -> int:
    day = day or today_local()
    # بازه برنامه: از امروز ۰۰:۰۰ تا فردا ۰۶:۰۰ (شامل ۱ شب)
    start = _aware(datetime.combine(day, dtime.min))
    end = _aware(datetime.combine(day + timedelta(days=1), dtime(hour=OVERNIGHT_BEFORE_HOUR)))
    qs = ScheduledMessage.objects.filter(
        type="fixed",
        last_sent__isnull=True,
        run_at__gte=start,
        run_at__lt=end,
        title__startswith=AD_PREFIX,
    )
    n = qs.count()
    qs.delete()
    return n


deactivate_today_ads = clear_today_panel_ads


def _parse_join_line(line: str) -> tuple[int | None, str]:
    """
    پشتیبانی از:
      https://...
      1|https://...
      1 https://...
    """
    line = (line or "").strip()
    if not line:
        return None, ""
    if "|" in line:
        left, right = line.split("|", 1)
        if left.strip().isdigit() and right.strip():
            return int(left.strip()), right.strip()
    parts = line.split(None, 1)
    if len(parts) == 2 and parts[0].isdigit() and parts[1].startswith(("http://", "https://", "@")):
        return int(parts[0]), parts[1].strip()
    return None, line


@transaction.atomic
def apply_join_only(links: list[str], day=None, replace: bool = True) -> dict:
    """لینک‌ها با اولویت ۱…۵ (یا اولویت صریح در هر خط)."""
    day = day or today_local()
    parsed: list[tuple[int | None, str]] = []
    for raw in links:
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            pr, link = raw
            link = str(link).strip()
            if link:
                parsed.append((int(pr) if pr is not None else None, link))
            continue
        pr, link = _parse_join_line(str(raw))
        if link:
            parsed.append((pr, link))
    parsed = parsed[:5]
    if not parsed:
        raise ValueError("حداقل یک لینک لازم است.")

    start, end = join_window_for_day(day)
    if replace:
        # همه جوین‌های فعال پنل (و در صورت نیاز همه فعال‌ها را اولویت‌بندی می‌کنیم بعداً)
        JoinMessage.objects.filter(title__startswith=JOIN_PREFIX, is_active=True).update(is_active=False)

    # اولویت: صریح از خط، وگرنه به ترتیب ۱،۲،۳…
    used = set()
    normalized: list[tuple[int, str]] = []
    auto = 1
    for pr, link in parsed:
        if pr is None or pr in used:
            while auto in used:
                auto += 1
            pr = auto
            auto += 1
        used.add(pr)
        normalized.append((pr, link))

    created = []
    for pr, link in normalized:
        created.append(JoinMessage.objects.create(
            title=f"{JOIN_PREFIX} p{pr} {day.isoformat()}",
            text=link,
            is_active=True,
            is_forever=False,
            priority=pr,
            start_datetime=start,
            end_datetime=end,
        ))
    return {
        "joins": len(created),
        "start": start,
        "end": end,
        "start_label": timezone.localtime(start).strftime("%Y/%m/%d %H:%M"),
        "end_label": timezone.localtime(end).strftime("%Y/%m/%d %H:%M"),
        "priorities": [p for p, _ in normalized],
    }


@transaction.atomic
def set_join_priority(pk: int, priority: int) -> JoinMessage:
    obj = JoinMessage.objects.get(pk=pk)
    obj.priority = int(priority)
    obj.save(update_fields=["priority"])
    return obj


@transaction.atomic
def renumber_all_join_priorities() -> int:
    """همه جوین‌های فعال را به ترتیب فعلی، اولویت ۱…n می‌دهد."""
    qs = list(JoinMessage.objects.filter(is_active=True).order_by("priority", "id"))
    for i, obj in enumerate(qs, start=1):
        if obj.priority != i:
            obj.priority = i
            obj.save(update_fields=["priority"])
    return len(qs)


@transaction.atomic
def apply_single_ad(
    *,
    mode: str,
    slot: str,
    text: str,
    join_links: list[str] | None = None,
    day=None,
    day_mode: str = "auto",
    queue_ad_until_message: bool = False,
    ignore_group_ad_setting: bool = False,
    source: str = "schedule",
) -> dict:
    """یک تبلیغ یک‌باره در یک ساعت مشخص. source=custom → خارج از برنامه."""
    day = day or today_local()
    slot = parse_time(slot)
    text = (text or "").strip()
    join_links = [x.strip() for x in (join_links or []) if x and str(x).strip()][:5]
    day_mode = day_mode if day_mode in ("auto", "today", "tomorrow_am") else "auto"
    is_custom = source == "custom"

    if not slot:
        raise ValueError("ساعت نامعتبر است.")
    if mode not in TITLE_PREFIX:
        raise ValueError("نوع تبلیغ نامعتبر است.")

    # برای ۲۵ همیشه بامداد فردا ۰۱:۰۰
    if slot == HOUR_25:
        day_mode = "tomorrow_am"

    run_at = slot_to_run_at(day, slot, day_mode=day_mode)
    when = run_at_label(run_at, day, slot=slot)

    # متن خالی = این ساعت تبلیغ نداشته باشد (صف ارسال‌نشده پاک می‌شود)
    if not text:
        cleared, _ = ScheduledMessage.objects.filter(
            type="fixed",
            last_sent__isnull=True,
            run_at=run_at,
            title__startswith=AD_PREFIX,
        ).delete()
        return {
            "ad": None,
            "skipped": True,
            "cleared": cleared,
            "mode": mode,
            "slot": slot,
            "run_at": run_at,
            "when": when,
            "overnight": is_overnight_slot(slot),
            "joins": 0,
            "join_window": None,
            "custom": is_custom,
        }

    # قبلاً ارسال شده → تکرار ممنوع
    if ScheduledMessage.objects.filter(
        type="fixed",
        run_at=run_at,
        title__startswith=AD_PREFIX,
        last_sent__isnull=False,
    ).exists():
        raise ValueError(f"{when} قبلاً ارسال شده و تکرار نمی‌شود.")

    # پاک کردن صف ارسال‌نشده همان لحظه (جلوگیری از چند ردیف)
    ScheduledMessage.objects.filter(
        type="fixed",
        last_sent__isnull=True,
        run_at=run_at,
        title__startswith=AD_PREFIX,
    ).delete()

    send_to_all, send_to_pv = _flags_for_mode(mode)
    overnight = timezone.localtime(run_at).date() > day
    prefixes = TITLE_PREFIX_CUSTOM if is_custom else TITLE_PREFIX
    if slot == HOUR_25:
        title_time = "25:00 ۱‌شب‌فردا"
    elif overnight:
        title_time = f"{slot} امشب"
    else:
        title_time = slot

    ad = ScheduledMessage.objects.create(
        title=f"{prefixes[mode]} {title_time}",
        text=text,
        send_to_all=send_to_all,
        send_to_pv=send_to_pv,
        chat_id=None,
        type="fixed",
        interval_minutes=None,
        run_at=run_at,
        last_sent=None,
        is_active=True,
        queue_ad_until_message=bool(queue_ad_until_message) if send_to_all else False,
        ignore_group_ad_setting=bool(ignore_group_ad_setting) if send_to_all else False,
    )

    join_result = None
    if mode == "super" and join_links:
        join_result = apply_join_only(join_links, day=day, replace=True)

    return {
        "ad": ad,
        "mode": mode,
        "slot": slot,
        "run_at": run_at,
        "when": when,
        "overnight": overnight,
        "custom": is_custom,
        "joins": (join_result or {}).get("joins", 0),
        "join_window": join_result,
    }


@transaction.atomic
def apply_periodic_ad(*, mode: str, text: str, interval_minutes: int) -> ScheduledMessage:
    """Create an active recurring advertisement handled by the existing scheduler."""
    text = (text or "").strip()
    if mode not in TITLE_PREFIX:
        raise ValueError("نوع تبلیغ نامعتبر است.")
    if not text:
        raise ValueError("متن تبلیغ نمی‌تواند خالی باشد.")
    try:
        interval_minutes = int(interval_minutes)
    except (TypeError, ValueError):
        raise ValueError("فاصله ارسال نامعتبر است.")
    if not 1 <= interval_minutes <= 10080:
        raise ValueError("فاصله ارسال باید بین ۱ دقیقه تا ۷ روز باشد.")

    send_to_all, send_to_pv = _flags_for_mode(mode)
    return ScheduledMessage.objects.create(
        title=f"{TITLE_PREFIX_CUSTOM[mode]} دوره‌ای هر {interval_minutes} دقیقه",
        text=text,
        send_to_all=send_to_all,
        send_to_pv=send_to_pv,
        chat_id=None,
        type="interval",
        interval_minutes=interval_minutes,
        run_at=None,
        last_sent=None,
        is_active=True,
        queue_ad_until_message=False,
        ignore_group_ad_setting=False,
    )


def list_periodic_ads():
    return ScheduledMessage.objects.filter(
        type="interval", title__startswith=AD_PREFIX
    ).order_by("-is_active", "-id")


@transaction.atomic
def apply_ads(
    *,
    mode: str,
    slots: list[str],
    text: str,
    join_links: list[str] | None = None,
    day=None,
    queue_ad_until_message: bool = False,
    ignore_group_ad_setting: bool = False,
    replace_today: bool = False,
) -> dict:
    """سازگاری با API قبلی — هر ساعت یک‌بار، type=fixed."""
    day = day or today_local()
    slots = parse_slots(slots)
    if replace_today:
        clear_today_panel_ads(day)
    created = []
    skipped = []
    joins_total = 0
    for slot in slots:
        try:
            r = apply_single_ad(
                mode=mode,
                slot=slot,
                text=text,
                join_links=join_links if mode == "super" else None,
                day=day,
                queue_ad_until_message=queue_ad_until_message,
                ignore_group_ad_setting=ignore_group_ad_setting,
            )
            created.append(r["slot"])
            joins_total = r.get("joins") or joins_total
            # فقط اولین سوپر لینک جوین را ست کند
            if mode == "super":
                join_links = None
        except ValueError as e:
            if "قبلاً ارسال" in str(e):
                skipped.append(slot)
            else:
                raise
    return {
        "ads": len(created),
        "joins": joins_total,
        "slots": created,
        "skipped_sent": skipped,
        "day": day.isoformat(),
        "mode": mode,
    }


apply_campaign = apply_ads


def board_status_for_schedule(schedule, day=None) -> list[dict]:
    """وضعیت هر ردیف برنامه برای پنل امروز."""
    day = day or today_local()
    rows = []
    for entry in schedule.normalized_entries():
        # ساعت‌های شب همیشه از امروز ثبت می‌شوند → بامداد فردا
        day_mode = "tomorrow_am" if is_overnight_slot(entry["time"]) else "auto"
        run_at = slot_to_run_at(day, entry["time"], day_mode=day_mode)
        existing = (
            ScheduledMessage.objects
            .filter(type="fixed", run_at=run_at, title__startswith=AD_PREFIX)
            .order_by("-id")
            .first()
        )
        status = "empty"
        if existing:
            if existing.last_sent:
                status = "sent"
            elif existing.is_active:
                status = "queued"
            else:
                status = "off"
        overnight = is_overnight_slot(entry["time"])
        h25 = is_hour25(entry["time"])
        delivery = None
        if existing and existing.last_sent:
            sg = int(getattr(existing, "success_groups", 0) or 0)
            sp = int(getattr(existing, "success_pv", 0) or 0)
            fg = int(getattr(existing, "fail_groups", 0) or 0)
            fp = int(getattr(existing, "fail_pv", 0) or 0)
            ag = int(getattr(existing, "attempt_groups", 0) or 0)
            ap = int(getattr(existing, "attempt_pv", 0) or 0)
            # اگر fail ذخیره نشده ولی attempt هست، از تفاضل بگیر
            if ag and not fg and ag >= sg:
                fg = ag - sg
            if ap and not fp and ap >= sp:
                fp = ap - sp
            delivery = {
                "ok_groups": sg,
                "fail_groups": fg,
                "ok_pv": sp,
                "fail_pv": fp,
                "show_groups": bool(existing.send_to_all or sg or fg or ag),
                "show_pv": bool(existing.send_to_pv or sp or fp or ap),
            }
        rows.append({
            "time": entry["time"],
            "time_label": "25:00" if h25 else entry["time"],
            "mode": entry["mode"],
            "mode_label": MODE_LABEL.get(entry["mode"], entry["mode"]),
            "run_at": run_at,
            "when": run_at_label(run_at, day, slot=entry["time"]),
            "overnight": overnight,
            "hour25": h25,
            "day_mode": day_mode,
            "status": status,
            "existing": existing,
            "delivery": delivery,
            "is_super": entry["mode"] == "super",
        })
    return rows


def dashboard_stats() -> dict:
    now = timezone.localtime()
    day = now.date()
    start, end = campaign_window(day)

    today_ads = ScheduledMessage.objects.filter(
        type="fixed", run_at__gte=start, run_at__lt=end, title__startswith=AD_PREFIX,
    )
    pending = today_ads.filter(is_active=True, last_sent__isnull=True).count()
    sent = today_ads.filter(last_sent__isnull=False).count()
    sent_qs = today_ads.filter(last_sent__isnull=False)
    ok_groups_today = sum(getattr(a, "success_groups", 0) or 0 for a in sent_qs)
    ok_pv_today = sum(getattr(a, "success_pv", 0) or 0 for a in sent_qs)
    active_joins = JoinMessage.objects.filter(is_active=True)
    live_joins = sum(1 for j in active_joins if j.is_active_now(now))
    jstart, jend = join_window_for_day(day)

    next_ad = (
        ScheduledMessage.objects
        .filter(
            type="fixed", is_active=True, last_sent__isnull=True,
            run_at__gte=now, title__startswith=AD_PREFIX,
        )
        .order_by("run_at")
        .first()
    )
    return {
        "pending_today": pending,
        "sent_today": sent,
        "total_today": today_ads.count(),
        "ok_groups_today": ok_groups_today,
        "ok_pv_today": ok_pv_today,
        "live_joins": live_joins,
        "active_joins": active_joins.count(),
        "next_ad": next_ad,
        "now": now,
        "join_start": jstart,
        "join_end": jend,
    }


def campaign_window(day=None):
    """بازه نمایش امروز: از ۰۰:۰۰ امروز تا پایان فردا (شامل خارج‌ازبرنامه و ۲۵)."""
    day = day or today_local()
    start = _aware(datetime.combine(day, dtime.min))
    end = _aware(datetime.combine(day + timedelta(days=2), dtime.min))
    return start, end


def list_today_ads(day=None):
    day = day or today_local()
    start, end = campaign_window(day)
    return list(
        ScheduledMessage.objects
        .filter(type="fixed", run_at__gte=start, run_at__lt=end, title__startswith=AD_PREFIX)
        .order_by("run_at", "id")
    )


def list_extra_ads(schedule=None, day=None):
    """
    تبلیغات خارج از برنامهٔ ساعت:
    - عنوان دارای [خارج]
    - یا run_at جزو ردیف‌های برنامه نیست
    """
    day = day or today_local()
    ads = list_today_ads(day) + list(list_periodic_ads())
    schedule_run_ats = set()
    if schedule:
        for entry in schedule.normalized_entries():
            day_mode = "tomorrow_am" if is_overnight_slot(entry["time"]) else "auto"
            schedule_run_ats.add(slot_to_run_at(day, entry["time"], day_mode=day_mode))

    extras = []
    for ad in ads:
        is_custom = CUSTOM_MARK in (ad.title or "")
        if ad.type == "interval":
            extras.append({
                "ad": ad,
                "is_custom": True,
                "status": "queued" if ad.is_active else "off",
                "when": f"هر {ad.interval_minutes} دقیقه",
                "ok_groups": getattr(ad, "success_groups", 0) or 0,
                "fail_groups": getattr(ad, "fail_groups", 0) or 0,
                "ok_pv": getattr(ad, "success_pv", 0) or 0,
                "fail_pv": getattr(ad, "fail_pv", 0) or 0,
            })
            continue
        in_schedule = ad.run_at in schedule_run_ats if schedule_run_ats else False
        if is_custom or not in_schedule:
            local = timezone.localtime(ad.run_at) if ad.run_at else None
            if ad.last_sent:
                status = "sent"
            elif ad.is_active:
                status = "queued"
            else:
                status = "off"
            extras.append({
                "ad": ad,
                "is_custom": is_custom,
                "status": status,
                "when": local.strftime("%Y/%m/%d %H:%M") if local else "—",
                "ok_groups": getattr(ad, "success_groups", 0) or 0,
                "fail_groups": getattr(ad, "fail_groups", 0) or 0,
                "ok_pv": getattr(ad, "success_pv", 0) or 0,
                "fail_pv": getattr(ad, "fail_pv", 0) or 0,
            })
    return extras


def list_active_joins():
    return list(JoinMessage.objects.filter(is_active=True).order_by("priority", "id"))


def active_schedule():
    from .models import AdLoadout
    return (
        AdLoadout.objects.filter(is_favorite=True).first()
        or AdLoadout.objects.order_by("id").first()
    )


def peers_status() -> list[dict]:
    # Telegram is deployed as a single panel and has no Rubika peer-sync layer.
    return []


# ── پاکسازی ──────────────────────────────────────────────────────────────────

def cleanup_preview() -> dict:
    now = timezone.localtime()
    day = today_local()
    start_today = _aware(datetime.combine(day, dtime.min))

    panel = ScheduledMessage.objects.filter(title__startswith=AD_PREFIX)
    fixed_panel = panel.filter(type="fixed")
    sent_all = fixed_panel.filter(last_sent__isnull=False)
    sent_old_3 = sent_all.filter(last_sent__lt=now - timedelta(days=3))
    sent_old_7 = sent_all.filter(last_sent__lt=now - timedelta(days=7))
    sent_old_30 = sent_all.filter(last_sent__lt=now - timedelta(days=30))

    missed = fixed_panel.filter(last_sent__isnull=True, run_at__lt=start_today)
    inactive = panel.filter(is_active=False)

    joins_all = JoinMessage.objects.all()
    joins_inactive = joins_all.filter(is_active=False)
    joins_expired = joins_all.filter(
        is_active=True, is_forever=False, end_datetime__isnull=False, end_datetime__lt=now,
    )

    return {
        "panel_total": panel.count(),
        "sent_all": sent_all.count(),
        "sent_old_3": sent_old_3.count(),
        "sent_old_7": sent_old_7.count(),
        "sent_old_30": sent_old_30.count(),
        "missed": missed.count(),
        "inactive": inactive.count(),
        "joins_total": joins_all.count(),
        "joins_inactive": joins_inactive.count(),
        "joins_expired": joins_expired.count(),
        "now": now,
    }


@transaction.atomic
def cleanup_run(action: str, days: int = 7) -> dict:
    now = timezone.localtime()
    day = today_local()
    start_today = _aware(datetime.combine(day, dtime.min))
    days = max(1, min(int(days or 7), 365))
    result = {"action": action, "days": days, "deleted_ads": 0, "deleted_joins": 0, "deactivated_joins": 0}

    panel = ScheduledMessage.objects.filter(title__startswith=AD_PREFIX)
    fixed_panel = panel.filter(type="fixed")

    if action in ("sent_older", "all_safe"):
        qs = fixed_panel.filter(last_sent__isnull=False, last_sent__lt=now - timedelta(days=days))
        n, _ = qs.delete()
        result["deleted_ads"] += n

    if action in ("missed", "all_safe"):
        qs = fixed_panel.filter(last_sent__isnull=True, run_at__lt=start_today)
        n, _ = qs.delete()
        result["deleted_ads"] += n

    if action == "inactive_ads":
        qs = panel.filter(is_active=False)
        n, _ = qs.delete()
        result["deleted_ads"] += n

    if action in ("expire_joins", "all_safe"):
        qs = JoinMessage.objects.filter(
            is_active=True, is_forever=False, end_datetime__isnull=False, end_datetime__lt=now,
        )
        result["deactivated_joins"] = qs.update(is_active=False)

    if action == "delete_dead_joins":
        qs = JoinMessage.objects.filter(is_active=False)
        n, _ = qs.delete()
        result["deleted_joins"] += n

    if action == "sent_today":
        end = _aware(datetime.combine(day + timedelta(days=1), dtime(hour=OVERNIGHT_BEFORE_HOUR)))
        qs = fixed_panel.filter(last_sent__isnull=False, run_at__gte=start_today, run_at__lt=end)
        n, _ = qs.delete()
        result["deleted_ads"] += n

    return result


def _mode_from_title(title: str) -> str:
    t = title or ""
    if "[سوپربمب]" in t or "[سوپر" in t:
        return "super"
    if "[بمب]" in t:
        return "bomb"
    if "[ربات]" in t:
        return "pv"
    if "[گروه]" in t:
        return "group"
    return "other"


def analytics_report(days: int = 14) -> dict:
    days = max(7, min(int(days or 14), 90))
    now = timezone.localtime()
    day0 = today_local()
    start = _aware(datetime.combine(day0 - timedelta(days=days - 1), dtime.min))

    panel = list(ScheduledMessage.objects.filter(
        title__startswith=AD_PREFIX,
        type="fixed",
        run_at__gte=start,
    ).only("title", "last_sent", "run_at", "is_active"))

    daily = []
    for i in range(days):
        d = day0 - timedelta(days=days - 1 - i)
        ds = _aware(datetime.combine(d, dtime.min))
        de = ds + timedelta(days=1)
        day_items = [a for a in panel if a.run_at and ds <= a.run_at < de]
        daily.append({
            "date": d.isoformat(),
            "label": d.strftime("%m/%d"),
            "sent": sum(1 for a in day_items if a.last_sent),
            "pending": sum(1 for a in day_items if not a.last_sent and a.is_active),
            "total": len(day_items),
            "ok_groups": sum(getattr(a, "success_groups", 0) or 0 for a in day_items if a.last_sent),
            "ok_pv": sum(getattr(a, "success_pv", 0) or 0 for a in day_items if a.last_sent),
        })

    by_mode = {k: 0 for k in ("group", "pv", "bomb", "super", "other")}
    by_mode_sent = {k: 0 for k in by_mode}
    by_mode_groups = {k: 0 for k in by_mode}
    by_mode_pv = {k: 0 for k in by_mode}
    hour_hist = [0] * 24
    ok_groups_total = 0
    ok_pv_total = 0
    for ad in panel:
        m = _mode_from_title(ad.title)
        by_mode[m] = by_mode.get(m, 0) + 1
        g = getattr(ad, "success_groups", 0) or 0
        p = getattr(ad, "success_pv", 0) or 0
        if ad.last_sent:
            by_mode_sent[m] = by_mode_sent.get(m, 0) + 1
            by_mode_groups[m] = by_mode_groups.get(m, 0) + g
            by_mode_pv[m] = by_mode_pv.get(m, 0) + p
            ok_groups_total += g
            ok_pv_total += p
            hour_hist[timezone.localtime(ad.last_sent).hour] += 1

    joins = JoinMessage.objects.all()
    live = sum(1 for j in joins.filter(is_active=True) if j.is_active_now(now))
    total = len(panel)
    sent = sum(1 for a in panel if a.last_sent)
    pending = sum(1 for a in panel if not a.last_sent and a.is_active)

    return {
        "days": days,
        "daily": daily,
        "by_mode": by_mode,
        "by_mode_sent": by_mode_sent,
        "by_mode_groups": by_mode_groups,
        "by_mode_pv": by_mode_pv,
        "hour_hist": hour_hist,
        "totals": {
            "total": total,
            "sent": sent,
            "pending": pending,
            "missed": sum(1 for a in panel if not a.last_sent and a.run_at and a.run_at < now and a.is_active),
            "joins_live": live,
            "joins_active": joins.filter(is_active=True).count(),
            "success_rate": round((sent / total) * 100, 1) if total else 0,
            "ok_groups": ok_groups_total,
            "ok_pv": ok_pv_total,
        },
        "mode_labels": MODE_LABEL,
        "now": now,
    }
