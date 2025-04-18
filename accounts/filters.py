import requests
from .models import Entity, PaymentMethod
from utils.widgets import create_model_select2_filter, create_select2_multiple_filter
import django_filters
from django import forms
from django_select2.forms import Select2Widget


class EntityFilter(django_filters.FilterSet):
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
    person_type = django_filters.MultipleChoiceFilter(
        field_name="person_type",
        label="Tipo de Pessoa",
        choices=[("F", "Pessoa Física"), ("J", "Pessoa Jurídica")],
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check d-flex justify-content-between align-items-center"}),
    )
    document = django_filters.CharFilter(
        field_name="document",
        lookup_expr="icontains",
        label="CPF/CNPJ contém",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Entity
        fields = ["name", "description", "person_type", "document"]


class PaymentMethodFilter(django_filters.FilterSet):
    fin_institution = django_filters.ChoiceFilter(
        widget=Select2Widget(
            attrs={
                "class": "form-select",
                "data-dropdown-parent": "#filtersOffcanvas",
            }
        ),
        choices=[],
        label="Instituição Financeira",
    )

    owner = create_model_select2_filter(
        model=Entity,
        search_fields=["name__icontains", "document__icontains"],
    )

    payment_type = create_select2_multiple_filter(
        PaymentMethod._meta.get_field("payment_type").choices
    )

    description = django_filters.CharFilter(
        field_name="description",
        lookup_expr="icontains",
        label="Descrição contém",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            response = requests.get("https://brasilapi.com.br/api/banks/v1")
            response.raise_for_status()
            banks = response.json()
        except Exception:
            banks = []

        choices = [("", "Selecione uma Instituição")]
        for bank in banks:
            if bank["code"]:
                option = f"{bank['code']} - {bank['name']}"
                choices.append((option, option))
        self.form.fields["fin_institution"].choices = choices

    class Meta:
        model = PaymentMethod
        fields = ["fin_institution", "owner", "payment_type", "description"]
