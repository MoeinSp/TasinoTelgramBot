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

    dice_turn_limit = models.PositiveIntegerField(
        default=0,
        verbose_name="محدودیت تعداد نوبت تاس",
        help_text="۰ = بدون محدودیت. مثلاً ۲ یعنی همه تاس‌ها باید در دقیقاً ۲ نوبت ریخته شوند.",
    )

    warning_enabled = models.BooleanField(
        default=True,
        verbose_name="اخطار خودکار"
    )
    quiet_extra = models.BooleanField(
        default=False,
        verbose_name="کم پیام",
        help_text="با روشن بودن، پیام‌های تکراری مثل «توی این بازی نیستی» و «قابلیت غیرفعال» ارسال نمی‌شوند.",
    )

    pv_start_enabled = models.BooleanField(
        default=False,
        verbose_name="شروع پیوی",
        help_text="اجازه شروع مسابقه تاس دونفره در پیوی ربات.",
    )
    pv_start_off_reason = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="دلیل خاموش بودن شروع پیوی",
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

    fee_hidden = models.BooleanField(
        default=False,
        verbose_name="مخفی بودن حق واسطه برای مدیران"
    )

    bet_mode = models.CharField(
        max_length=10,
        default="fixed",
        choices=(
            ("fixed", "فیکس"),
            ("extra", "اضافه"),
        ),
        verbose_name="حالت بازی (پیش‌فرض)",
        help_text="برای «شروع ۲ ۵۰» بدون ذکر حالت. پیش‌فرض: فیکس",
    )

    increase_hidden = models.BooleanField(
        default=False,
        verbose_name="افزایش موجودی مخفی",
        help_text="اگر روشن باشد، ادمین فقط «افزایش موجودی» می‌زند و مبلغ را در پیوی وارد می‌کند.",
    )

    pv_admin_finance_enabled = models.BooleanField(
        default=False,
        verbose_name="دسترسی ادمین به پنل مالی پیوی",
        help_text="اگر روشن باشد، ادمین‌ها در پیوی همان گزارش‌های مالی مالک را می‌بینند.",
    )

    min_withdrawal_amount = models.PositiveIntegerField(
        default=0,
        verbose_name="حداقل مبلغ تسویه کاربر",
        help_text="۰ = غیرفعال. مثلاً ۵۰ یعنی کاربر با موجودی قابل تسویه زیر ۵۰ نمی‌تواند درخواست تسویه بدهد.",
    )

    min_pv_bet = models.PositiveIntegerField(
        default=0,
        verbose_name="حداقل مبلغ شرط پیوی",
        help_text="۰ = فقط حداقل سراسری. مثلاً ۳۰ یعنی شروع پیوی با شرط کمتر از ۳۰ قبول نمی‌شود.",
    )

    game_seq = models.PositiveIntegerField(
        default=0,
        verbose_name="شمارنده آیدی بازی",
        help_text="آخرین شمارهٔ اختصاص‌داده‌شده به مسابقات این گروه (آیدی بازی).",
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

    balance_hidden = models.BooleanField(
        default=False,
        verbose_name="موجودی مخفی",
    )

    accounts_hidden = models.BooleanField(
        default=False,
        verbose_name="لیست حساب‌ها مخفی (پیوی)",
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


class DiceGameHistory(models.Model):
    """تاریخچه مسابقات تاس (برای آمار بازی، نه هر تاس تکی)."""
    telegram_chat_id = models.BigIntegerField(db_index=True)
    telegram_user_id = models.BigIntegerField()
    total = models.IntegerField()
    average = models.FloatField()
    count = models.IntegerField()
    winner = models.BooleanField(default=False)
    amount_won = models.IntegerField(default=0)
    bet_amount = models.IntegerField(default=0)
    game_session = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["telegram_chat_id", "created_at"]),
            models.Index(fields=["telegram_chat_id", "game_session"]),
        ]

    def __str__(self):
        return f"{self.telegram_chat_id} | {self.telegram_user_id} | {self.total}"


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
    receipt_file_id = models.TextField(blank=True, default="")
    receipt_note = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["telegram_chat_id", "telegram_user_id", "-created_at"]),
            models.Index(fields=["type"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.telegram_user_id} | {self.type} | {self.amount}"


class AdminAccounting(models.Model):
    telegram_chat_id = models.BigIntegerField(db_index=True)
    admin_id = models.BigIntegerField(db_index=True)
    share_percent = models.PositiveSmallIntegerField(default=50)
    is_active_cashier = models.BooleanField(default=False)
    activity_started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("telegram_chat_id", "admin_id"), name="uniq_telegram_admin_accounting")]


