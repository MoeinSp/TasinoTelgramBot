from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("account", "0020_dicegamehistory")]

    operations = [
        migrations.CreateModel(
            name="AdminActivitySession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_chat_id", models.BigIntegerField(db_index=True)),
                ("admin_id", models.BigIntegerField(db_index=True)),
                ("started_at", models.DateTimeField(db_index=True)),
                ("ended_at", models.DateTimeField(blank=True, db_index=True, null=True)),
            ],
            options={
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(fields=["telegram_chat_id", "-started_at"], name="acct_act_sess_chat_start"),
                    models.Index(fields=["telegram_chat_id", "admin_id", "-started_at"], name="acct_act_sess_chat_admin"),
                ],
            },
        ),
    ]
