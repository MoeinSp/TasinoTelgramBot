from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bot_setting", "0010_botsiteconfig_admin_sensitive_hidden"),
    ]

    operations = [
        migrations.CreateModel(
            name="ButtonEmojiOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(help_text="کلید ثبت‌شده در BUTTON_EMOJI_DEFS (مثل btn_start).", max_length=64, unique=True, verbose_name="کلید دکمه")),
                ("custom_emoji_id", models.CharField(help_text="custom_emoji_id گرفته‌شده از پیام ایموجی پرمیوم مالک.", max_length=64, verbose_name="شناسه ایموجی پرمیوم")),
                ("placeholder", models.CharField(blank=True, default="", help_text="ایموجی پایه (fallback) که زیر ایموجی پرمیوم قرار می‌گیرد.", max_length=16, verbose_name="ایموجی نمایشی")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "ایموجی دکمه",
                "verbose_name_plural": "ایموجی دکمه‌ها",
                "ordering": ["key"],
            },
        ),
    ]
