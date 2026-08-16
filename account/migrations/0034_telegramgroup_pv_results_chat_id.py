from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0033_rename_acct_act_sess_chat_start_account_adm_telegra_c2f23f_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="pv_results_chat_id",
            field=models.BigIntegerField(
                blank=True,
                help_text="اگر تنظیم شود، نتیجهٔ بازی‌های پیوی این گروه + شناسهٔ بازیکنان در آن گپ هم اعلام می‌شود.",
                null=True,
                verbose_name="گپ اعلام نتایج پیوی",
            ),
        ),
    ]
