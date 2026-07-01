from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0002_telegramgroup_fee_percent_dicerollstat"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="welcome_enabled",
            field=models.BooleanField(default=False, verbose_name="خوشامدگویی فعال"),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="welcome_text",
            field=models.TextField(blank=True, null=True, verbose_name="متن خوشامدگویی"),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="welcome_gif_file_id",
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name="گیف خوشامدگویی"),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="anti_flood_enabled",
            field=models.BooleanField(default=False, verbose_name="آنتی فلود فعال"),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="anti_flood_limit",
            field=models.IntegerField(default=5, verbose_name="حد فلود (تعداد پیام)"),
        ),
        migrations.AddField(
            model_name="telegramgroup",
            name="anti_flood_window",
            field=models.IntegerField(default=10, verbose_name="بازه فلود (ثانیه)"),
        ),
    ]
