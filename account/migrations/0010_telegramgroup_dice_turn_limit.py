from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0009_wallet_transaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="dice_turn_limit",
            field=models.PositiveIntegerField(
                default=0,
                help_text="۰ = بدون محدودیت. مثلاً ۲ یعنی همه تاس‌ها باید در دقیقاً ۲ نوبت ریخته شوند.",
                verbose_name="محدودیت تعداد نوبت تاس",
            ),
        ),
    ]
