from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0021_admin_activity_session"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegramgroup",
            name="pv_admin_finance_enabled",
            field=models.BooleanField(
                default=False,
                help_text="اگر روشن باشد، ادمین‌ها در پیوی همان گزارش‌های مالی مالک را می‌بینند.",
                verbose_name="دسترسی ادمین به پنل مالی پیوی",
            ),
        ),
    ]
