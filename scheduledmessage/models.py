from django.db import models


class ScheduledMessage(models.Model):
    TYPES = (
        ("interval", "دوره‌ای (هر چند دقیقه یکبار)"),
        ("fixed", "زمان مشخص (تاریخ و ساعت)"),
    )

    title = models.CharField(
        max_length=100,
        verbose_name="عنوان پیام"
    )

    text = models.TextField(
        verbose_name="متن پیام"
    )

    queue_ad_until_message = models.BooleanField(
        default=False,
        verbose_name="تعویق تبلیغات تا ارسال پیام"
    )

    send_to_pv = models.BooleanField(
        default=False,
        verbose_name="ارسال به پیوی"
    )

    send_to_all = models.BooleanField(
        default=False,
        verbose_name="ارسال به همه گروه‌ها"
    )

    chat_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="شناسه گروه"
    )

    type = models.CharField(
        max_length=10,
        choices=TYPES,
        default="interval",
        verbose_name="نوع زمان‌بندی"
    )

    # مخصوص پیام‌های دوره‌ای
    interval_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="فاصله زمانی (دقیقه)"
    )

    ignore_group_ad_setting = models.BooleanField(
        default=False,
        verbose_name="نادیده گرفتن تنظیمات تبلیغات گروه",
        help_text="اگر فعال باشد حتی گروه‌هایی که تبلیغات را خاموش کرده‌اند نیز پیام را دریافت می‌کنند."
    )

    # مخصوص زمان مشخص
    run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان دقیق ارسال"
    )

    last_sent = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="آخرین ارسال"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد"
    )

    def __str__(self):
        return f"{self.title} - {self.get_type_display()}"

    class Meta:
        verbose_name = "پیام زمان‌بندی‌شده"
        verbose_name_plural = "پیام‌های زمان‌بندی‌شده"

        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["run_at"]),
            models.Index(fields=["chat_id"]),
        ]

        ordering = [
            "-is_active",
            "-id",
        ]