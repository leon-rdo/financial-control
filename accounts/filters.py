import django_filters
from django import forms
from .models import BankAccount, PaymentMethod


class BankAccountFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Buscar por nome ou banco...",
            }
        ),
    )
    type = django_filters.ChoiceFilter(
        choices=[("", "Todos")] + list(BankAccount.TypeChoices.choices),
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )
    active = django_filters.ChoiceFilter(
        choices=[
            ("", "Todos"),
            ("true", "Ativas"),
            ("false", "Inativas"),
        ],
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )

    class Meta:
        model = BankAccount
        fields = ["name", "type", "active"]


class PaymentMethodFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Buscar por nome...",
            }
        ),
    )
    type = django_filters.ChoiceFilter(
        choices=[("", "Todos")] + list(PaymentMethod.TypeChoices.choices),
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )
    active = django_filters.ChoiceFilter(
        choices=[
            ("", "Todos"),
            ("true", "Ativos"),
            ("false", "Inativos"),
        ],
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )

    class Meta:
        model = PaymentMethod
        fields = ["name", "type", "active"]
