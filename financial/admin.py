from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Count, Q
from .models import Purchase, Installment


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0
    readonly_fields = [
        "installment_number",
        "amount",
        "due_date",
        "reference_month",
        "reference_year",
    ]
    can_delete = False

    fields = [
        "installment_number",
        "amount",
        "due_date",
        "reference_month",
        "reference_year",
        "paid",
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        "description",
        "total_amount_display",
        "number_of_installments",
        "installment_amount_display",
        "purchase_date",
        "payment_method",
        "installments_paid_count",
        "created_at",
    ]
    list_filter = ["purchase_date", "payment_method", "category", "created_at"]
    search_fields = ["description", "notes"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "installments_paid_count",
        "total_paid_amount",
        "remaining_amount",
    ]
    date_hierarchy = "purchase_date"
    list_per_page = 50
    inlines = [InstallmentInline]
    autocomplete_fields = ["category", "entity", "payment_method"]

    fieldsets = (
        (
            _("Basic Information"),
            {
                "fields": (
                    "description",
                    "total_amount",
                    "purchase_date",
                    "number_of_installments",
                )
            },
        ),
        (_("Categorization"), {"fields": ("category", "entity", "payment_method")}),
        (
            _("Payment Status"),
            {
                "fields": (
                    "installments_paid_count",
                    "total_paid_amount",
                    "remaining_amount",
                ),
                "classes": ("collapse",),
            },
        ),
        (_("Additional Information"), {"fields": ("notes",), "classes": ("collapse",)}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def total_amount_display(self, obj):
        return f"R$ {obj.total_amount:,.2f}"

    total_amount_display.short_description = _("Total Amount")
    total_amount_display.admin_order_field = "total_amount"

    def installment_amount_display(self, obj):
        installment_amount = obj.total_amount / obj.number_of_installments
        return f"R$ {installment_amount:,.2f}"

    installment_amount_display.short_description = _("Installment Amount")

    def installments_paid_count(self, obj):
        paid = obj.installments.filter(paid=True).count()
        total = obj.number_of_installments
        return f"{paid}/{total}"

    installments_paid_count.short_description = _("Paid Installments")

    def total_paid_amount(self, obj):
        total = (
            obj.installments.filter(paid=True).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        return f"R$ {total:,.2f}"

    total_paid_amount.short_description = _("Total Paid")

    def remaining_amount(self, obj):
        paid = (
            obj.installments.filter(paid=True).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        remaining = obj.total_amount - paid
        return f"R$ {remaining:,.2f}"

    remaining_amount.short_description = _("Remaining Amount")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "category", "entity", "payment_method"
        ).prefetch_related("installments")

    actions = ["regenerate_installments"]

    @admin.action(description=_("Regenerate installments"))
    def regenerate_installments(self, request, queryset):
        count = 0
        for purchase in queryset:
            purchase.generate_installments()
            count += 1
        self.message_user(
            request, _(f"Installments regenerated for {count} purchases.")
        )


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = [
        "purchase_description",
        "installment_info",
        "amount_display",
        "due_date",
        "reference_period",
        "paid",
        "created_at",
    ]
    list_filter = [
        "paid",
        "reference_year",
        "reference_month",
        "due_date",
        "purchase__payment_method",
    ]
    search_fields = ["purchase__description"]
    readonly_fields = ["created_at", "updated_at"]
    list_editable = ["paid"]
    date_hierarchy = "due_date"
    list_per_page = 50
    autocomplete_fields = ["purchase"]

    fieldsets = (
        (_("Purchase Information"), {"fields": ("purchase",)}),
        (
            _("Installment Details"),
            {
                "fields": (
                    "installment_number",
                    "amount",
                    "due_date",
                    "reference_month",
                    "reference_year",
                    "paid",
                )
            },
        ),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def purchase_description(self, obj):
        return obj.purchase.description

    purchase_description.short_description = _("Purchase")
    purchase_description.admin_order_field = "purchase__description"

    def installment_info(self, obj):
        return f"{obj.installment_number}/{obj.purchase.number_of_installments}"

    installment_info.short_description = _("Installment")

    def amount_display(self, obj):
        return f"R$ {obj.amount:,.2f}"

    amount_display.short_description = _("Amount")
    amount_display.admin_order_field = "amount"

    def reference_period(self, obj):
        return f"{obj.reference_month:02d}/{obj.reference_year}"

    reference_period.short_description = _("Period")
    reference_period.admin_order_field = "reference_year"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("purchase", "purchase__payment_method")

    actions = ["mark_as_paid", "mark_as_unpaid"]

    @admin.action(description=_("Mark as paid"))
    def mark_as_paid(self, request, queryset):
        updated = queryset.update(paid=True)
        self.message_user(request, _(f"{updated} installments marked as paid."))

    @admin.action(description=_("Mark as unpaid"))
    def mark_as_unpaid(self, request, queryset):
        updated = queryset.update(paid=False)
        self.message_user(request, _(f"{updated} installments marked as unpaid."))
