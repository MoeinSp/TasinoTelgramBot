# این فایل فقط برای سازگاری با دیپلوی‌هایی است که قبلاً
# شاخهٔ موازی 0034_telegramgroup_game_chat_lock_and_more ساخته بودند.
# فیلد واقعی game_chat_lock در 0038_telegramgroup_game_chat_lock اعمال می‌شود.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0033_rename_acct_act_sess_chat_start_account_adm_telegra_c2f23f_idx_and_more"),
    ]

    operations = []
