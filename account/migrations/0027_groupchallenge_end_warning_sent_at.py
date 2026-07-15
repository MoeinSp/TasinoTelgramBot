from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0026_telegramgroup_quiet_extra"),
    ]

    operations = [
        migrations.AddField(
            model_name="groupchallenge",
            name="end_warning_sent_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
