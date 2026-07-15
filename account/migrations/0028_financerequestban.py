from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0027_groupchallenge_end_warning_sent_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="FinanceRequestBan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_chat_id", models.BigIntegerField(db_index=True)),
                ("telegram_user_id", models.BigIntegerField(db_index=True)),
                ("banned_by", models.BigIntegerField(blank=True, null=True)),
                ("reason", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["telegram_chat_id", "telegram_user_id"], name="account_fin_telegra_7f2a1b_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="financerequestban",
            constraint=models.UniqueConstraint(
                fields=("telegram_chat_id", "telegram_user_id"),
                name="uniq_tg_finance_request_ban",
            ),
        ),
    ]
