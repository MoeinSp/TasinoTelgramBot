from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("account", "0018_wallettransaction_receipt_fields")]
    operations = [migrations.CreateModel(name="BalanceIncreaseRequest", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("telegram_chat_id", models.BigIntegerField(db_index=True)), ("telegram_user_id", models.BigIntegerField(db_index=True)),
        ("amount", models.BigIntegerField()), ("status", models.CharField(choices=[("waiting_receipt", "Waiting receipt"), ("pending", "Pending"), ("approved", "Approved"), ("cancelled", "Cancelled")], db_index=True, default="waiting_receipt", max_length=20)),
        ("receipt_file_id", models.TextField(blank=True, default="")), ("receipt_note", models.CharField(blank=True, default="", max_length=32)),
        ("approved_by", models.BigIntegerField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("approved_at", models.DateTimeField(blank=True, null=True)),
    ])]
