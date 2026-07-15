from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_http_methods

from scheduledmessage.models import ScheduledMessage
from bot_setting.models import JoinMessage

from .models import AdLoadout
from .forms import ScheduleForm, CustomAdForm, PeriodicAdForm, JoinOnlyForm, SlotPostForm
from . import services


def _staff(user):
    return user.is_authenticated and user.is_staff


staff_required = user_passes_test(_staff, login_url="/ad/login/")


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("ad_panel:dashboard")
    error = ""
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", ""),
            password=request.POST.get("password", ""),
        )
        if user and user.is_staff:
            login(request, user)
            return redirect(request.GET.get("next") or "ad_panel:dashboard")
        error = "نام کاربری یا رمز اشتباه است."
    return render(request, "ad_panel/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("ad_panel:login")


def _board_context(request, schedule=None):
    schedules = list(AdLoadout.objects.all())
    sid = request.GET.get("schedule")
    if schedule is None:
        if sid:
            schedule = AdLoadout.objects.filter(pk=sid).first()
        schedule = schedule or services.active_schedule()
    stats = services.dashboard_stats()
    rows = services.board_status_for_schedule(schedule) if schedule else []
    today_ads = services.list_today_ads()
    extra_ads = services.list_extra_ads(schedule)
    jstart, jend = services.join_window_for_day()
    return {
        "stats": stats,
        "schedule": schedule,
        "schedules": schedules,
        "rows": rows,
        "today_ads": today_ads,
        "extra_ads": extra_ads,
        "joins": services.list_active_joins(),
        "custom_form": CustomAdForm(),
        "periodic_form": PeriodicAdForm(),
        "periodic_ads": services.list_periodic_ads(),
        "join_start": jstart,
        "join_end": jend,
        "mode_choices": AdLoadout.MODE_CHOICES,
        "page": "dashboard",
    }


@login_required(login_url="/ad/login/")
@staff_required
def dashboard(request):
    return render(request, "ad_panel/dashboard.html", _board_context(request))


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def post_slot(request):
    form = SlotPostForm(request.POST)
    if not form.is_valid():
        messages.error(request, "فرم ناقص است — ساعت را چک کن.")
        return redirect("ad_panel:dashboard")
    cd = form.cleaned_data
    try:
        if cd.get("schedule_type") == "interval":
            ad = services.apply_periodic_ad(
                mode=cd["mode"], text=cd["text"], interval_minutes=cd["interval_minutes"],
            )
            messages.success(request, f"تبلیغ خارج از برنامهٔ دوره‌ای ثبت شد: هر {ad.interval_minutes} دقیقه")
            return redirect("/ad/#extra-ads")
        result = services.apply_single_ad(
            mode=cd["mode"],
            slot=cd["time"],
            text=cd["text"],
            join_links=cd.get("join_links") or [],
            day_mode=cd.get("day_mode") or "auto",
        )
        if result.get("skipped"):
            messages.success(
                request,
                f"بدون تبلیغ برای {result.get('when') or cd['time']} "
                f"(صف پاک شد: {result.get('cleared', 0)})",
            )
        else:
            msg = f"ثبت شد: {services.MODE_LABEL.get(cd['mode'])} · {result.get('when') or cd['time']} (یک‌بار)"
            if result.get("joins"):
                jw = result.get("join_window") or {}
                msg += f" · جوین {result['joins']} لینک ({jw.get('start_label')} → {jw.get('end_label')})"
            elif cd["mode"] == "super" and not cd.get("join_links"):
                msg += " · جوین ثبت نشد (لینک خالی بود)"
            messages.success(request, msg)
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("ad_panel:dashboard")


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def post_custom(request):
    form = CustomAdForm(request.POST)
    if not form.is_valid():
        for err in form.non_field_errors():
            messages.error(request, err)
        for field, errs in form.errors.items():
            if field == "__all__":
                continue
            messages.error(request, f"{field}: {', '.join(errs)}")
        return redirect("ad_panel:dashboard")
    cd = form.cleaned_data
    try:
        result = services.apply_single_ad(
            mode=cd["mode"],
            slot=cd["time"],
            text=cd["text"],
            join_links=cd.get("join_links") or [],
            day_mode=cd.get("day_mode") or "auto",
            source="custom",
        )
        if result.get("skipped"):
            messages.success(
                request,
                f"بدون تبلیغ برای {result.get('when') or cd['time']} "
                f"(صف پاک شد: {result.get('cleared', 0)})",
            )
        else:
            msg = (
                f"خارج از برنامه ثبت شد: {services.MODE_LABEL.get(cd['mode'])} · "
                f"{result.get('when') or cd['time']} — در بخش پایین «خارج از برنامه» ببین"
            )
            if result.get("joins"):
                jw = result.get("join_window") or {}
                msg += f" · جوین ({jw.get('start_label')} → {jw.get('end_label')})"
            messages.success(request, msg)
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("/ad/#extra-ads")


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def post_periodic(request):
    form = PeriodicAdForm(request.POST)
    if not form.is_valid():
        for field, errs in form.errors.items():
            messages.error(request, f"{field}: {', '.join(errs)}")
        return redirect("/ad/#periodic-ads")
    try:
        ad = services.apply_periodic_ad(**form.cleaned_data)
        messages.success(request, f"تبلیغ دوره‌ای ثبت شد: هر {ad.interval_minutes} دقیقه")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("/ad/#periodic-ads")


# سازگاری URL قدیمی
@login_required(login_url="/ad/login/")
@staff_required
def post_ad(request):
    return redirect("ad_panel:dashboard")


campaign = post_ad


@login_required(login_url="/ad/login/")
@staff_required
@require_http_methods(["GET", "POST"])
def join_page(request):
    if request.method == "POST":
        form = JoinOnlyForm(request.POST)
        if form.is_valid():
            try:
                result = services.apply_join_only(form.cleaned_data["join_links"])
                pr = "،".join(str(p) for p in result.get("priorities") or [])
                messages.success(
                    request,
                    f"{result['joins']} لینک جوین (اولویت {pr}): "
                    f"{result['start_label']} → {result['end_label']}",
                )
                return redirect("ad_panel:join")
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = JoinOnlyForm()

    start, end = services.join_window_for_day()
    return render(request, "ad_panel/join.html", {
        "form": form,
        "joins": services.list_active_joins(),
        "window_start": start,
        "window_end": end,
        "page": "join",
    })


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def join_set_priority(request, pk):
    try:
        pr = int(request.POST.get("priority", "0"))
    except (TypeError, ValueError):
        messages.error(request, "اولویت نامعتبر است.")
        return redirect("ad_panel:join")
    try:
        obj = services.set_join_priority(pk, pr)
        messages.success(request, f"اولویت «{obj.title}» → {obj.priority}")
    except JoinMessage.DoesNotExist:
        messages.error(request, "جوین پیدا نشد.")
    return redirect("ad_panel:join")


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def join_renumber(request):
    n = services.renumber_all_join_priorities()
    messages.success(request, f"اولویت همه جوین‌های فعال مرتب شد: ۱ تا {n}")
    return redirect("ad_panel:join")


@login_required(login_url="/ad/login/")
@staff_required
def schedules(request):
    return render(request, "ad_panel/schedules.html", {
        "schedules": AdLoadout.objects.all(),
        "page": "schedules",
    })


loadouts = schedules


def _parse_schedule_rows(post) -> list[dict]:
    times = post.getlist("row_time")
    modes = post.getlist("row_mode")
    entries = []
    for t, m in zip(times, modes):
        entries.append({"time": t, "mode": m})
    return entries


@login_required(login_url="/ad/login/")
@staff_required
@require_http_methods(["GET", "POST"])
def schedule_edit(request, pk=None):
    obj = get_object_or_404(AdLoadout, pk=pk) if pk else None
    if request.method == "POST":
        form = ScheduleForm(request.POST, instance=obj)
        entries = _parse_schedule_rows(request.POST)
        if form.is_valid():
            if not services.parse_entries(entries):
                messages.error(request, "حداقل یک ردیف ساعت+نوع لازم است.")
            else:
                saved = form.save_with_entries(entries)
                if saved.is_favorite:
                    AdLoadout.objects.exclude(pk=saved.pk).update(is_favorite=False)
                messages.success(request, "برنامه ساعت ذخیره شد.")
                return redirect("ad_panel:schedules")
    else:
        form = ScheduleForm(instance=obj)

    entries = obj.normalized_entries() if obj else [
        {"time": "09:00", "mode": "group"},
        {"time": "13:00", "mode": "super"},
        {"time": "17:00", "mode": "super"},
        {"time": "20:00", "mode": "bomb"},
        {"time": "22:00", "mode": "group"},
        {"time": "25:00", "mode": "group"},
    ]
    return render(request, "ad_panel/schedule_form.html", {
        "form": form,
        "obj": obj,
        "entries": entries,
        "mode_choices": AdLoadout.MODE_CHOICES,
        "page": "schedules",
    })


loadout_edit = schedule_edit


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def schedule_delete(request, pk):
    get_object_or_404(AdLoadout, pk=pk).delete()
    messages.success(request, "برنامه حذف شد.")
    return redirect("ad_panel:schedules")


loadout_delete = schedule_delete


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def toggle_ad(request, pk):
    obj = get_object_or_404(ScheduledMessage, pk=pk)
    obj.is_active = not obj.is_active
    obj.save()
    return redirect("ad_panel:dashboard")


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def delete_ad(request, pk):
    get_object_or_404(ScheduledMessage, pk=pk).delete()
    messages.success(request, "حذف شد.")
    return redirect("ad_panel:dashboard")


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def deactivate_join(request, pk):
    obj = get_object_or_404(JoinMessage, pk=pk)
    obj.is_active = False
    obj.save()
    return redirect("ad_panel:join")


@login_required(login_url="/ad/login/")
@staff_required
@require_POST
def clear_today(request):
    n = services.clear_today_panel_ads()
    messages.success(request, f"{n} تبلیغ ارسال‌نشده پاک شد.")
    return redirect("ad_panel:dashboard")


@login_required(login_url="/ad/login/")
@staff_required
def stats_page(request):
    try:
        days = int(request.GET.get("days") or 14)
    except ValueError:
        days = 14
    report = services.analytics_report(days=days)
    return render(request, "ad_panel/stats.html", {
        "report": report,
        "page": "stats",
    })


@login_required(login_url="/ad/login/")
@staff_required
@require_http_methods(["GET", "POST"])
def tools_page(request):
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        try:
            days = int(request.POST.get("days") or 7)
        except ValueError:
            days = 7

        if action == "push_sync":
            messages.error(request, "همگام‌سازی چند پنل در نسخه تلگرام پشتیبانی نمی‌شود.")
            return redirect("ad_panel:tools")

        allowed = {
            "sent_older", "missed", "inactive_ads",
            "expire_joins", "delete_dead_joins", "all_safe", "sent_today",
        }
        if action not in allowed:
            messages.error(request, "عملیات نامعتبر است.")
        else:
            result = services.cleanup_run(action, days=days)
            parts = []
            if result["deleted_ads"]:
                parts.append(f"{result['deleted_ads']} تبلیغ حذف")
            if result["deactivated_joins"]:
                parts.append(f"{result['deactivated_joins']} جوین خاموش")
            if result["deleted_joins"]:
                parts.append(f"{result['deleted_joins']} جوین حذف")
            messages.success(request, " · ".join(parts) if parts else "چیزی برای پاکسازی نبود.")
        return redirect("ad_panel:tools")

    return render(request, "ad_panel/tools.html", {
        "preview": services.cleanup_preview(),
        "peers": services.peers_status(),
        "sync_self": getattr(settings, "SYNC_SELF_URL", "") or "",
        "page": "tools",
    })