class AdminActivitySession(models.Model):
    telegram_chat_id = models.BigIntegerField(db_index=True)
    admin_id = models.BigIntegerField(db_index=True)
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    start_group_balance = models.BigIntegerField(null=True, blank=True, verbose_name="تراز کل گروه در شروع")
    end_group_balance = models.BigIntegerField(null=True, blank=True, verbose_name="تراز کل گروه در پایان")

    class Meta:
        indexes = [
            models.Index(fields=["telegram_chat_id", "-started_at"]),
            models.Index(fields=["telegram_chat_id", "admin_id", "-started_at"]),
        ]
        ordering = ["-started_at"]


class WithdrawalRequest(models.Model):
    STATUS = (("pending", "Pending"), ("receipt", "Waiting Receipt"), ("done", "Done"), ("cancelled", "Cancelled"))
    telegram_chat_id = models.BigIntegerField(db_index=True)
    telegram_user_id = models.BigIntegerField(db_index=True)
    amount = models.BigIntegerField(default=0)
    card_number = models.CharField(max_length=16)
    card_name = models.CharField(max_length=100)
    settle_kind = models.CharField(
        max_length=16,
        blank=True,
        default="custom",
        help_text="full=تسویه کامل، custom=مبلغ دلخواه",
    )
    status = models.CharField(max_length=16, choices=STATUS, default="pending", db_index=True)
    approved_by = models.BigIntegerField(null=True, blank=True)
    receipt_file_id = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class BalanceIncreaseRequest(models.Model):
    STATUS = (("waiting_receipt", "Waiting receipt"), ("pending", "Pending"), ("approved", "Approved"), ("cancelled", "Cancelled"))
    telegram_chat_id = models.BigIntegerField(db_index=True)
    telegram_user_id = models.BigIntegerField(db_index=True)
    amount = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=STATUS, default="waiting_receipt", db_index=True)
    receipt_file_id = models.TextField(blank=True, default="")
    receipt_note = models.CharField(max_length=32, blank=True, default="")
    approved_by = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)


class FinanceRequestBan(models.Model):
    """مسدودسازی فقط برای درخواست افزایش/تسویه — بدون بن از گروه."""
    telegram_chat_id = models.BigIntegerField(db_index=True)
    telegram_user_id = models.BigIntegerField(db_index=True)
    banned_by = models.BigIntegerField(null=True, blank=True)
    reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["telegram_chat_id", "telegram_user_id"],
                name="uniq_tg_finance_request_ban",
            ),
        ]
        indexes = [
            models.Index(fields=["telegram_chat_id", "telegram_user_id"]),
        ]


class GroupChallenge(models.Model):
    TYPES = (
        ("dice", "چالش تاس"),
        ("dart", "چالش دارت"),
        ("luck", "چالش شانس"),
        ("football", "چالش فوتبال"),
        ("basketball", "چالش بسکتبال"),
        ("max_bet", "بیشترین مبلغ شرط"),
        ("max_count", "بیشترین تعداد"),
        ("max_increase", "بیشترین افزایش موجودی"),
        ("sum_increase", "مجموع افزایش موجودی"),
    )
    STATUS = (
        ("active", "فعال"),
        ("ended", "پایان‌یافته"),
        ("cancelled", "لغو شده"),
    )

    telegram_chat_id = models.BigIntegerField(db_index=True)
    created_by = models.BigIntegerField(db_index=True)
    challenge_type = models.CharField(max_length=32, choices=TYPES, db_index=True)
    prize_amount = models.BigIntegerField(default=0)
    min_games_today = models.PositiveIntegerField(default=0)
    min_wallet = models.BigIntegerField(default=0)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=16, choices=STATUS, default="active", db_index=True)
    winner_id = models.BigIntegerField(null=True, blank=True)
    winner_score = models.BigIntegerField(default=0)
    settled = models.BooleanField(default=False)
    announce_message_id = models.BigIntegerField(null=True, blank=True)
    end_warning_sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["telegram_chat_id", "status", "end_at"]),
            models.Index(fields=["telegram_chat_id", "challenge_type", "status"]),
        ]
        ordering = ["-created_at"]


class ChallengeEntry(models.Model):
    challenge = models.ForeignKey(GroupChallenge, related_name="entries", on_delete=models.CASCADE)
    telegram_user_id = models.BigIntegerField(db_index=True)
    best_score = models.BigIntegerField(default=0)
    total_score = models.BigIntegerField(default=0)
    plays = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["challenge", "telegram_user_id"], name="uniq_tg_challenge_entry_user"),
        ]
        indexes = [
            models.Index(fields=["challenge", "-total_score"]),
            models.Index(fields=["challenge", "-best_score"]),
        ]


class GamePlayLog(models.Model):
    telegram_chat_id = models.BigIntegerField(db_index=True)
    telegram_user_id = models.BigIntegerField(db_index=True)
    game_type = models.CharField(max_length=32, db_index=True)
    score = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["telegram_chat_id", "telegram_user_id", "game_type", "created_at"]),
        ]
