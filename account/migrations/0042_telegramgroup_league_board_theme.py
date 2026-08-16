from django.db import migrations, models

from account import migration_utils as idem


TG = "account_telegramgroup"


def forwards(apps, schema_editor):
    idem.add_column_sql(
        schema_editor, TG, "league_board_theme", "smallint DEFAULT 1 NOT NULL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0041_telegramgroup_stat_week_prizes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="telegramgroup",
                    name="league_board_theme",
                    field=models.PositiveSmallIntegerField(
                        default=1,
                        help_text="شماره تم نمایش جدول لیگ (۱ تا ۱۰).",
                        verbose_name="تم جدول لیگ",
                    ),
                ),
            ],
        ),
    ]
