from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bot_setting", "0003_bot_site_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="botsiteconfig",
            name="premium_emoji_ids",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='مثل {"rose":"5287...","dice":"123..."}',
                verbose_name="شناسه ایموجی‌های پرمیوم",
            ),
        ),
    ]
