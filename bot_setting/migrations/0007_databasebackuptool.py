from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bot_setting", "0006_botsiteconfig_bot_enabled"),
    ]

    operations = [
        migrations.CreateModel(
            name="DatabaseBackupTool",
            fields=[],
            options={
                "verbose_name": "بکاپ و بازیابی دیتابیس",
                "verbose_name_plural": "بکاپ و بازیابی دیتابیس",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("bot_setting.botsiteconfig",),
        ),
    ]
