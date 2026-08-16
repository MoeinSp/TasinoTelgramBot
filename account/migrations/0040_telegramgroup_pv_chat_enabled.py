from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0039_telegramgroup_pv_soft_timeout"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="pv_chat_enabled",
            field=models.BooleanField(
                default=True,
                help_text="اگر خاموش باشد، چت/واکنش داخل بازی پیوی برای اعضای گروه غیرفعال است.",
                verbose_name="چت پیوی",
            ),
        ),
    ]
