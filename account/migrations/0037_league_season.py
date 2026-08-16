from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0036_league"),
    ]

    operations = [
        migrations.AddField(
            model_name="leaguestanding",
            name="season_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="تاریخ شنبهٔ شروع هفته به صورت YYYY-MM-DD",
                max_length=16,
                verbose_name="شناسه هفته",
            ),
        ),
        migrations.AddIndex(
            model_name="leaguestanding",
            index=models.Index(
                fields=["telegram_chat_id", "season_id", "-wager_total"],
                name="account_lea_tg_season_idx",
            ),
        ),
    ]
