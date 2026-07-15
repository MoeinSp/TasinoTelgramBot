from django.db import models


class AdLoadout(models.Model):
    """برنامه ساعت روزانه: هر ردیف = ساعت + نوع تبلیغ."""

    MODE_CHOICES = (
        ("group", "تبلیغ گروه"),
        ("pv", "تبلیغ ربات"),
        ("bomb", "بمب"),
        ("super", "سوپر بمب"),
    )
    MODE_KEYS = {k for k, _ in MODE_CHOICES}

    name = models.CharField(max_length=120, verbose_name="نام برنامه")
    # [{"time": "09:00", "mode": "group"}, ...] — ۲۵:۰۰ = ۱ شب فردا
    slots = models.JSONField(default=list, verbose_name="ردیف‌ها")
    default_mode = models.CharField(
        max_length=16,
        choices=MODE_CHOICES,
        default="bomb",
        verbose_name="نوع پیش‌فرض (سازگاری)",
    )
    queue_ad_until_message = models.BooleanField(default=False)
    ignore_group_ad_setting = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    is_favorite = models.BooleanField(default=True, verbose_name="فعال برای پنل امروز")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "برنامه ساعت"
        verbose_name_plural = "برنامه‌های ساعت"
        ordering = ["-is_favorite", "name"]

    def __str__(self):
        return f"{self.name} ({len(self.normalized_entries())} ردیف)"

    def normalized_entries(self) -> list[dict]:
        from .services import parse_time, _slot_sort_key

        out = []
        seen = set()
        for raw in self.slots or []:
            if isinstance(raw, dict):
                t = parse_time(raw.get("time") or raw.get("slot") or "")
                mode = str(raw.get("mode") or self.default_mode or "bomb").strip()
            else:
                t = parse_time(raw)
                mode = self.default_mode or "bomb"
            if not t:
                continue
            if mode not in self.MODE_KEYS:
                mode = "bomb"
            key = (t, mode)
            if key in seen:
                continue
            seen.add(key)
            out.append({"time": t, "mode": mode})
        return sorted(out, key=lambda e: _slot_sort_key(e["time"]))

    def normalized_slots(self) -> list[str]:
        return [e["time"] for e in self.normalized_entries()]
