from django.contrib import admin

from .models import DigestLog, TelegramUpdate


@admin.register(TelegramUpdate)
class TelegramUpdateAdmin(admin.ModelAdmin):
    list_display = ["update_id", "chat_id", "status", "attempts", "received_at", "processed_at"]
    list_filter = ["status"]
    readonly_fields = ["payload", "error", "received_at", "processed_at"]


@admin.register(DigestLog)
class DigestLogAdmin(admin.ModelAdmin):
    list_display = ["key", "sent_at"]
    readonly_fields = ["key", "text", "sent_at"]
