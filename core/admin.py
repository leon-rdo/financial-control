from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Category, Tag, Entity


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = [
        "icon_display",
        "name",
        "type_badge",
        "color_preview",
        "transactions_count",
        "active",
        "created_at",
    ]
    list_filter = ["type", "active", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at", "transactions_count", "recurrences_count", "purchases_count"]
    list_editable = ["active"]
    list_per_page = 50

    fieldsets = (
        (_("Basic Information"), {"fields": ("name", "type", "active")}),
        (_("Visual"), {"fields": ("color", "icon")}),
        (
            _("Usage Statistics"),
            {
                "fields": ("transactions_count", "recurrences_count", "purchases_count"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def icon_display(self, obj):
        return obj.icon or "-"

    icon_display.short_description = _("Icon")

    def type_badge(self, obj):
        colors = {
            "INCOME": "#16a34a",
            "EXPENSE": "#dc2626",
            "BOTH": "#6b7280",
        }
        color = colors.get(obj.type, "#6b7280")
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            obj.get_type_display(),
        )

    type_badge.short_description = _("Type")
    type_badge.admin_order_field = "type"

    def color_preview(self, obj):
        if obj.color:
            return format_html(
                '<div style="width: 20px; height: 20px; background-color: {}; '
                'border: 1px solid #ccc; border-radius: 3px; display: inline-block;"></div>',
                obj.color,
            )
        return "-"

    color_preview.short_description = _("Color")

    def transactions_count(self, obj):
        return obj.transactions.count()

    transactions_count.short_description = _("Transactions")

    def recurrences_count(self, obj):
        return obj.recurrences.count()

    recurrences_count.short_description = _("Recurrences")

    def purchases_count(self, obj):
        return obj.purchases.count()

    purchases_count.short_description = _("Purchases")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("transactions", "recurrences", "purchases")

    actions = ["activate_categories", "deactivate_categories"]

    @admin.action(description=_("Activate selected categories"))
    def activate_categories(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, _("{} categories activated.").format(updated))

    @admin.action(description=_("Deactivate selected categories"))
    def deactivate_categories(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, _("{} categories deactivated.").format(updated))


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "color_preview", "transactions_count", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at", "transactions_count"]
    list_per_page = 50

    fieldsets = (
        (_("Basic Information"), {"fields": ("name", "color")}),
        (
            _("Usage Statistics"),
            {"fields": ("transactions_count",), "classes": ("collapse",)},
        ),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def color_preview(self, obj):
        if obj.color:
            return format_html(
                '<span style="background-color: {}; color: #fff; padding: 2px 8px; '
                'border-radius: 3px; font-size: 11px;">{}</span>',
                obj.color,
                obj.color,
            )
        return "-"

    color_preview.short_description = _("Color")

    def transactions_count(self, obj):
        return obj.transactions.count()

    transactions_count.short_description = _("Transactions")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("transactions")


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "type",
        "document",
        "email",
        "phone",
        "transactions_count",
        "active",
        "created_at",
    ]
    list_filter = ["type", "active", "created_at"]
    search_fields = ["name", "document", "email"]
    readonly_fields = ["created_at", "updated_at", "transactions_count", "recurrences_count", "purchases_count"]
    list_editable = ["active"]
    list_per_page = 50

    fieldsets = (
        (_("Basic Information"), {"fields": ("name", "type", "active")}),
        (_("Contact Information"), {"fields": ("document", "email", "phone")}),
        (
            _("Usage Statistics"),
            {
                "fields": ("transactions_count", "recurrences_count", "purchases_count"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def transactions_count(self, obj):
        return obj.transactions.count()

    transactions_count.short_description = _("Transactions")

    def recurrences_count(self, obj):
        return obj.recurrences.count()

    recurrences_count.short_description = _("Recurrences")

    def purchases_count(self, obj):
        return obj.purchases.count()

    purchases_count.short_description = _("Purchases")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("transactions", "recurrences", "purchases")

    actions = ["activate_entities", "deactivate_entities"]

    @admin.action(description=_("Activate selected entities"))
    def activate_entities(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, _("{} entities activated.").format(updated))

    @admin.action(description=_("Deactivate selected entities"))
    def deactivate_entities(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, _("{} entities deactivated.").format(updated))
