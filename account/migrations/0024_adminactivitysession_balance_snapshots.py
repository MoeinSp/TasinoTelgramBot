from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0023_telegramgroup_min_withdrawal_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="adminactivitysession",
            name="start_group_balance",
            field=models.BigIntegerField(blank=True, null=True, verbose_name="تراز کل گروه در شروع"),
        ),
        migrations.AddField(
            model_name="adminactivitysession",
            name="end_group_balance",
            field=models.BigIntegerField(blank=True, null=True, verbose_name="تراز کل گروه در پایان"),
        ),
    ]
