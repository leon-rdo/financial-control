from django import forms
from .models import BankAccount, PaymentMethod


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ["name", "bank", "type", "parent", "color", "opening_balance", "opening_balance_date", "active"]
        widgets = {
            "parent": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "opening_balance": forms.NumberInput(
                attrs={"class": "input input-bordered w-full", "step": "0.01"}
            ),
            "opening_balance_date": forms.DateInput(
                attrs={"class": "input input-bordered w-full", "type": "date"}, format="%Y-%m-%d"
            ),
            "name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: Nubank",
                }
            ),
            "bank": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Será preenchido automaticamente",
                }
            ),
            "type": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "color": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "#FF5733",
                    "maxlength": "7",
                }
            ),
            "active": forms.CheckboxInput(
                attrs={
                    "class": "checkbox checkbox-primary",
                }
            ),
        }


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = [
            "name",
            "type",
            "bank_account",
            "billing_card",
            "credit_limit",
            "closing_day",
            "due_day",
            "active",
        ]
        widgets = {
            "billing_card": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: Nubank Crédito",
                }
            ),
            "type": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "bank_account": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "credit_limit": forms.NumberInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "0.00",
                    "step": "0.01",
                }
            ),
            "closing_day": forms.NumberInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: 10",
                    "min": "1",
                    "max": "31",
                }
            ),
            "due_day": forms.NumberInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: 15",
                    "min": "1",
                    "max": "31",
                }
            ),
            "active": forms.CheckboxInput(
                attrs={
                    "class": "checkbox checkbox-primary",
                }
            ),
        }


class SimplePaymentMethodForm(forms.ModelForm):
    """Formulário simplificado para criação inline de métodos de pagamento"""

    class Meta:
        model = PaymentMethod
        fields = ["name", "type"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: Nubank Crédito",
                }
            ),
            "type": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.active = True
        if commit:
            instance.save()
        return instance


def _limit_choices(form):
    """Caixinha só pode ficar em conta comum; cartão adicional só em cartão principal."""
    if "parent" in form.fields:
        qs = BankAccount.objects.filter(parent__isnull=True)
        if form.instance.pk:
            qs = qs.exclude(pk=form.instance.pk)
        form.fields["parent"].queryset = qs
        form.fields["parent"].empty_label = "Nenhuma (conta comum)"
    if "billing_card" in form.fields:
        qs = PaymentMethod.objects.filter(type="CREDIT", billing_card__isnull=True)
        if form.instance.pk:
            qs = qs.exclude(pk=form.instance.pk)
        form.fields["billing_card"].queryset = qs
        form.fields["billing_card"].empty_label = "Nenhum (fatura própria)"


for _form in (BankAccountForm, PaymentMethodForm):
    _original_init = _form.__init__

    def _init(self, *args, _original_init=_original_init, **kwargs):
        _original_init(self, *args, **kwargs)
        _limit_choices(self)

    _form.__init__ = _init
