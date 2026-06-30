from django.db import models


class WordFilter(models.Model):
    chat_id = models.BigIntegerField(
        verbose_name="شناسه گروه"
    )

    word = models.CharField(
        max_length=100,
        verbose_name="کلمه مسدود شده"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد"
    )

    class Meta:
        verbose_name = "کلمه فیلتر شده"
        verbose_name_plural = "کلمات فیلتر شده"

        unique_together = (
            "chat_id",
            "word"
        )

        indexes = [
            models.Index(
                fields=["chat_id"]
            )
        ]

        ordering = [
            "chat_id",
            "word"
        ]

    def __str__(self):
        return f"{self.word} @ {self.chat_id}"