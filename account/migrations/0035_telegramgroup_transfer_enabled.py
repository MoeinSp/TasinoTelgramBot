from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0034_telegramgroup_pv_results_chat_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="transfer_enabled",
            field=models.BooleanField(
                default=True,
                help_text="اگر خاموش باشد، دستور انتقال موجودی در گروه کار نمی‌کند.",
                verbose_name="انتقال موجودی",
            ),
        ),
    ]
