"""داشبورد آماری پنل ادمین تاسینو."""
from django.utils import timezone


def dashboard_callback(request, context):
    from account.models import TelegramGroup, TelegramGroupMember, WalletTransaction, License
    from bot_setting.models import BotSiteConfig, ForcedJoinConfig
    from scheduledmessage.models import ScheduledMessage
    from wordfilter.models import WordFilter

    today = timezone.localdate()
    groups_total = TelegramGroup.objects.count()
    groups_active = TelegramGroup.objects.filter(is_active=True, off=False).count()
    members_total = TelegramGroupMember.objects.count()
    owners = TelegramGroupMember.objects.filter(is_owner=True).count()
    tx_today = WalletTransaction.objects.filter(created_at__date=today).count()
    fee_today = (
        WalletTransaction.objects
        .filter(created_at__date=today, type="fee")
        .count()
    )
    licenses_free = License.objects.filter(is_used=False).count()
    sched_active = ScheduledMessage.objects.filter(is_active=True).count()
    filters_count = WordFilter.objects.count()

    site = BotSiteConfig.get_singleton()
    fj = ForcedJoinConfig.get_singleton()

    context.update({
        "tasino_stats": [
            {"title": "گروه‌های فعال", "metric": f"{groups_active} / {groups_total}", "icon": "groups"},
            {"title": "اعضا", "metric": f"{members_total:,}", "footer": f"{owners} مالک"},
            {"title": "تراکنش امروز", "metric": f"{tx_today:,}", "footer": f"{fee_today} حق واسطه"},
            {"title": "لایسنس آزاد", "metric": f"{licenses_free:,}"},
            {"title": "پیام زمان‌بندی", "metric": f"{sched_active:,}"},
            {"title": "فیلتر کلمه", "metric": f"{filters_count:,}"},
        ],
        "tasino_links": {
            "link_directory": site.link_directory_url,
            "support": site.support_url,
            "forced_join": "فعال" if fj.enabled else "خاموش",
            "forced_channel": fj.channel_title or fj.channel_username or "—",
            "bot_enabled": bool(getattr(site, "bot_enabled", True)),
        },
    })
    return context
