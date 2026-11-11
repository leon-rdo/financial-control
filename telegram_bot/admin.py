from django.contrib import admin

from .models import PendingTransaction


@admin.register(PendingTransaction)
class PendingTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "description",
        "amount",
        "transaction_type",
        "status",
        "category",
        "payment_method",
        "created_at",
    ]
    list_filter = ["status", "transaction_type"]
    readonly_fields = ["raw_ai_response", "created_at"]


from .models import TelegramUpdate  # noqa: E402


@admin.register(TelegramUpdate)
class TelegramUpdateAdmin(admin.ModelAdmin):
    list_display = ["update_id", "chat_id", "status", "attempts", "received_at", "processed_at"]
    list_filter = ["status"]
    readonly_fields = ["payload", "error", "received_at", "processed_at"]


from .models import DigestLog  # noqa: E402


@admin.register(DigestLog)
class DigestLogAdmin(admin.ModelAdmin):
    list_display = ["key", "sent_at"]
    readonly_fields = ["key", "text", "sent_at"]
