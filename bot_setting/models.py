from django.db import models
from django.core.cache import cache
from django.utils import timezone

class JoinMessage(models.Model):
    title = models.CharField(max_length=200, verbose_name="عنوان")
    text = models.TextField(verbose_name="متن پیام")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    priority = models.IntegerField(default=0, verbose_name="اولویت")

    is_forever = models.BooleanField(default=False, verbose_name="بدون انقضا")

    # ✅ بازه دقیق
    start_datetime = models.DateTimeField(null=True, blank=True, verbose_name="شروع نمایش")
    end_datetime = models.DateTimeField(null=True, blank=True, verbose_name="پایان نمایش")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['priority', '-created_at']

    def __str__(self):
        return self.title

    def is_active_now(self, check=None):
        if not self.is_active:
            return False

        if check is None:
            check = timezone.localtime(timezone.now())

        if self.is_forever:
            return True

        if self.start_datetime and self.end_datetime:
            return self.start_datetime <= check <= self.end_datetime

        return False


    @classmethod
    def get_join_message(cls):
        cache_key = 'join_active_message'
        cached = cache.get(cache_key)
        if cached is not None:  # اجازه میدیم None هم کش بشه
            return cached

        now = timezone.localtime(timezone.now())

        # گرفتن همه پیام‌های فعال
        messages = cls.objects.filter(is_active=True).order_by('priority', '-created_at')

        # جمع‌آوری متن همه پیام‌هایی که الان فعالن
        active_texts = []
        for msg in messages:
            if msg.is_active_now(now):
                active_texts.append(msg.text)

        # ساخت متن نهایی
        header = "❄️ برای استفاده از بات بصورت دائمی و رایگان حتما در کانال ها و گروه های زیر عضو شوید."

        if active_texts:
            body = "\n".join(active_texts)
            final_text = f"{header}\n\n{body}\n\n🟢 بعد از عضو شدن /start را ارسال کنید."
        else:
            final_text = f"{header}\n\n🟢 بعد از عضو شدن /start را ارسال کنید."

        cache.set(cache_key, final_text, 360)  # کش 60 ثانیه
        return final_text

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete('join_active_message')


class ForcedJoinConfig(models.Model):
    """تنظیم جوین اجباری کانال اصلی — یک رکورد (pk=1)."""
    enabled = models.BooleanField(default=False, verbose_name="فعال")
    channel_id = models.BigIntegerField(null=True, blank=True, verbose_name="شناسه کانال")
    channel_title = models.CharField(max_length=200, blank=True, default="", verbose_name="نام کانال")
    channel_username = models.CharField(max_length=100, blank=True, default="", verbose_name="یوزرنیم")
    invite_link = models.CharField(max_length=512, blank=True, default="", verbose_name="لینک دعوت")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "جوین اجباری کانال"
        verbose_name_plural = "جوین اجباری کانال"

    def __str__(self):
        return self.channel_title or str(self.channel_id or "—")

    @classmethod
    def get_singleton(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

class BotSiteConfig(models.Model):
    """تنظیمات سراسری ربات — یک رکورد (pk=1)."""
    link_directory_url = models.URLField(
        max_length=512,
        default="https://t.me/TasinoBot",
        verbose_name="لینک لینکدونی",
        help_text="آدرس دکمه «لینکدونی» در پیوی ربات",
    )
    link_directory_title = models.CharField(
        max_length=64,
        default="🔥 بزرگترین لینکدونی",
        verbose_name="متن دکمه لینکدونی",
    )
    support_url = models.URLField(
        max_length=512,
        default="https://t.me/Spayers",
        verbose_name="لینک پشتیبانی",
    )
    support_title = models.CharField(
        max_length=64,
        default="گروه پشتیبانی",
        verbose_name="عنوان پشتیبانی",
    )
    channel_url = models.URLField(
        max_length=512,
        blank=True,
        default="https://t.me/TasinoBot",
        verbose_name="لینک کانال رسمی",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیمات سراسری ربات"
        verbose_name_plural = "تنظیمات سراسری ربات"

    def __str__(self):
        return "تنظیمات سراسری تاسینو"

    @classmethod
    def get_singleton(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
