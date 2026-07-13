from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0011_telegramgroupmember_balance_hidden"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroupmember",
            name="accounts_hidden",
            field=models.BooleanField(
                default=False,
                verbose_name="لیست حساب‌ها مخفی (پیوی)",
            ),
        ),
    ]
