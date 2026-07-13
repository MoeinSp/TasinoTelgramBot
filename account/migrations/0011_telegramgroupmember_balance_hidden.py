from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0010_telegramgroup_dice_turn_limit"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroupmember",
            name="balance_hidden",
            field=models.BooleanField(default=False, verbose_name="موجودی مخفی"),
        ),
    ]
