from django import forms
from .models import BankAccount, PaymentMethod


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ["name", "bank", "type", "color", "active"]
        widgets = {
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
            "credit_limit",
            "closing_day",
            "due_day",
            "active",
        ]
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
