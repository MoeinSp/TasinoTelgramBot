from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0025_groupchallenge"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="quiet_extra",
            field=models.BooleanField(
                default=False,
                help_text="با روشن بودن، پیام‌های تکراری مثل «توی این بازی نیستی» و «قابلیت غیرفعال» ارسال نمی‌شوند.",
                verbose_name="کم پیام",
            ),
        ),
    ]
