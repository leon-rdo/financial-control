from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Count, Q

from .models import Transaction, TransactionTag, Purchase, Installment, Recurrence


# ── Inlines ──────────────────────────────────────────────────────────────────


class TransactionTagInline(admin.TabularInline):
    model = TransactionTag
    extra = 1
    autocomplete_fields = ["tag"]


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


# ── Transaction ──────────────────────────────────────────────────────────────


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        "description",
        "type_badge",
        "amount_display",
        "date",
        "category",
        "payment_method",
        "entity",
        "confirmed",
        "tags_list",
        "created_at",
    ]
    list_filter = [
        "type",
        "confirmed",
        "date",
        "category",
        "payment_method",
        "entity",
        "tags",
        "created_at",
    ]
    search_fields = ["description", "notes", "entity__name", "category__name"]
    readonly_fields = ["created_at", "updated_at"]
    list_editable = ["confirmed"]
    date_hierarchy = "date"
    list_per_page = 50
    list_select_related = ["category", "entity", "payment_method", "recurrence", "purchase"]
    inlines = [TransactionTagInline]
    autocomplete_fields = ["category", "entity", "payment_method", "recurrence", "purchase"]

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("type", "description", "amount", "date", "confirmed")},
        ),
        (
            _("Categorization"),
            {"fields": ("category", "entity", "payment_method")},
        ),
        (
            _("Links"),
            {
                "fields": ("recurrence", "purchase"),
                "classes": ("collapse",),
                "description": _("Links to recurrence or purchase that generated this transaction."),
            },
        ),
        (
            _("Additional Information"),
            {"fields": ("notes",), "classes": ("collapse",)},
        ),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def type_badge(self, obj):
        color = "#16a34a" if obj.type == "INCOME" else "#dc2626"
        label = obj.get_type_display()
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            label,
        )

    type_badge.short_description = _("Type")
    type_badge.admin_order_field = "type"

    def amount_display(self, obj):
        color = "#16a34a" if obj.type == "INCOME" else "#dc2626"
        sign = "+" if obj.type == "INCOME" else "-"
        formatted = f"{sign} R$ {obj.amount:,.2f}"
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            formatted,
        )

    amount_display.short_description = _("Amount")
    amount_display.admin_order_field = "amount"

    def confirmed_icon(self, obj):
        if obj.confirmed:
            return mark_safe('<span style="color: #16a34a;" title="Confirmada">&#10003;</span>')
        return mark_safe('<span style="color: #d97706;" title="Pendente">&#9679;</span>')

    confirmed_icon.short_description = _("Confirmed")
    confirmed_icon.admin_order_field = "confirmed"

    def tags_list(self, obj):
        tags = list(obj.tags.all()[:6])
        if not tags:
            return "-"
        parts = [
            format_html(
                '<span style="background-color: {}; color: #fff; padding: 1px 6px; '
                'border-radius: 3px; font-size: 11px; margin-right: 2px;">{}</span>',
                tag.color or "#6b7280",
                tag.name,
            )
            for tag in tags[:5]
        ]
        result = mark_safe("".join(parts))
        if len(tags) > 5:
            result = mark_safe(f"{result} +...")
        return result

    tags_list.short_description = _("Tags")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "category", "entity", "payment_method", "recurrence", "purchase"
        ).prefetch_related("tags")

    actions = ["mark_confirmed", "mark_unconfirmed"]

    @admin.action(description=_("Mark as confirmed"))
    def mark_confirmed(self, request, queryset):
        updated = queryset.update(confirmed=True)
        self.message_user(request, _("{} transactions marked as confirmed.").format(updated))

    @admin.action(description=_("Mark as unconfirmed"))
    def mark_unconfirmed(self, request, queryset):
        updated = queryset.update(confirmed=False)
        self.message_user(request, _("{} transactions marked as unconfirmed.").format(updated))


# ── Recurrence ───────────────────────────────────────────────────────────────


