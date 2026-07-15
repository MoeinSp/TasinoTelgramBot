from django.contrib import admin
from .models import AdLoadout


@admin.register(AdLoadout)
class AdLoadoutAdmin(admin.ModelAdmin):
    list_display = ("name", "is_favorite", "updated_at")
    list_filter = ("is_favorite",)
    search_fields = ("name",)
