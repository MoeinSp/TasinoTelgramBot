from django.contrib import admin
from .models import WordFilter


@admin.register(WordFilter)
class WordFilterAdmin(admin.ModelAdmin):
    list_display = ("word", "chat_id", "created_at")
    list_filter = ("chat_id",)
    search_fields = ("word", "chat_id")
    ordering = ("chat_id", "word")
    readonly_fields = ("created_at",)
