from django import forms

from core import widgets as w

from .models import BalanceSnapshot, BankAccount, PaymentMethod


class BankAccountForm(w.FriendlyEmptyLabels, forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ["name", "bank", "type", "holder", "parent", "color", "opening_balance", "opening_balance_date",
                  "active"]
        widgets = {
            "name": w.text("Ex.: Nubank"),
            "bank": w.text("Preenchido ao escolher o banco"),
            "type": w.select(),
            "holder": w.select(),
            "parent": w.select(),
            "color": w.text("#1B3F8F", maxlength="7"),
            "opening_balance": w.money(),
            "opening_balance_date": w.date(),
            "active": w.check(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parents = BankAccount.objects.filter(parent__isnull=True, active=True)
        if self.instance.pk:
            parents = parents.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = parents
        self.fields["parent"].empty_label = "Não, é uma conta"
        self.fields["holder"].empty_label = "Sem titular"


class PaymentMethodForm(w.FriendlyEmptyLabels, forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ["name", "type", "bank_account", "holder", "billing_card", "lent_to", "credit_limit", "closing_day",
                  "due_day", "active"]
        widgets = {
            "name": w.text("Ex.: Nubank crédito"),
            "type": w.select(),
            "bank_account": w.select(),
            "holder": w.select(),
            "billing_card": w.select(),
            "lent_to": w.select(),
            "credit_limit": w.money(),
            "closing_day": w.day("Ex.: 3"),
            "due_day": w.day("Ex.: 10"),
            "active": w.check(),
        }

    def __init__(self, *args, **kwargs):
        from core.models import Entity

        super().__init__(*args, **kwargs)
        mains = PaymentMethod.objects.filter(type=PaymentMethod.TypeChoices.CREDIT, billing_card__isnull=True)
        if self.instance.pk:
            mains = mains.exclude(pk=self.instance.pk)
        self.fields["billing_card"].queryset = mains
        self.fields["billing_card"].empty_label = "Na própria fatura (é o cartão principal)"
        self.fields["lent_to"].queryset = Entity.objects.filter(type=Entity.TypeChoices.PERSON)
        self.fields["lent_to"].empty_label = "Fica com a família"
        self.fields["bank_account"].empty_label = "Nenhuma"
        self.fields["holder"].empty_label = "Herdar da conta"


class SimplePaymentMethodForm(w.FriendlyEmptyLabels, forms.ModelForm):
    """Criação rápida de forma de pagamento (dentro do formulário de transação)."""

    class Meta:
        model = PaymentMethod
        fields = ["name", "type"]


class BalanceSnapshotForm(w.FriendlyEmptyLabels, forms.ModelForm):
    """Saldo conhecido de uma conta ou caixinha no fim de um dia."""

    class Meta:
        model = BalanceSnapshot
        fields = ["account", "date", "balance", "notes"]
        widgets = {
            "account": w.select(),
            "date": w.date(),
            "balance": forms.NumberInput(attrs={"class": "field field-num", "step": "0.01", "placeholder": "0,00",
                                                "inputmode": "decimal"}),
            "notes": w.text("Ex.: conferido no app do banco"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = BankAccount.objects.filter(active=True).select_related("parent")

    def validate_unique(self):
        # Um saldo por conta e dia: informar de novo no mesmo dia substitui (ver BalanceSnapshotCreateView)
        pass
