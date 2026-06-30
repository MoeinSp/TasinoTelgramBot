from django.contrib import admin
from django.utils.html import format_html
from .models import JoinMessage


@admin.register(JoinMessage)
class JoinMessageAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "priority", "is_forever", "start_datetime", "end_datetime", "created_at")
    list_filter = ("is_active", "is_forever")
    list_editable = ("is_active", "priority")
    search_fields = ("title", "text")
    ordering = ("priority", "-created_at")
    readonly_fields = ("created_at",)

    fieldsets = (
        ("محتوا", {
            "fields": ("title", "text")
        }),
        ("زمان‌بندی", {
            "fields": ("is_active", "is_forever", "priority", "start_datetime", "end_datetime")
        }),
        ("تاریخ ایجاد", {
            "fields": ("created_at",)
        }),
    )
