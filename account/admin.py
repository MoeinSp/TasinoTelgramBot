from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import (
    TelegramGroup, TelegramGroupMember, LearnedResponse,
    DiceRollStat, License, TelegramUser, Note, WalletTransaction,
)


@admin.register(TelegramGroup)
class TelegramGroupAdmin(ModelAdmin):
    list_display = (
        "name", "telegram_chat_id", "theme",
        "status_badges", "fee_percent", "max_warnings",
        "welcome_on", "captcha_on", "subscription_until", "created_at",
    )
    list_filter = (
        "off", "is_active", "is_speaker_enabled", "group_lock",
        "dice_option", "welcome_enabled", "captcha_enabled",
        "anti_flood_enabled", "antiraid_enabled", "telegram_emoji_enabled",
    )
    search_fields = ("telegram_chat_id", "name")
    readonly_fields = ("created_at",)
    list_editable = ("fee_percent", "max_warnings")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 30
    list_filter_submit = True

    fieldsets = (
        ("اطلاعات اصلی", {
            "fields": ("telegram_chat_id", "name", "theme", "created_at"),
        }),
        ("وضعیت ربات", {
            "fields": (
                "off", "is_active", "is_speaker_enabled",
                "group_lock", "dice_option", "warning_enabled",
                "telegram_emoji_enabled",
            ),
        }),
        ("مالی و اشتراک", {
            "fields": ("max_warnings", "fee_percent", "subscription_until"),
        }),
        ("خوشامدگویی", {
            "fields": ("welcome_enabled", "welcome_text", "welcome_gif_file_id"),
        }),
        ("امنیت", {
            "fields": (
                "captcha_enabled", "captcha_timeout",
                "anti_flood_enabled", "anti_flood_limit", "anti_flood_window",
                "antiraid_enabled",
            ),
        }),
        ("حالت شب", {
            "fields": ("night_mode_enabled", "night_start_hour", "night_end_hour"),
            "classes": ("collapse",),
        }),
        ("قوانین و لاگ", {
            "fields": ("rules_text", "log_channel_id"),
            "classes": ("collapse",),
        }),
        ("تبلیغات", {
            "fields": ("ad_enabled", "ad_disabled_until"),
            "classes": ("collapse",),
        }),
        ("قفل‌ها و دستورات (JSON)", {
            "fields": ("locks", "enabled_commands"),
            "classes": ("collapse",),
        }),
    )

    @display(description="وضعیت")
    def status_badges(self, obj):
        badges = []
        if obj.off:
            badges.append('<span style="color:#ef4444;font-weight:700">⛔ خاموش</span>')
        else:
            badges.append('<span style="color:#22c55e;font-weight:700">✅ فعال</span>')
        if obj.is_speaker_enabled:
            badges.append('<span style="color:#3b82f6">🔊</span>')
        if obj.group_lock:
            badges.append('<span style="color:#f59e0b">🔒</span>')
        return mark_safe(" ".join(badges))

    @display(description="خوشامد", boolean=True)
    def welcome_on(self, obj):
        return bool(obj.welcome_enabled)

    @display(description="کپچا", boolean=True)
    def captcha_on(self, obj):
        return bool(obj.captcha_enabled)


