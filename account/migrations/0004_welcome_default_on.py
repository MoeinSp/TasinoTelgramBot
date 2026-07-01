from django.db import migrations, models


def enable_welcome_for_existing_groups(apps, schema_editor):
    TelegramGroup = apps.get_model("account", "TelegramGroup")
    TelegramGroup.objects.filter(welcome_enabled=False).update(welcome_enabled=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0003_welcome_antispam"),
    ]

    operations = [
        migrations.AlterField(
            model_name="telegramgroup",
            name="welcome_enabled",
            field=models.BooleanField(default=True, verbose_name="خوشامدگویی فعال"),
        ),
        migrations.RunPython(enable_welcome_for_existing_groups, noop),
    ]
