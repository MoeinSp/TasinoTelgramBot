from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0012_telegramgroupmember_accounts_hidden"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="bet_mode",
            field=models.CharField(
                choices=[("fixed", "فیکس"), ("extra", "اضافه")],
                default="fixed",
                help_text="برای «شروع ۲ ۵۰» بدون ذکر حالت. پیش‌فرض: فیکس",
                max_length=10,
                verbose_name="حالت بازی (پیش‌فرض)",
            ),
        ),
    ]
