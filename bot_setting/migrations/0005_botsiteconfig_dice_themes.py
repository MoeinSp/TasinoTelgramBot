from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bot_setting", "0004_botsiteconfig_premium_emoji_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="botsiteconfig",
            name="dice_themes",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='مثل {"1":{"single_header":"..."},"16":{...}} — روی ۱۵ تم پیش‌فرض می‌نشیند',
                verbose_name="تم‌های سفارشی تاس",
            ),
        ),
    ]
