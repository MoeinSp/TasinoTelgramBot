from django.db import migrations, models

from account import migration_utils as idem


TG = "account_telegramgroup"


def forwards(apps, schema_editor):
    idem.add_column_sql(
        schema_editor, TG, "game_chat_lock", "boolean DEFAULT false NOT NULL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0037_league_season"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="telegramgroup",
                    name="game_chat_lock",
                    field=models.BooleanField(
                        default=False,
                        help_text="فقط پیام‌های بازی و پیشنهاد شرط (عدد / شروع …) مجاز؛ بقیه پاک می‌شود. ادمین و ویژه معاف‌اند.",
                        verbose_name="قفل بازی",
                    ),
                ),
            ],
        ),
    ]
