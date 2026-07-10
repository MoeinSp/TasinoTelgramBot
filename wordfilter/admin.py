from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import WordFilter


@admin.register(WordFilter)
class WordFilterAdmin(ModelAdmin):
    list_display = ("word", "chat_id", "created_at")
    list_filter = ("chat_id",)
    search_fields = ("word",)
    ordering = ("chat_id", "word")
    readonly_fields = ("created_at",)
    list_per_page = 50
