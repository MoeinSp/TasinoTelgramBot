from django.db import migrations, models

from account import migration_utils as idem


TG = "account_telegramgroup"


def forwards(apps, schema_editor):
    idem.add_column_sql(
        schema_editor, TG, "pv_soft_timeout", "boolean DEFAULT false NOT NULL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0038_telegramgroup_game_chat_lock"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="telegramgroup",
                    name="pv_soft_timeout",
                    field=models.BooleanField(
                        default=False,
                        help_text="اگر روشن باشد، تاخیر در تاس‌تعیین/انتخاب راند/قبل از اولین تاس بازی اصلی باعث باخت نمی‌شود (بازی لغو می‌شود).",
                        verbose_name="باخت پیوی خاموش",
                    ),
                ),
            ],
        ),
    ]
