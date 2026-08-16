from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0040_telegramgroup_pv_chat_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="prize_stat_games",
            field=models.PositiveIntegerField(
                default=0,
                help_text="جایزه نفر اول پربازی‌ترین در آمار روزانه (۰ = بدون جایزه).",
                verbose_name="جایزه آمار تعداد",
            ),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="prize_stat_max_bet",
            field=models.PositiveIntegerField(
                default=0,
                help_text="جایزه بیشترین شرط یک‌بازی در آمار روزانه (۰ = بدون جایزه).",
                verbose_name="جایزه آمار بیشترین شرط",
            ),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="prize_week_1",
            field=models.PositiveIntegerField(default=0, verbose_name="جایزه لیگ رتبه ۱"),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="prize_week_2",
            field=models.PositiveIntegerField(default=0, verbose_name="جایزه لیگ رتبه ۲"),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="prize_week_3",
            field=models.PositiveIntegerField(default=0, verbose_name="جایزه لیگ رتبه ۳"),
        ),
    ]
