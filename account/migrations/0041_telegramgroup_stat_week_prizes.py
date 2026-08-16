from django.db import migrations, models

from account import migration_utils as idem


TG = "account_telegramgroup"


def forwards(apps, schema_editor):
    for col in (
        "prize_stat_game",
        "prize_stat_max_bet",
        "prize_week_1",
        "prize_week_2",
        "prize_week_3",
    ):
        idem.add_column_sql(schema_editor, TG, col, "integer DEFAULT 0 NOT NULL")


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0040_telegramgroup_pv_chat_enabled"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="telegramgroup",
                    name="prize_stat_game",
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
            ],
        ),
    ]
