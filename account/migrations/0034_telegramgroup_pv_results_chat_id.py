from django.db import migrations, models

from account import migration_utils as idem


TG = "account_telegramgroup"


def forwards(apps, schema_editor):
    idem.add_column_sql(schema_editor, TG, "pv_results_chat_id", "bigint NULL")


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0033_rename_acct_act_sess_chat_start_account_adm_telegra_c2f23f_idx_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="telegramgroup",
                    name="pv_results_chat_id",
                    field=models.BigIntegerField(
                        blank=True,
                        help_text="اگر تنظیم شود، نتیجهٔ بازی‌های پیوی این گروه + شناسهٔ بازیکنان در آن گپ هم اعلام می‌شود.",
                        null=True,
                        verbose_name="گپ اعلام نتایج پیوی",
                    ),
                ),
            ],
        ),
    ]
