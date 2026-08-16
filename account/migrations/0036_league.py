from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0035_telegramgroup_transfer_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="league_enabled",
            field=models.BooleanField(
                default=False,
                help_text="اگر روشن باشد، حجم شرط کاربران در لیگ ثبت و جوایز پله‌ای پرداخت می‌شود.",
                verbose_name="لیگ شرط",
            ),
        ),
        migrations.CreateModel(
            name="LeagueStanding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_chat_id", models.BigIntegerField(db_index=True)),
                ("telegram_user_id", models.BigIntegerField(db_index=True)),
                ("wager_total", models.BigIntegerField(default=0, verbose_name="مجموع شرط")),
                (
                    "claimed_level",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text="۰ = هنوز جایزه‌ای نگرفته؛ ۱..۵ = آخرین پله پرداخت‌شده",
                        verbose_name="آخرین پلهٔ جایزه‌گرفته",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "رتبه لیگ",
                "verbose_name_plural": "رتبه‌های لیگ",
            },
        ),
        migrations.AddIndex(
            model_name="leaguestanding",
            index=models.Index(
                fields=["telegram_chat_id", "-wager_total"],
                name="account_lea_telegra_wager_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="leaguestanding",
            constraint=models.UniqueConstraint(
                fields=("telegram_chat_id", "telegram_user_id"),
                name="uniq_tg_league_standing",
            ),
        ),
    ]
