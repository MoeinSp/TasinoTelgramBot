from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bot_setting", "0009_forcedjoinconfig_active_from_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="botsiteconfig",
            name="admin_sensitive_hidden",
            field=models.BooleanField(
                default=False,
                help_text="اگر روشن باشد، ادمین‌ها در همه گروه‌ها حق واسطه، فعالیت‌ها، حساب ادمین و گزارش مالک را نمی‌بینند.",
                verbose_name="مخفی حساس از ادمین (سراسری)",
            ),
        ),
    ]
