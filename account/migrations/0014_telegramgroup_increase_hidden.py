from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0013_telegramgroup_bet_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="increase_hidden",
            field=models.BooleanField(
                default=False,
                help_text="اگر روشن باشد، ادمین فقط «افزایش موجودی» می‌زند و مبلغ را در پیوی وارد می‌کند.",
                verbose_name="افزایش موجودی مخفی",
            ),
        ),
    ]
