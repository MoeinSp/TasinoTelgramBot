from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0038_telegramgroup_game_chat_lock"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="pv_soft_timeout",
            field=models.BooleanField(
                default=False,
                help_text="اگر روشن باشد، تاخیر در تاس‌تعیین/انتخاب راند/قبل از اولین تاس بازی اصلی باعث باخت نمی‌شود (بازی لغو می‌شود).",
                verbose_name="باخت پیوی خاموش",
            ),
        ),
    ]
