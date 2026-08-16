from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0037_league_season"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="game_chat_lock",
            field=models.BooleanField(
                default=False,
                help_text="فقط پیام‌های بازی و پیشنهاد شرط (عدد / شروع …) مجاز؛ بقیه پاک می‌شود. ادمین و ویژه معاف‌اند.",
                verbose_name="قفل بازی",
            ),
        ),
    ]
