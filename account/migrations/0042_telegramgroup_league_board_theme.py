from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0041_telegramgroup_stat_week_prizes"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="league_board_theme",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="شماره تم نمایش جدول لیگ (۱ تا ۱۰).",
                verbose_name="تم جدول لیگ",
            ),
        ),
    ]
