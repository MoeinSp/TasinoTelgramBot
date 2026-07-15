from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("account", "0017_admin_accounting_withdrawal")]
    operations = [
        migrations.AddField("wallettransaction", "receipt_file_id", models.TextField(blank=True, default="")),
        migrations.AddField("wallettransaction", "receipt_note", models.CharField(blank=True, default="", max_length=256)),
    ]
