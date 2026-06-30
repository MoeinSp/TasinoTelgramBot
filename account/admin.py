from django.contrib import admin
from django.utils.html import format_html
from .models import TelegramGroup, TelegramGroupMember, LearnedResponse, DiceRollStat, License, TelegramUser


# ─── گروه‌ها ──────────────────────────────────────────────────────────────────

@admin.register(TelegramGroup)
class TelegramGroupAdmin(admin.ModelAdmin):
    list_display = (
        "telegram_chat_id", "name", "theme",
        "status_badges", "fee_percent", "max_warnings", "subscription_until", "created_at",
    )
    list_filter = ("off", "is_speaker_enabled", "group_lock", "dice_option", "is_active")
    search_fields = ("telegram_chat_id", "name")
    readonly_fields = ("created_at",)
    list_editable = ("fee_percent", "max_warnings")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        ("اطلاعات اصلی", {
            "fields": ("telegram_chat_id", "name", "theme", "created_at")
        }),
        ("وضعیت ربات", {
            "fields": ("off", "is_active", "is_speaker_enabled", "group_lock", "dice_option", "warning_enabled")
        }),
        ("تنظیمات", {
            "fields": ("max_warnings", "fee_percent", "subscription_until")
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

    def status_badges(self, obj):
        badges = []
        if obj.off:
            badges.append('<span style="color:red">⛔ خاموش</span>')
        else:
            badges.append('<span style="color:green">✅ فعال</span>')
        if obj.is_speaker_enabled:
            badges.append('<span style="color:#2196F3">🔊 سخنگو</span>')
        if obj.group_lock:
            badges.append('<span style="color:orange">🔒 قفل</span>')
        return format_html(" &nbsp; ".join(badges))
    status_badges.short_description = "وضعیت"


# ─── اعضا ─────────────────────────────────────────────────────────────────────

@admin.register(TelegramGroupMember)
class TelegramGroupMemberAdmin(admin.ModelAdmin):
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

    fieldsets = (
        ("شناسه", {
            "fields": ("telegram_chat_id", "telegram_user_id", "group", "alias")
        }),
        ("نقش", {
            "fields": ("role", "is_owner", "is_admin", "is_vip")
        }),
        ("آمار فعالیت", {
            "fields": ("level", "xp_total", "message_count", "warnings")
        }),
        ("مالی", {
            "fields": ("point",)
        }),
        ("کارت بانکی", {
            "fields": ("card_number", "card_number2", "card_number3", "card_name")
        }),
        ("تاریخ", {
            "fields": ("added_at",)
        }),
    )

    def role_badge(self, obj):
        colors = {
            "owner": ("#FFD700", "👑 مالک"),
            "admin": ("#2196F3", "🛡 ادمین"),
            "vip": ("#9C27B0", "⭐ ویژه"),
            "banned": ("#f44336", "🚫 بن"),
            "muted": ("#FF9800", "🔇 سکوت"),
            "member": ("#4CAF50", "👤 عضو"),
        }
        color, label = colors.get(obj.role, ("#999", obj.role))
        return format_html(
            '<span style="color:{};font-weight:bold">{}</span>', color, label
        )
    role_badge.short_description = "نقش"

    def cards_display(self, obj):
        cards = [c for c in [obj.card_number, obj.card_number2, obj.card_number3] if c]
        if not cards:
            return "—"
        return format_html("<br>".join(
            f'<code style="font-size:11px">{c[:4]}—{c[4:8]}—{c[8:12]}—{c[12:]}</code>'
            for c in cards
        ))
    cards_display.short_description = "کارت‌ها"


# ─── یادگیری ──────────────────────────────────────────────────────────────────

@admin.register(LearnedResponse)
class LearnedResponseAdmin(admin.ModelAdmin):
    list_display = ("trigger", "short_response", "group", "created_by", "created_at")
    search_fields = ("trigger", "response")
    list_filter = ("group",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    def short_response(self, obj):
        return obj.response[:60] + "..." if len(obj.response) > 60 else obj.response
    short_response.short_description = "پاسخ"


# ─── آمار تاس ─────────────────────────────────────────────────────────────────

@admin.register(DiceRollStat)
class DiceRollStatAdmin(admin.ModelAdmin):
    list_display = ("telegram_user_id", "telegram_chat_id", "value_display", "rolled_at")
    list_filter = ("value",)
    search_fields = ("telegram_user_id", "telegram_chat_id")
    ordering = ("-rolled_at",)
    date_hierarchy = "rolled_at"

    def value_display(self, obj):
        faces = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
        return format_html(
            '<span style="font-size:20px">{}</span> &nbsp; {}',
            faces.get(obj.value, obj.value), obj.value
        )
    value_display.short_description = "عدد"


# ─── لایسنس ───────────────────────────────────────────────────────────────────

@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
    list_display = ("code", "duration_days", "created_by", "is_used", "used_by_group", "used_at", "created_at")
    list_filter = ("is_used",)
    search_fields = ("code", "created_by")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "used_at")
