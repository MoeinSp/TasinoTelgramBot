from django.db import models
from django.utils import timezone


def default_locks():
    return {
        "link": True,
        "forward": True,
        "username": True,
        "gif": False,
        "photo": False,
        "media": False,
        "bad_words": True,
        "edit_message": False,
        "fun_text": False,
        "sticker": False,
        "voice": False,
        "video": False,
        "video_note": False,
        "audio": False,
        "document": False,
        "contact": False,
        "location": False,
        "poll": False,
        "via_bot": False,
        "game": False,
    }


def default_commands():
    return [
        "جوک",
        "فال",
        "دانستنی",
        "فکت",
        "سخن",
        "معما",
        "دو راهی",
        "چالش",
        "شخصیت",

        "تاس",
        "بسکتبال",
        "پنالتی",
        "بولینگ",
        "سنگ کاغذ قیچی",
        "دارت",
        "شانس",
        "سکه",
        "اسلات",
        "بازی",
    ]


class TelegramGroup(models.Model):

    telegram_chat_id = models.BigIntegerField(
        unique=True,
        verbose_name="شناسه گروه تلگرام"
    )

    theme = models.IntegerField(
        default=1,
        verbose_name="تم"
    )

    max_warnings = models.IntegerField(
        default=3,
        verbose_name="حداکثر اخطار"
    )

    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="نام گروه"
    )

    off = models.BooleanField(
        default=False,
        verbose_name="خاموش بودن ربات"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد"
    )

    group_lock = models.BooleanField(
        default=False,
        verbose_name="قفل کلی گروه"
    )

    dice_option = models.BooleanField(
        default=True,
        verbose_name="تاس متوالی"
    )

    warning_enabled = models.BooleanField(
        default=True,
        verbose_name="اخطار خودکار"
    )

    is_speaker_enabled = models.BooleanField(
        default=False,
        verbose_name="اسپیکر فعال"
    )

    locks = models.JSONField(
        default=default_locks,
        verbose_name="قفل‌های گروه"
    )

    enabled_commands = models.JSONField(
        default=default_commands,
        verbose_name="دستورات فعال گروه"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال بودن گروه"
    )

    subscription_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاریخ انقضا"
    )

    ad_enabled = models.BooleanField(
        default=True,
        verbose_name="دریافت تبلیغات"
    )

    ad_disabled_until = models.DateTimeField(
        null=True,
        blank=True
    )

    fee_percent = models.IntegerField(
        default=10,
        verbose_name="درصد کارمزد"
    )

    welcome_enabled = models.BooleanField(
        default=True,
        verbose_name="خوشامدگویی فعال"
    )

    welcome_text = models.TextField(
        blank=True,
        null=True,
        verbose_name="متن خوشامدگویی"
    )

    welcome_gif_file_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="گیف خوشامدگویی"
    )

    anti_flood_enabled = models.BooleanField(
        default=False,
        verbose_name="آنتی فلود فعال"
    )

    anti_flood_limit = models.IntegerField(
        default=5,
        verbose_name="حد فلود (تعداد پیام)"
    )

    anti_flood_window = models.IntegerField(
        default=10,
        verbose_name="بازه فلود (ثانیه)"
    )

    captcha_enabled = models.BooleanField(
        default=False,
        verbose_name="کپچا فعال"
    )

    captcha_timeout = models.IntegerField(
        default=180,
        verbose_name="مهلت کپچا (ثانیه)"
    )

    antiraid_enabled = models.BooleanField(
        default=False,
        verbose_name="حالت ضد رید فعال"
    )

    log_channel_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="شناسه کانال لاگ"
    )

    rules_text = models.TextField(
        blank=True,
        null=True,
        verbose_name="قوانین گروه"
    )

    night_mode_enabled = models.BooleanField(
        default=False,
        verbose_name="حالت شب فعال"
    )

    night_start_hour = models.IntegerField(
        default=0,
        verbose_name="ساعت شروع حالت شب"
    )

    night_end_hour = models.IntegerField(
        default=8,
        verbose_name="ساعت پایان حالت شب"
    )

    telegram_emoji_enabled = models.BooleanField(
        default=False,
        verbose_name="استیکر/ایموجی متحرک تلگرام برای بازی‌ها"
    )

    def check_subscription(self):
        if (
            self.subscription_until and
            self.subscription_until > timezone.now()
        ):
            return True

        self.is_active = False
        return False

    def __str__(self):
        return self.name or str(self.telegram_chat_id)

    class Meta:
        verbose_name = "گروه"
        verbose_name_plural = "گروه‌ها"
        ordering = ["-created_at"]

