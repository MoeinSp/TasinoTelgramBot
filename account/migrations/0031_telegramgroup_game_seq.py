from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0030_telegramgroup_min_pv_bet"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="game_seq",
            field=models.PositiveIntegerField(
                default=0,
                help_text="آخرین شمارهٔ اختصاص‌داده‌شده به مسابقات این گروه (آیدی بازی).",
                verbose_name="شمارنده آیدی بازی",
            ),
        ),
    ]