@admin.register(Recurrence)
class RecurrenceAdmin(admin.ModelAdmin):
    list_display = [
        "description",
        "type_badge",
        "amount_display",
        "frequency",
        "reference_day",
        "start_date",
        "end_date",
        "active",
        "transaction_count",
        "created_at",
    ]
    list_filter = [
        "type",
        "frequency",
        "active",
        "category",
        "payment_method",
        "start_date",
        "created_at",
    ]
    search_fields = ["description", "notes", "entity__name", "category__name"]
    readonly_fields = ["created_at", "updated_at", "transaction_count"]
    list_editable = ["active"]
    date_hierarchy = "start_date"
    list_per_page = 50
    list_select_related = ["category", "entity", "payment_method"]
    autocomplete_fields = ["category", "entity", "payment_method"]

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("description", "type", "amount", "active")},
        ),
        (
            _("Categorization"),
            {"fields": ("category", "entity", "payment_method")},
        ),
        (
            _("Schedule"),
            {"fields": ("frequency", "reference_day", "start_date", "end_date")},
        ),
        (
            _("Statistics"),
            {
                "fields": ("transaction_count",),
                "classes": ("collapse",),
            },
        ),
        (
            _("Additional Information"),
            {"fields": ("notes",), "classes": ("collapse",)},
        ),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def type_badge(self, obj):
        color = "#16a34a" if obj.type == "INCOME" else "#dc2626"
        label = obj.get_type_display()
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            label,
        )

    type_badge.short_description = _("Type")
    type_badge.admin_order_field = "type"

    def amount_display(self, obj):
        return f"R$ {obj.amount:,.2f}"

    amount_display.short_description = _("Amount")
    amount_display.admin_order_field = "amount"

    def transaction_count(self, obj):
        return obj.transactions.count()

    transaction_count.short_description = _("Transactions Generated")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "category", "entity", "payment_method"
        ).prefetch_related("transactions")

    actions = ["activate_recurrences", "deactivate_recurrences"]

    @admin.action(description=_("Activate selected recurrences"))
    def activate_recurrences(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, _("{} recurrences activated.").format(updated))

    @admin.action(description=_("Deactivate selected recurrences"))
    def deactivate_recurrences(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, _("{} recurrences deactivated.").format(updated))


# ── Purchase ─────────────────────────────────────────────────────────────────


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        "description",
        "total_amount_display",
        "number_of_installments",
        "installment_amount_display",
        "purchase_date",
        "category",
        "payment_method",
        "entity",
        "installments_paid_count",
        "created_at",
    ]
    list_filter = ["purchase_date", "payment_method", "category", "entity", "created_at"]
    search_fields = ["description", "notes", "entity__name", "category__name"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "installments_paid_count",
        "total_paid_amount",
        "remaining_amount",
    ]
    date_hierarchy = "purchase_date"
    list_per_page = 50
    list_select_related = ["category", "entity", "payment_method"]
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
            request, _("Installments regenerated for {} purchases.").format(count)
        )


# ── Installment ──────────────────────────────────────────────────────────────


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = [
        "purchase_description",
        "installment_info",
        "amount_display",
        "due_date",
        "reference_period",
        "paid_icon",
        "paid",
        "created_at",
    ]
    list_filter = [
        "paid",
        "reference_year",
        "reference_month",
        "due_date",
        "purchase__payment_method",
        "purchase__category",
    ]
    search_fields = ["purchase__description"]
    readonly_fields = ["created_at", "updated_at"]
    list_editable = ["paid"]
    date_hierarchy = "due_date"
    list_per_page = 50
    list_select_related = ["purchase", "purchase__payment_method", "purchase__category"]
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

    def paid_icon(self, obj):
        if obj.paid:
            return mark_safe('<span style="color: #16a34a;" title="Paga">&#10003;</span>')
        return mark_safe('<span style="color: #d97706;" title="Pendente">&#9679;</span>')

    paid_icon.short_description = _("Status")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("purchase", "purchase__payment_method", "purchase__category")

    actions = ["mark_as_paid", "mark_as_unpaid"]

    @admin.action(description=_("Mark as paid"))
    def mark_as_paid(self, request, queryset):
        updated = queryset.update(paid=True)
        self.message_user(request, _("{} installments marked as paid.").format(updated))

    @admin.action(description=_("Mark as unpaid"))
    def mark_as_unpaid(self, request, queryset):
        updated = queryset.update(paid=False)
        self.message_user(request, _("{} installments marked as unpaid.").format(updated))
