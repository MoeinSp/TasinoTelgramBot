from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0029_telegramgroup_pv_start"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="min_pv_bet",
            field=models.PositiveIntegerField(
                default=0,
                help_text="۰ = فقط حداقل سراسری. مثلاً ۳۰ یعنی شروع پیوی با شرط کمتر از ۳۰ قبول نمی‌شود.",
                verbose_name="حداقل مبلغ شرط پیوی",
            ),
        ),
    ]
