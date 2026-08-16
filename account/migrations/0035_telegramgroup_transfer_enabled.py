from django.db import migrations, models

from account import migration_utils as idem


TG = "account_telegramgroup"


def forwards(apps, schema_editor):
    idem.add_column_sql(
        schema_editor, TG, "transfer_enabled", "boolean DEFAULT true NOT NULL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0034_telegramgroup_pv_results_chat_id"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="telegramgroup",
                    name="transfer_enabled",
                    field=models.BooleanField(
                        default=True,
                        help_text="اگر خاموش باشد، دستور انتقال موجودی در گروه کار نمی‌کند.",
                        verbose_name="انتقال موجودی",
                    ),
                ),
            ],
        ),
    ]
