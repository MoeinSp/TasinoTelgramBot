from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0022_telegramgroup_pv_admin_finance_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="min_withdrawal_amount",
            field=models.PositiveIntegerField(
                default=0,
                help_text="۰ = غیرفعال. مثلاً ۵۰ یعنی کاربر با موجودی قابل تسویه زیر ۵۰ نمی‌تواند درخواست تسویه بدهد.",
                verbose_name="حداقل مبلغ تسویه کاربر",
            ),
        ),
    ]
