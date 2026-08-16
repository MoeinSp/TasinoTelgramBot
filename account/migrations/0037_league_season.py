from django.db import migrations, models

from account import migration_utils as idem


LS = "account_leaguestanding"


def forwards(apps, schema_editor):
    idem.add_column_sql(
        schema_editor,
        LS,
        "season_id",
        "varchar(16) DEFAULT '' NOT NULL",
    )
    idem.ensure_index(
        schema_editor,
        f'CREATE INDEX "account_lea_tg_season_idx" ON "{LS}" '
        f'("telegram_chat_id", "season_id", "wager_total" DESC);',
        "account_lea_tg_season_idx",
    )
    # plain db_index on season_id
    idem.ensure_index(
        schema_editor,
        f'CREATE INDEX "account_leaguestanding_season_id_idx" ON "{LS}" ("season_id");',
        "account_leaguestanding_season_id_idx",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0036_league"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="leaguestanding",
                    name="season_id",
                    field=models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="تاریخ شنبهٔ شروع هفته به صورت YYYY-MM-DD",
                        max_length=16,
                        verbose_name="شناسه هفته",
                    ),
                ),
                migrations.AddIndex(
                    model_name="leaguestanding",
                    index=models.Index(
                        fields=["telegram_chat_id", "season_id", "-wager_total"],
                        name="account_lea_tg_season_idx",
                    ),
                ),
            ],
        ),
    ]
