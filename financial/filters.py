import django_filters
from django import forms
from .models import Recurrence, Transaction, Purchase


class RecurrenceFilter(django_filters.FilterSet):
    description = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Buscar por descrição...",
            }
        ),
    )
    type = django_filters.ChoiceFilter(
        choices=[("", "Todos")] + list(Recurrence.TypeChoices.choices),
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )
    frequency = django_filters.ChoiceFilter(
        choices=[("", "Todas")] + list(Recurrence.FrequencyChoices.choices),
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
        model = Recurrence
        fields = ["description", "type", "frequency", "active"]


class TransactionFilter(django_filters.FilterSet):
    description = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Buscar por descrição...",
            }
        ),
    )
    type = django_filters.ChoiceFilter(
        choices=[("", "Todos")] + list(Transaction.TypeChoices.choices),
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )
    category = django_filters.ModelChoiceFilter(
        queryset=None,  # Will be set in __init__
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )
    payment_method = django_filters.ModelChoiceFilter(
        queryset=None,  # Will be set in __init__
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )
    confirmed = django_filters.ChoiceFilter(
        choices=[
            ("", "Todos"),
            ("true", "Confirmadas"),
            ("false", "Pendentes"),
        ],
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )
    date_from = django_filters.DateFilter(
        field_name="date",
        lookup_expr="gte",
        widget=forms.DateInput(
            attrs={
                "class": "input input-bordered w-full",
                "type": "date",
            }
        ),
    )
    date_to = django_filters.DateFilter(
        field_name="date",
        lookup_expr="lte",
        widget=forms.DateInput(
            attrs={
                "class": "input input-bordered w-full",
                "type": "date",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import Category
        from accounts.models import PaymentMethod

        self.filters["category"].queryset = Category.objects.filter(active=True)
        self.filters["payment_method"].queryset = PaymentMethod.objects.filter(
            active=True
        )

    class Meta:
        model = Transaction
        fields = [
            "description",
            "type",
            "category",
            "payment_method",
            "confirmed",
            "date_from",
            "date_to",
        ]


class PurchaseFilter(django_filters.FilterSet):
    description = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Buscar por descrição...",
            }
        ),
    )
    category = django_filters.ModelChoiceFilter(
        queryset=None,  # Will be set in __init__
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )
    payment_method = django_filters.ModelChoiceFilter(
        queryset=None,  # Will be set in __init__
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
    )
    purchase_date_from = django_filters.DateFilter(
        field_name="purchase_date",
        lookup_expr="gte",
        widget=forms.DateInput(
            attrs={
                "class": "input input-bordered w-full",
                "type": "date",
            }
        ),
    )
    purchase_date_to = django_filters.DateFilter(
        field_name="purchase_date",
        lookup_expr="lte",
        widget=forms.DateInput(
            attrs={
                "class": "input input-bordered w-full",
                "type": "date",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import Category
        from accounts.models import PaymentMethod

        self.filters["category"].queryset = Category.objects.filter(active=True)
        self.filters["payment_method"].queryset = PaymentMethod.objects.filter(
            active=True
        )

    class Meta:
        model = Purchase
        fields = [
            "description",
            "category",
            "payment_method",
            "purchase_date_from",
            "purchase_date_to",
        ]
