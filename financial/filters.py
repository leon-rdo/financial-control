import django_filters
from django.db.models import Q

from accounts.models import BankAccount, PaymentMethod
from core import widgets as w
from core.models import Category

from .models import Purchase, Recurrence, Transaction, Transfer


def search(placeholder="Buscar pela descrição"):
    return django_filters.CharFilter(field_name="description", lookup_expr="icontains",
                                     widget=w.text(placeholder, type="search"))


def date_filter(field, lookup):
    return django_filters.DateFilter(field_name=field, lookup_expr=lookup, widget=w.date())


def choice(choices, all_label="Todos"):
    return django_filters.ChoiceFilter(choices=choices, empty_label=all_label, widget=w.select())


class RecurrenceFilter(django_filters.FilterSet):
    description = search()
    type = choice(Recurrence.TypeChoices.choices)
    frequency = choice(Recurrence.FrequencyChoices.choices, "Todas")
    active = choice([("1", "Ativas"), ("0", "Inativas")], "Todas")

    class Meta:
        model = Recurrence
        fields = ["description", "type", "frequency", "active"]


class TransactionFilter(django_filters.FilterSet):
    description = search()
    type = choice(Transaction.TypeChoices.choices)
    category = django_filters.ModelChoiceFilter(queryset=Category.objects.none(), empty_label="Todas",
                                                widget=w.select())
    payment_method = django_filters.ModelChoiceFilter(queryset=PaymentMethod.objects.none(), empty_label="Todos",
                                                      widget=w.select())
    confirmed = choice([("1", "Confirmadas"), ("0", "Pendentes")])
    third_party = django_filters.ChoiceFilter(
        choices=[("exclude", "Só da família"), ("only", "Só de terceiros")], empty_label="Todos",
        method="filter_third_party", widget=w.select())
    date_from = date_filter("date", "gte")
    date_to = date_filter("date", "lte")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["category"].queryset = Category.objects.filter(active=True)
        self.filters["payment_method"].queryset = PaymentMethod.objects.filter(active=True)

    def filter_third_party(self, queryset, name, value):
        if value == "only":
            return queryset.filter(on_behalf_of__isnull=False)
        if value == "exclude":
            return queryset.filter(on_behalf_of__isnull=True)
        return queryset

    class Meta:
        model = Transaction
        fields = ["description", "type", "category", "payment_method", "confirmed", "third_party",
                  "date_from", "date_to"]


class PurchaseFilter(django_filters.FilterSet):
    description = search()
    category = django_filters.ModelMultipleChoiceFilter(queryset=Category.objects.none(),
                                                        widget=w.multi(id="filter-category"))
    payment_method = django_filters.ModelMultipleChoiceFilter(queryset=PaymentMethod.objects.none(),
                                                              widget=w.multi(id="filter-payment-method"))
    status = django_filters.ChoiceFilter(
        choices=[("open", "Com parcelas a pagar"), ("done", "Quitados")], empty_label="Todos",
        method="filter_status", widget=w.select())
    purchase_date_from = date_filter("purchase_date", "gte")
    purchase_date_to = date_filter("purchase_date", "lte")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["category"].queryset = Category.objects.filter(active=True)
        self.filters["payment_method"].queryset = PaymentMethod.objects.filter(active=True)

    def filter_status(self, queryset, name, value):
        if value == "open":
            return queryset.filter(installments__paid=False).distinct()
        if value == "done":
            return queryset.exclude(installments__paid=False)
        return queryset

    class Meta:
        model = Purchase
        fields = ["description", "category", "payment_method", "status", "purchase_date_from",
                  "purchase_date_to"]


class TransferFilter(django_filters.FilterSet):
    description = search()
    account = django_filters.ModelChoiceFilter(queryset=BankAccount.objects.none(), empty_label="Todas",
                                               method="filter_account", widget=w.select())
    to_card = django_filters.ModelChoiceFilter(queryset=PaymentMethod.objects.none(), empty_label="Todos",
                                               widget=w.select())
    kind = django_filters.ChoiceFilter(
        choices=[("invoice", "Pagamentos de fatura"), ("between", "Entre contas e caixinhas"),
                 ("open", "Com ponta aberta")],
        empty_label="Todas", method="filter_kind", widget=w.select())
    date_from = date_filter("date", "gte")
    date_to = date_filter("date", "lte")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["account"].queryset = BankAccount.objects.filter(active=True).select_related("parent")
        self.filters["to_card"].queryset = PaymentMethod.objects.filter(
            type=PaymentMethod.TypeChoices.CREDIT, billing_card__isnull=True)

    def filter_account(self, queryset, name, value):
        return queryset.filter(Q(from_account=value) | Q(to_account=value)) if value else queryset

    def filter_kind(self, queryset, name, value):
        if value == "invoice":
            return queryset.filter(to_card__isnull=False)
        if value == "between":
            return queryset.filter(to_card__isnull=True, from_account__isnull=False, to_account__isnull=False)
        if value == "open":
            return queryset.filter(open_q())
        return queryset

    class Meta:
        model = Transfer
        fields = ["description", "account", "to_card", "kind", "date_from", "date_to"]


def open_q():
    """Transferência com ponta aberta: sem origem, ou sem destino (nem conta nem cartão)."""
    return Q(from_account__isnull=True) | Q(to_account__isnull=True, to_card__isnull=True)

