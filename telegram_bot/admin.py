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
