from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0015_alter_wallettransaction_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="fee_hidden",
            field=models.BooleanField(default=False, verbose_name="مخفی بودن حق واسطه برای مدیران"),
        ),
    ]
