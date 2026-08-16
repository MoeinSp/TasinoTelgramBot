from django.db import migrations, models

from account import migration_utils as idem


TG = "account_telegramgroup"


def forwards(apps, schema_editor):
    idem.add_column_sql(
        schema_editor, TG, "pv_chat_enabled", "boolean DEFAULT true NOT NULL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0039_telegramgroup_pv_soft_timeout"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="telegramgroup",
                    name="pv_chat_enabled",
                    field=models.BooleanField(
                        default=True,
                        help_text="اگر خاموش باشد، چت/واکنش داخل بازی پیوی برای اعضای گروه غیرفعال است.",
                        verbose_name="چت پیوی",
                    ),
                ),
            ],
        ),
    ]
