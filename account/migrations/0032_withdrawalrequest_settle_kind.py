from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0031_telegramgroup_game_seq"),
    ]

    operations = [
        migrations.AddField(
            model_name="withdrawalrequest",
            name="settle_kind",
            field=models.CharField(
                blank=True,
                default="custom",
                help_text="full=تسویه کامل، custom=مبلغ دلخواه",
                max_length=16,
            ),
        ),
    ]
