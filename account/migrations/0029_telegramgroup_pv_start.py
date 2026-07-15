from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0028_financerequestban"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="pv_start_enabled",
            field=models.BooleanField(
                default=False,
                help_text="اجازه شروع مسابقه تاس دونفره در پیوی ربات.",
                verbose_name="شروع پیوی",
            ),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="pv_start_off_reason",
            field=models.CharField(
                blank=True,
                default="",
                max_length=300,
                verbose_name="دلیل خاموش بودن شروع پیوی",
            ),
        ),
    ]
