from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AdLoadout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, verbose_name="نام قالب")),
                (
                    "slots",
                    models.JSONField(
                        default=list,
                        help_text='لیست ساعت‌ها مثل ["10:00","12:00","14:00"]',
                        verbose_name="ساعت‌ها",
                    ),
                ),
                (
                    "default_mode",
                    models.CharField(
                        choices=[
                            ("group", "تبلیغ گروه"),
                            ("pv", "تبلیغ ربات (پیوی)"),
                            ("bomb", "بمب (گروه + ربات)"),
                            ("super", "سوپر بمب (گروه + ربات + جوین)"),
                        ],
                        default="bomb",
                        max_length=16,
                        verbose_name="حالت پیش‌فرض",
                    ),
                ),
                ("queue_ad_until_message", models.BooleanField(default=False, verbose_name="صف تا پیام بعدی گروه")),
                (
                    "ignore_group_ad_setting",
                    models.BooleanField(default=False, verbose_name="اطلاعیه (نادیده گرفتن خاموشی تبلیغ گروه)"),
                ),
                ("notes", models.TextField(blank=True, default="", verbose_name="یادداشت")),
                ("is_favorite", models.BooleanField(default=False, verbose_name="علاقه‌مندی")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "قالب تبلیغ (Loadout)",
                "verbose_name_plural": "قالب‌های تبلیغ (Loadout)",
                "ordering": ["-is_favorite", "name"],
            },
        ),
    ]
