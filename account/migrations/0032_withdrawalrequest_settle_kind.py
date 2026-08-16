from django.db import migrations, models


class Migration(migrations.Migration):
    """Idempotent: ستون ممکن است از قبل روی DB موجود باشد."""

    dependencies = [
        ("account", "0031_telegramgroup_game_seq"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="withdrawalrequest",
                    name="settle_kind",
                    field=models.CharField(
                        blank=True,
                        default="custom",
                        help_text="full=تسویه کامل، custom=مبلغ دلخواه",
                        max_length=16,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "account_withdrawalrequest" '
                        "ADD COLUMN IF NOT EXISTS settle_kind varchar(16) "
                        "DEFAULT 'custom' NOT NULL;"
                    ),
                    reverse_sql=(
                        'ALTER TABLE "account_withdrawalrequest" '
                        "DROP COLUMN IF EXISTS settle_kind;"
                    ),
                ),
            ],
        ),
    ]
