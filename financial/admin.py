from django.contrib import admin
from .models import Category, FinancialRecord, Installment


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_income")
    search_fields = ("name",)
    list_filter = ("is_income",)


@admin.register(FinancialRecord)
class FinancialRecordAdmin(admin.ModelAdmin):
    list_display = ("entity", "amount", "date", "category", "payment_method")
    search_fields = ("entity__name", "description")
    list_filter = ("date", "category", "payment_method")
    ordering = ("-date",)


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = (
        "fin_record",
        "installment_number",
        "due_date",
        "amount",
        "is_paid",
    )
    list_filter = ("due_date", "is_paid")
    ordering = ("due_date",)
