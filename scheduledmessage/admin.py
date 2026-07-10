from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import ScheduledMessage


@admin.register(ScheduledMessage)
class ScheduledMessageAdmin(ModelAdmin):
    list_display = (
        "title", "type_badge", "target_info", "is_active", "status_badge",
        "last_sent", "created_at",
    )
    list_filter = ("is_active", "type", "send_to_all", "send_to_pv", "ignore_group_ad_setting")
    search_fields = ("title", "text")
    list_editable = ("is_active",)
    ordering = ("-is_active", "-id")
    readonly_fields = ("created_at", "last_sent", "next_send_preview")
    list_per_page = 30

    fieldsets = (
        ("محتوا", {"fields": ("title", "text")}),
        ("نوع زمان‌بندی", {
            "fields": ("type", "interval_minutes", "run_at"),
            "description": "⏱ دوره‌ای: فاصله دقیقه | 📅 زمان مشخص: تاریخ و ساعت",
        }),
        ("هدف ارسال", {
            "fields": ("send_to_all", "send_to_pv", "chat_id"),
        }),
        ("تنظیمات تبلیغات", {
            "fields": ("ignore_group_ad_setting", "queue_ad_until_message"),
            "classes": ("collapse",),
        }),
        ("وضعیت", {
            "fields": ("is_active", "last_sent", "next_send_preview", "created_at"),
        }),
    )

    @display(description="نوع")
    def type_badge(self, obj):
        if obj.type == "interval":
            mins = obj.interval_minutes or "؟"
            return format_html(
                '<span style="color:#3b82f6;font-weight:700">⏱ هر {} دقیقه</span>', mins
            )
        if obj.type == "fixed":
            t = obj.run_at.strftime("%Y-%m-%d %H:%M") if obj.run_at else "—"
            return format_html(
                '<span style="color:#a855f7;font-weight:700">📅 {}</span>', t
            )
        return obj.type

    @display(description="هدف")
    def target_info(self, obj):
        parts = []
        if obj.send_to_all:
            parts.append("🌐 همه گروه‌ها")
        if obj.send_to_pv:
            parts.append("💬 پیوی")
        if obj.chat_id and not obj.send_to_all:
            parts.append(f"👥 {obj.chat_id}")
        return " | ".join(parts) if parts else "—"

    @display(description="وضعیت")
    def status_badge(self, obj):
        if not obj.is_active:
            return mark_safe('<span style="color:#94a3b8">⛔ غیرفعال</span>')
        if obj.type == "fixed" and obj.last_sent:
            return mark_safe('<span style="color:#22c55e">✅ ارسال شد</span>')
        return mark_safe('<span style="color:#22c55e;font-weight:700">🟢 فعال</span>')

    @display(description="ارسال بعدی")
    def next_send_preview(self, obj):
        if not obj.is_active:
            return "—"
        now = timezone.now().replace(second=0, microsecond=0)
        if obj.type == "fixed":
            if obj.run_at and not obj.last_sent:
                delta = obj.run_at - now
                if delta.total_seconds() > 0:
                    mins = int(delta.total_seconds() // 60)
                    return f"⏳ {mins} دقیقه دیگر ({obj.run_at.strftime('%H:%M')})"
                return "⚡ آماده ارسال"
            return "✅ قبلاً ارسال شده"
        if obj.type == "interval" and obj.interval_minutes:
            if obj.last_sent:
                from datetime import timedelta
                nxt = obj.last_sent + timedelta(minutes=obj.interval_minutes)
                delta = nxt - now
                if delta.total_seconds() > 0:
                    mins = int(delta.total_seconds() // 60)
                    return f"⏳ {mins} دقیقه دیگر ({nxt.strftime('%H:%M')})"
                return "⚡ آماده ارسال"
            return "⚡ اولین ارسال در دقیقه آینده"
        return "—"
