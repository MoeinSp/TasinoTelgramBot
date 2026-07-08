from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0007_telegramgroup_telegram_emoji_enabled"),
    ]

    operations = [
        migrations.AlterField(
            model_name="telegramgroup",
            name="fee_percent",
            field=models.IntegerField(default=10, verbose_name="درصد کارمزد"),
        ),
    ]