class License(models.Model):

    code = models.CharField(
        max_length=50,
        unique=True
    )

    duration_days = models.IntegerField()

    created_by = models.BigIntegerField(
        verbose_name="سازنده"
    )

    used_by_group = models.ForeignKey(
        TelegramGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    used_by_owner = models.BigIntegerField(
        null=True,
        blank=True
    )

    is_used = models.BooleanField(
        default=False
    )

    used_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.code} - {self.duration_days} days"

class TelegramGroupMember(models.Model):

    telegram_chat_id = models.BigIntegerField(
        verbose_name="شناسه گروه"
    )

    group = models.ForeignKey(
        TelegramGroup,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="گروه"
    )

    telegram_user_id = models.BigIntegerField(
        verbose_name="شناسه کاربر"
    )

    card_number = models.CharField(
        max_length=16,
        null=True,
        blank=True
    )

    card_number2 = models.CharField(
        max_length=16,
        null=True,
        blank=True
    )

    card_number3 = models.CharField(
        max_length=16,
        null=True,
        blank=True
    )

    card_name = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    added_at = models.DateTimeField(
        auto_now_add=True
    )

    alias = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    point = models.IntegerField(
        default=0,
        null=True,
        blank=True
    )

    message_count = models.IntegerField(
        default=0
    )

    warnings = models.IntegerField(
        default=0
    )

    xp_total = models.IntegerField(
        default=0
    )

    level = models.IntegerField(
        default=1
    )

    role = models.CharField(
        max_length=20,
        default="member"
    )

    is_owner = models.BooleanField(
        default=False
    )

    is_admin = models.BooleanField(
        default=False
    )

    is_vip = models.BooleanField(
        default=False
    )

    def __str__(self):
        return self.alias or str(self.telegram_user_id)

    def add_xp(self, amount=2):
        self.xp_total += amount

        needed_xp = self.level * 100

        if self.xp_total >= needed_xp:
            self.xp_total -= needed_xp
            self.level += 1
            return True

        return False

    class Meta:
        verbose_name = "عضو گروه"
        verbose_name_plural = "اعضای گروه"

        indexes = [
            models.Index(
                fields=[
                    "telegram_chat_id",
                    "telegram_user_id"
                ]
            )
        ]

        ordering = [
            "-xp_total",
            "-level"
        ]


class TelegramUser(models.Model):

    telegram_user_id = models.BigIntegerField(
        null=True,
        blank=True
    )

    telegram_chat_id = models.BigIntegerField(
        unique=True,
        db_index=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["telegram_chat_id"]
            )
        ]


class LearnedResponse(models.Model):

    group = models.ForeignKey(
        TelegramGroup,
        on_delete=models.CASCADE,
        related_name="learned_responses"
    )

    trigger = models.CharField(
        max_length=255
    )

    response = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    created_by = models.BigIntegerField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.trigger} → {self.response}"

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "group",
                    "trigger"
                ]
            )
        ]


class DiceRollStat(models.Model):
    telegram_chat_id = models.BigIntegerField()
    telegram_user_id = models.BigIntegerField()
    value = models.SmallIntegerField()
    rolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["telegram_chat_id", "telegram_user_id", "rolled_at"]),
        ]

    def __str__(self):
        return f"{self.telegram_user_id} rolled {self.value} @ {self.rolled_at}"


class Note(models.Model):
    group = models.ForeignKey(
        TelegramGroup,
        on_delete=models.CASCADE,
        related_name="notes"
    )

    name = models.CharField(max_length=100)
    content = models.TextField()

    created_by = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("group", "name")]
        indexes = [
            models.Index(fields=["group", "name"]),
        ]

    def __str__(self):
        return f"#{self.name}"


class WalletTransaction(models.Model):
    TYPES = (
        ("admin_increase", "افزایش ادمین"),
        ("admin_decrease", "کاهش ادمین"),
        ("admin_clear", "تسویه"),
        ("bet", "شرط"),
        ("win", "برد"),
        ("fee", "حق واسطه"),
    )

    telegram_chat_id = models.BigIntegerField(db_index=True)
    telegram_user_id = models.BigIntegerField(db_index=True)
    admin_id = models.BigIntegerField(null=True, blank=True)
    type = models.CharField(max_length=32, choices=TYPES)
    amount = models.BigIntegerField()
    balance_after = models.BigIntegerField()
    description = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["telegram_chat_id", "telegram_user_id", "-created_at"]),
            models.Index(fields=["type"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.telegram_user_id} | {self.type} | {self.amount}"
