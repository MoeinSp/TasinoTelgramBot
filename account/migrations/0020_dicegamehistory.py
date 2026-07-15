from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0019_balance_increase_request"),
    ]

    operations = [
        migrations.CreateModel(
            name="DiceGameHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_chat_id", models.BigIntegerField(db_index=True)),
                ("telegram_user_id", models.BigIntegerField()),
                ("total", models.IntegerField()),
                ("average", models.FloatField()),
                ("count", models.IntegerField()),
                ("winner", models.BooleanField(default=False)),
                ("amount_won", models.IntegerField(default=0)),
                ("bet_amount", models.IntegerField(default=0)),
                ("game_session", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["telegram_chat_id", "created_at"], name="account_dice_chat_created_idx"),
                    models.Index(fields=["telegram_chat_id", "game_session"], name="account_dice_chat_session_idx"),
                ],
            },
        ),
    ]
