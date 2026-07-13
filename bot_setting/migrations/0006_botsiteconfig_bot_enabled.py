from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bot_setting", "0005_botsiteconfig_dice_themes"),
    ]

    operations = [
        migrations.AddField(
            model_name="botsiteconfig",
            name="bot_enabled",
            field=models.BooleanField(
                default=True,
                help_text="اگر خاموش باشد، ربات در همه گروه‌ها و پیوی (به‌جز سازنده) پاسخ نمی‌دهد. قبل از بکاپ/بازیابی خاموش کنید.",
                verbose_name="ربات روشن (سراسری)",
            ),
        ),
    ]
