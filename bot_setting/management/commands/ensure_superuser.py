import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "ساخت سوپریوزر از env (بدون prompt)"

    def handle(self, *args, **options):
        User = get_user_model()
        username = (os.getenv("DJANGO_SUPERUSER_USERNAME") or "admin").strip()
        email = (os.getenv("DJANGO_SUPERUSER_EMAIL") or "admin@tasino.local").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD") or ""

        if not password:
            self.stderr.write(
                "❌ DJANGO_SUPERUSER_PASSWORD تنظیم نشده.\n"
                "مثال:\n"
                "  DJANGO_SUPERUSER_PASSWORD=secret python manage.py ensure_superuser"
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"کاربر '{username}' از قبل وجود دارد."))
            return

        User.objects.create_superuser(username, email, password)
        self.stdout.write(self.style.SUCCESS(f"✅ سوپریوزر '{username}' ساخته شد."))
