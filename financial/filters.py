from calendar import monthrange
from datetime import date

from accounts.models import Entity, PaymentMethod
from .models import Category, FinancialRecord, Installment
from utils.widgets import create_model_select2_filter, create_nested_select2_filter
import django_filters
from django import forms


class FinancialRecordFilter(django_filters.FilterSet):
    date__gte = django_filters.DateFilter(
        field_name="date",
        lookup_expr="gte",
        label="Data a partir de",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    date__lte = django_filters.DateFilter(
        field_name="date",
        lookup_expr="lte",
        label="Data até",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    entity = create_model_select2_filter(
        model=FinancialRecord._meta.get_field("entity").related_model,
        search_fields=["name__icontains", "document__icontains"],
    )

    payment_method = create_model_select2_filter(
        model=FinancialRecord._meta.get_field("payment_method").related_model,
        search_fields=[
            "fin_institution__icontains",
            "owner__name__icontains",
            "payment_type__icontains",
        ],
    )

    category = create_model_select2_filter(
        model=Category,
        search_fields=["name__icontains"],
    )

    description = django_filters.CharFilter(
        field_name="description",
        lookup_expr="icontains",
        label="Descrição contém",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    amount__gte = django_filters.NumberFilter(
        field_name="amount",
        lookup_expr="gte",
        label="Valor maior ou igual a",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    amount__lte = django_filters.NumberFilter(
        field_name="amount",
        lookup_expr="lte",
        label="Valor menor ou igual a",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = FinancialRecord
        fields = [
            "date__gte",
            "date__lte",
            "entity",
            "payment_method",
            "category",
            "description",
            "amount__gte",
            "amount__lte",
        ]


class InstallmentFilter(django_filters.FilterSet):
    due_month__gte = django_filters.CharFilter(
        label="Vencimento a partir de (mês/ano)",
        method="filter_due_date_gte",
        widget=forms.DateInput(attrs={"type": "month", "class": "form-control"}),
    )
    due_month__lte = django_filters.CharFilter(
        label="Vencimento até (mês/ano)",
        method="filter_due_date_lte",
        widget=forms.DateInput(attrs={"type": "month", "class": "form-control"}),
    )

    amount__gte = django_filters.NumberFilter(
        field_name="amount",
        lookup_expr="gte",
        label="Valor maior ou igual a",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    amount__lte = django_filters.NumberFilter(
        field_name="amount",
        lookup_expr="lte",
        label="Valor menor ou igual a",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    is_paid = django_filters.TypedChoiceFilter(
        field_name="is_paid",
        label="Status do pagamento",
        coerce=lambda x: x == "True",
        choices=(
            ("", "Todos"),
            ("True", "Pago"),
            ("False", "Pendente"),
        ),
        widget=forms.RadioSelect(
            attrs={"class": "form-check d-flex justify-content-between w-100"}
        ),
    )

    entity = create_nested_select2_filter("fin_record__entity", Entity, ["name__icontains", "document__icontains"])
    payment_method = create_nested_select2_filter("fin_record__payment_method", PaymentMethod, ["fin_institution__icontains", "owner__name__icontains"])
    category = create_nested_select2_filter("fin_record__category", Category, ["name__icontains"])


    class Meta:
        model = Installment
        fields = [
            "due_month__gte",
            "due_month__lte",
            "amount__gte",
            "amount__lte",
            "is_paid",
            "entity",
            "payment_method",
            "category",
        ]

    def filter_due_date_gte(self, queryset, name, value):
        try:
            year, month = map(int, value.split("-"))
            first_day = date(year, month, 1)
            return queryset.filter(due_date__gte=first_day)
        except (ValueError, AttributeError):
            return queryset.none()

    def filter_due_date_lte(self, queryset, name, value):
        try:
            year, month = map(int, value.split("-"))
            last_day = date(year, month, monthrange(year, month)[1])
            return queryset.filter(due_date__lte=last_day)
        except (ValueError, AttributeError):
            return queryset.none()


class CategoryFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        field_name="name",
        lookup_expr="icontains",
        label="Nome contém",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    description = django_filters.CharFilter(
        field_name="description",
        lookup_expr="icontains",
        label="Descrição contém",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    is_income = django_filters.ChoiceFilter(
        field_name="is_income",
        label="É receita?",
        choices=(
            ("True", "Receita"),
            ("False", "Despesa"),
        ),
        widget=forms.RadioSelect(
            attrs={"class": "form-check d-flex justify-content-between w-100"}
        ),
        method="filter_is_income",
    )

    def filter_is_income(self, queryset, name, value):
        if value == "":
            return queryset
        elif value == "True":
            return queryset.filter(is_income=True)
        elif value == "False":
            return queryset.filter(is_income=False)
        return queryset

    class Meta:
        model = Category
        fields = ["name", "description", "is_income"]
