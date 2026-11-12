from django import forms

from accounts.models import BankAccount, PaymentMethod
from core import widgets as w
from core.models import Entity

from .models import Purchase, Recurrence, Transaction, Transfer


def third_party_field(form):
    """'Por conta de': só pessoas de fora da família (Entity do tipo PERSON)."""
    field = form.fields["on_behalf_of"]
    current = form.instance.on_behalf_of_id if form.instance.pk else None
    field.queryset = Entity.objects.filter(type=Entity.TypeChoices.PERSON).filter(
        active=True) | Entity.objects.filter(pk=current)
    field.empty_label = "Ninguém, é da família"
    field.required = False


class RecurrenceForm(w.FriendlyEmptyLabels, forms.ModelForm):
    class Meta:
        model = Recurrence
        fields = ["description", "amount", "type", "category", "entity", "payment_method", "frequency",
                  "reference_day", "start_date", "end_date", "active", "notes"]
        widgets = {
            "description": w.text("Ex.: Aluguel"),
            "amount": w.money(),
            "type": w.select(),
            "category": w.select(),
            "entity": w.select(),
            "payment_method": w.select(),
            "frequency": w.select(),
            "reference_day": w.day("Ex.: 5"),
            "start_date": w.date(),
            "end_date": w.date(),
            "active": w.check(),
            "notes": w.area("Observações"),
        }


class TransactionForm(w.FriendlyEmptyLabels, forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["type", "description", "amount", "date", "category", "entity", "payment_method", "on_behalf_of",
                  "confirmed", "tags", "notes"]
        widgets = {
            "type": w.select(),
            "description": w.text("Ex.: Supermercado"),
            "amount": w.money(),
            "date": w.date(),
            "category": w.select(),
            "entity": w.select(),
            "payment_method": w.select(),
            "on_behalf_of": w.select(),
            "confirmed": w.check(),
            "tags": w.multi(size="4"),
            "notes": w.area("Observações"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        third_party_field(self)


class PurchaseForm(w.FriendlyEmptyLabels, forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ["description", "total_amount", "purchase_date", "number_of_installments", "entity", "category",
                  "payment_method", "on_behalf_of", "notes"]
        widgets = {
            "description": w.text("Ex.: Geladeira"),
            "total_amount": w.money(),
            "purchase_date": w.date(),
            "number_of_installments": w.number("Ex.: 10", min="1"),
            "entity": w.select(),
            "category": w.select(),
            "payment_method": w.select(),
            "on_behalf_of": w.select(),
            "notes": w.area("Observações"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        third_party_field(self)


class TransferForm(w.FriendlyEmptyLabels, forms.ModelForm):
    """Pagamento de fatura ou dinheiro movido entre contas e caixinhas da família.
    Não é receita nem despesa."""

    invoice = forms.CharField(
        label="Fatura paga (mês de vencimento)", required=False,
        widget=forms.DateInput(attrs={"class": "field", "type": "month"}),
    )

    class Meta:
        model = Transfer
        fields = ["date", "amount", "description", "from_account", "to_account", "to_card", "notes"]
        widgets = {
            "date": w.date(),
            "amount": w.money(),
            "description": w.text("Ex.: Pagamento da fatura"),
            "from_account": w.select(),
            "to_account": w.select(),
            "to_card": w.select(),
            "notes": w.area("Observações", rows=2),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = BankAccount.objects.filter(active=True).select_related("parent")
        self.fields["from_account"].queryset = accounts
        self.fields["to_account"].queryset = accounts
        self.fields["from_account"].empty_label = "Fora do sistema ou desconhecida"
        self.fields["to_account"].empty_label = "Nenhuma (é pagamento de fatura)"
        self.fields["to_card"].queryset = PaymentMethod.objects.filter(
            type=PaymentMethod.TypeChoices.CREDIT, billing_card__isnull=True, active=True)
        self.fields["to_card"].empty_label = "Nenhum (é entre contas)"
        if self.instance.pk and self.instance.invoice_year and self.instance.invoice_month:
            self.initial["invoice"] = f"{self.instance.invoice_year}-{self.instance.invoice_month:02d}"

    def clean(self):
        data = super().clean()
        if data.get("to_account") and data.get("to_card"):
            raise forms.ValidationError("Escolha o destino: uma conta ou um cartão, não os dois.")
        if data.get("from_account") and data.get("from_account") == data.get("to_account"):
            raise forms.ValidationError("A origem e o destino são a mesma conta.")
        invoice = data.get("invoice")
        if data.get("to_card") and not invoice:
            self.add_error("invoice", "Informe o mês da fatura paga.")
        if invoice:
            try:
                year, month = (int(p) for p in invoice.split("-"))
            except ValueError:
                self.add_error("invoice", "Use o formato AAAA-MM.")
            else:
                self.instance.invoice_year, self.instance.invoice_month = year, month
        if not data.get("to_card"):
            self.instance.invoice_year = self.instance.invoice_month = None
        return data
