from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0024_adminactivitysession_balance_snapshots"),
    ]

    operations = [
        migrations.CreateModel(
            name="GroupChallenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_chat_id", models.BigIntegerField(db_index=True)),
                ("created_by", models.BigIntegerField(db_index=True)),
                ("challenge_type", models.CharField(db_index=True, max_length=32)),
                ("prize_amount", models.BigIntegerField(default=0)),
                ("min_games_today", models.PositiveIntegerField(default=0)),
                ("min_wallet", models.BigIntegerField(default=0)),
                ("start_at", models.DateTimeField(db_index=True)),
                ("end_at", models.DateTimeField(db_index=True)),
                ("status", models.CharField(db_index=True, default="active", max_length=16)),
                ("winner_id", models.BigIntegerField(blank=True, null=True)),
                ("winner_score", models.BigIntegerField(default=0)),
                ("settled", models.BooleanField(default=False)),
                ("announce_message_id", models.BigIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GamePlayLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_chat_id", models.BigIntegerField(db_index=True)),
                ("telegram_user_id", models.BigIntegerField(db_index=True)),
                ("game_type", models.CharField(db_index=True, max_length=32)),
                ("score", models.BigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name="ChallengeEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_user_id", models.BigIntegerField(db_index=True)),
                ("best_score", models.BigIntegerField(default=0)),
                ("total_score", models.BigIntegerField(default=0)),
                ("plays", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("challenge", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="account.groupchallenge")),
            ],
        ),
        migrations.AddIndex(
            model_name="groupchallenge",
            index=models.Index(fields=["telegram_chat_id", "status", "end_at"], name="account_gro_telegra_ch1_idx"),
        ),
        migrations.AddIndex(
            model_name="groupchallenge",
            index=models.Index(fields=["telegram_chat_id", "challenge_type", "status"], name="account_gro_telegra_ch2_idx"),
        ),
        migrations.AddIndex(
            model_name="gameplaylog",
            index=models.Index(fields=["telegram_chat_id", "telegram_user_id", "game_type", "created_at"], name="account_gam_telegra_pl1_idx"),
        ),
        migrations.AddIndex(
            model_name="challengeentry",
            index=models.Index(fields=["challenge", "-total_score"], name="account_cha_challen_e1_idx"),
        ),
        migrations.AddIndex(
            model_name="challengeentry",
            index=models.Index(fields=["challenge", "-best_score"], name="account_cha_challen_e2_idx"),
        ),
        migrations.AddConstraint(
            model_name="challengeentry",
            constraint=models.UniqueConstraint(fields=("challenge", "telegram_user_id"), name="uniq_tg_challenge_entry_user"),
        ),
    ]