@admin.register(TelegramGroupMember)
class TelegramGroupMemberAdmin(ModelAdmin):
    list_display = (
        "telegram_user_id", "telegram_chat_id", "alias",
        "role_badge", "level", "xp_total", "message_count",
        "point", "warnings", "cards_display", "added_at",
    )
    list_filter = ("role", "is_owner", "is_admin", "is_vip")
    search_fields = ("telegram_user_id", "telegram_chat_id", "alias", "card_number")
    list_editable = ("point", "warnings")
    ordering = ("-message_count",)
    readonly_fields = ("added_at",)
    list_per_page = 40
    list_filter_submit = True
    autocomplete_fields = ("group",)

    fieldsets = (
        ("شناسه", {"fields": ("telegram_chat_id", "telegram_user_id", "group", "alias")}),
        ("نقش", {"fields": ("role", "is_owner", "is_admin", "is_vip")}),
        ("آمار", {"fields": ("level", "xp_total", "message_count", "warnings")}),
        ("مالی", {"fields": ("point",)}),
        ("کارت بانکی", {"fields": ("card_number", "card_number2", "card_number3", "card_name")}),
        ("تاریخ", {"fields": ("added_at",)}),
    )

    @display(description="نقش")
    def role_badge(self, obj):
        colors = {
            "owner": ("#eab308", "👑 مالک"),
            "admin": ("#3b82f6", "🛡 ادمین"),
            "vip": ("#a855f7", "⭐ ویژه"),
            "banned": ("#ef4444", "🚫 بن"),
            "muted": ("#f97316", "🔇 سکوت"),
            "member": ("#22c55e", "👤 عضو"),
        }
        color, label = colors.get(obj.role, ("#94a3b8", obj.role))
        return format_html('<span style="color:{};font-weight:700">{}</span>', color, label)

    @display(description="کارت‌ها")
    def cards_display(self, obj):
        cards = [c for c in [obj.card_number, obj.card_number2, obj.card_number3] if c]
        if not cards:
            return "—"
        html = "<br>".join(
            format_html(
                '<code style="font-size:11px">{}—{}—{}—{}</code>',
                c[:4], c[4:8], c[8:12], c[12:],
            )
            for c in cards
        )
        return mark_safe(html)


@admin.register(LearnedResponse)
class LearnedResponseAdmin(ModelAdmin):
    list_display = ("trigger", "short_response", "group", "created_by", "created_at")
    search_fields = ("trigger", "response")
    list_filter = ("group",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("group",)

    @display(description="پاسخ")
    def short_response(self, obj):
        return obj.response[:60] + "..." if len(obj.response) > 60 else obj.response


@admin.register(DiceRollStat)
class DiceRollStatAdmin(ModelAdmin):
    list_display = ("telegram_user_id", "telegram_chat_id", "value_display", "rolled_at")
    list_filter = ("value",)
    search_fields = ("telegram_user_id", "telegram_chat_id")
    ordering = ("-rolled_at",)
    date_hierarchy = "rolled_at"

    @display(description="عدد")
    def value_display(self, obj):
        faces = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
        return format_html(
            '<span style="font-size:20px">{}</span> &nbsp; {}',
            faces.get(obj.value, obj.value), obj.value,
        )


@admin.register(License)
class LicenseAdmin(ModelAdmin):
    list_display = ("code", "duration_days", "created_by", "is_used", "used_by_group", "used_at", "created_at")
    list_filter = ("is_used",)
    search_fields = ("code", "created_by")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "used_at")
    autocomplete_fields = ("used_by_group",)


@admin.register(TelegramUser)
class TelegramUserAdmin(ModelAdmin):
    list_display = ("telegram_user_id", "telegram_chat_id", "created_at")
    search_fields = ("telegram_user_id", "telegram_chat_id")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


@admin.register(Note)
class NoteAdmin(ModelAdmin):
    list_display = ("name", "group", "short_content", "created_by", "created_at")
    search_fields = ("name", "content")
    list_filter = ("group",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("group",)

    @display(description="محتوا")
    def short_content(self, obj):
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content


@admin.register(WalletTransaction)
class WalletTransactionAdmin(ModelAdmin):
    list_display = (
        "id", "telegram_chat_id", "telegram_user_id",
        "type_badge", "amount", "balance_after", "admin_id", "created_at",
    )
    list_filter = ("type",)
    search_fields = ("telegram_chat_id", "telegram_user_id", "description")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
    list_per_page = 50
    list_filter_submit = True

    @display(description="نوع")
    def type_badge(self, obj):
        colors = {
            "admin_increase": "#22c55e",
            "admin_decrease": "#ef4444",
            "admin_clear": "#f59e0b",
            "bet": "#3b82f6",
            "win": "#a855f7",
            "fee": "#06b6d4",
        }
        color = colors.get(obj.type, "#94a3b8")
        label = dict(obj.TYPES).get(obj.type, obj.type)
        return format_html(
            '<span style="color:{};font-weight:700">{}</span>', color, label,
        )
