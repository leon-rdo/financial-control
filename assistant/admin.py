from django.contrib import admin

from .models import Attachment, ChatMessage, Conversation, ImportBatch, StagedEntry


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    fields = ["role", "text_preview", "model", "stop_reason", "usage", "created_at"]
    readonly_fields = fields
    can_delete = False
    show_change_link = True


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "chat_id", "provider", "model", "last_activity_at", "closed_at"]
    list_filter = ["provider", "model"]
    readonly_fields = ["prompt_hash", "created_at"]
    inlines = [ChatMessageInline]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "role", "text_preview", "model", "created_at"]
    list_filter = ["role"]
    readonly_fields = ["native_content", "usage", "created_at"]


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["id", "filename", "kind", "size", "provider", "created_at"]
    list_filter = ["kind"]
    readonly_fields = ["sha256", "storage_path", "provider_file_id", "created_at"]


class StagedEntryInline(admin.TabularInline):
    model = StagedEntry
    extra = 0
    fields = ["position", "kind", "description", "amount", "date", "category", "category_name",
              "payment_method", "installment_number", "installments_total", "match_status", "include",
              "committed_transaction", "committed_purchase"]
    readonly_fields = ["committed_transaction", "committed_purchase", "match_status"]
    raw_id_fields = ["category", "payment_method"]


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ["id", "kind", "status", "title", "payment_method", "invoice_year", "invoice_month",
                    "invoice_total", "created_at", "committed_at"]
    list_filter = ["kind", "status"]
    readonly_fields = ["version", "warnings", "created_at", "updated_at", "committed_at"]
    inlines = [StagedEntryInline]


from .models import ExtractionJob  # noqa: E402


@admin.register(ExtractionJob)
class ExtractionJobAdmin(admin.ModelAdmin):
    list_display = ["id", "attachment", "mode", "model", "status", "import_batch", "created_at", "finished_at"]
    list_filter = ["mode", "status", "model"]
    readonly_fields = ["usage", "error", "provider_batch_id", "created_at", "finished_at"]
