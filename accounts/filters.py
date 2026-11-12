import django_filters

from core import widgets as w

from .models import BankAccount, PaymentMethod


class BankAccountFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr="icontains", widget=w.text("Buscar pelo nome", type="search"))
    type = django_filters.ChoiceFilter(choices=BankAccount.TypeChoices.choices, empty_label="Todos",
                                       widget=w.select())
    active = django_filters.ChoiceFilter(choices=[("1", "Ativas"), ("0", "Inativas")], empty_label="Todas",
                                         widget=w.select())

    class Meta:
        model = BankAccount
        fields = ["name", "type", "active"]


class PaymentMethodFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr="icontains", widget=w.text("Buscar pelo nome", type="search"))
    type = django_filters.ChoiceFilter(choices=PaymentMethod.TypeChoices.choices, empty_label="Todos",
                                       widget=w.select())
    active = django_filters.ChoiceFilter(choices=[("1", "Ativas"), ("0", "Inativas")], empty_label="Todas",
                                         widget=w.select())

    class Meta:
        model = PaymentMethod
        fields = ["name", "type", "active"]
