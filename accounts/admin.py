from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import BankAccount, PaymentMethod


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "bank", "type", "color_preview", "active", "created_at"]
    list_filter = ["type", "active", "bank", "created_at"]
    search_fields = ["name", "bank"]
    readonly_fields = ["created_at", "updated_at"]
    list_editable = ["active"]
    list_per_page = 50

    fieldsets = (
        (_("Basic Information"), {"fields": ("name", "bank", "type", "active")}),
        (_("Visual"), {"fields": ("color",)}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def color_preview(self, obj):
        if obj.color:
            return f'<div style="width: 20px; height: 20px; background-color: {obj.color}; border: 1px solid #ccc; border-radius: 3px;"></div>'
        return "-"

    color_preview.short_description = _("Color")
    color_preview.allow_tags = True

    actions = ["activate_accounts", "deactivate_accounts"]

    @admin.action(description=_("Activate selected bank accounts"))
    def activate_accounts(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, _(f"{updated} bank accounts activated."))

    @admin.action(description=_("Deactivate selected bank accounts"))
    def deactivate_accounts(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, _(f"{updated} bank accounts deactivated."))


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "type",
        "bank_account",
        "credit_limit_display",
        "closing_day",
        "due_day",
        "active",
        "created_at",
    ]
    list_filter = ["type", "active", "created_at", "bank_account"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]
    list_editable = ["active"]
    list_per_page = 50

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("name", "type", "bank_account", "active")},
        ),
        (
            _("Credit Card Information"),
            {
                "fields": ("credit_limit", "closing_day", "due_day"),
                "description": _("Fill these fields only for credit cards"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def credit_limit_display(self, obj):
        if obj.type == "CREDIT" and obj.credit_limit:
            return f"R$ {obj.credit_limit:,.2f}"
        return "-"

    credit_limit_display.short_description = _("Credit Limit")

    def get_fieldsets(self, request, obj=None):
        """Show credit card fields only for credit card types"""
        fieldsets = super().get_fieldsets(request, obj)

        if obj and obj.type == "CREDIT":
            # Expand credit card section
            fieldsets = list(fieldsets)
            for i, fieldset in enumerate(fieldsets):
                if fieldset[0] == _("Credit Card Information"):
                    fieldsets[i] = (fieldset[0], {**fieldset[1], "classes": ()})

        return fieldsets

    actions = ["activate_payment_methods", "deactivate_payment_methods"]

    @admin.action(description=_("Activate selected payment methods"))
    def activate_payment_methods(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, _(f"{updated} payment methods activated."))

    @admin.action(description=_("Deactivate selected payment methods"))
    def deactivate_payment_methods(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, _(f"{updated} payment methods deactivated."))
