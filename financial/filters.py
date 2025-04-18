from .models import Category, FinancialRecord
from utils.widgets import create_model_select2_filter
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
