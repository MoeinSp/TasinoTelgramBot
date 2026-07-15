from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("account", "0016_telegramgroup_fee_hidden")]
    operations = [
        migrations.CreateModel(name="AdminAccounting", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("telegram_chat_id", models.BigIntegerField(db_index=True)), ("admin_id", models.BigIntegerField(db_index=True)),
            ("share_percent", models.PositiveSmallIntegerField(default=50)), ("is_active_cashier", models.BooleanField(default=False)),
            ("activity_started_at", models.DateTimeField(blank=True, null=True)),
        ], options={"constraints": [models.UniqueConstraint(fields=("telegram_chat_id", "admin_id"), name="uniq_telegram_admin_accounting")]}),
        migrations.CreateModel(name="WithdrawalRequest", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("telegram_chat_id", models.BigIntegerField(db_index=True)), ("telegram_user_id", models.BigIntegerField(db_index=True)),
            ("amount", models.BigIntegerField(default=0)), ("card_number", models.CharField(max_length=16)), ("card_name", models.CharField(max_length=100)),
            ("status", models.CharField(choices=[("pending", "Pending"), ("receipt", "Waiting Receipt"), ("done", "Done"), ("cancelled", "Cancelled")], db_index=True, default="pending", max_length=16)),
            ("approved_by", models.BigIntegerField(blank=True, null=True)), ("receipt_file_id", models.TextField(blank=True, default="")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("approved_at", models.DateTimeField(blank=True, null=True)), ("completed_at", models.DateTimeField(blank=True, null=True)),
        ]),
    ]
