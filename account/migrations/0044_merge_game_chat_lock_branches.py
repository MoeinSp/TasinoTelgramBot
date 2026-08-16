# Merge دو شاخهٔ account:
# - 0034_telegramgroup_game_chat_lock_and_more (شاخهٔ قدیمی/سرور)
# - 0043_rename_... (شاخهٔ اصلی)
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0034_telegramgroup_game_chat_lock_and_more"),
        ("account", "0043_rename_account_lea_telegra_wager_idx_account_lea_telegra_40418d_idx_and_more"),
    ]

    operations = []
