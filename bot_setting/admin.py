"""
پنل ادمین تنظیمات ربات — Unfold UI
"""
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import JoinMessage, ForcedJoinConfig, BotSiteConfig


class SingletonAdmin(ModelAdmin):
    """ادمین تک‌رکوردی — همیشه همان pk=1 را ویرایش می‌کند."""

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = self.model.get_singleton()
        return HttpResponseRedirect(
            reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change", args=[obj.pk])
        )


@admin.register(BotSiteConfig)
class BotSiteConfigAdmin(SingletonAdmin):
    fieldsets = (
        ("🔥 لینکدونی", {
            "fields": ("link_directory_url", "link_directory_title"),
            "description": "دکمه لینکدونی در پیوی ربات برای کاربران عادی",
        }),
        ("💬 پشتیبانی", {
            "fields": ("support_url", "support_title"),
        }),
        ("📣 کانال", {
            "fields": ("channel_url",),
            "classes": ("collapse",),
        }),
        ("⏱ آخرین تغییر", {
            "fields": ("updated_at",),
        }),
    )
    readonly_fields = ("updated_at",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        try:
            from bot.site_config import apply_site_config_cache
            apply_site_config_cache({
                "link_directory_url": obj.link_directory_url,
                "link_directory_title": obj.link_directory_title,
                "support_url": obj.support_url,
                "support_title": obj.support_title,
                "channel_url": obj.channel_url or "",
            })
            messages.success(request, "کش ربات هم به‌روز شد.")
        except Exception:
            messages.warning(request, "ذخیره شد؛ برای اعمال در ربات کش را ریلود کنید.")


@admin.register(ForcedJoinConfig)
class ForcedJoinConfigAdmin(SingletonAdmin):
    fieldsets = (
        ("وضعیت", {
            "fields": ("enabled",),
        }),
        ("کانال", {
            "fields": ("channel_id", "channel_title", "channel_username", "invite_link"),
        }),
        ("⏱ آخرین تغییر", {
            "fields": ("updated_at",),
        }),
    )
    readonly_fields = ("updated_at",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        try:
            from bot.required_join import apply_forced_join_cache
            apply_forced_join_cache({
                "enabled": obj.enabled,
                "channel_id": obj.channel_id,
                "channel_title": obj.channel_title or "",
                "channel_username": obj.channel_username or "",
                "invite_link": obj.invite_link or "",
            })
            messages.success(request, "کش جوین اجباری به‌روز شد.")
        except Exception:
            messages.warning(request, "ذخیره شد؛ برای اعمال در ربات کش را ریلود کنید.")


@admin.register(JoinMessage)
class JoinMessageAdmin(ModelAdmin):
    list_display = ("title", "active_badge", "priority", "is_forever", "start_datetime", "end_datetime", "created_at")
    list_filter = ("is_active", "is_forever")
    list_editable = ("priority",)
    search_fields = ("title", "text")
    ordering = ("priority", "-created_at")
    readonly_fields = ("created_at",)
    list_per_page = 25

    fieldsets = (
        ("محتوا", {"fields": ("title", "text")}),
        ("زمان‌بندی", {
            "fields": ("is_active", "is_forever", "priority", "start_datetime", "end_datetime"),
        }),
        ("تاریخ", {"fields": ("created_at",)}),
    )

    @display(description="فعال", label=True)
    def active_badge(self, obj):
        return "فعال" if obj.is_active else "خاموش"
