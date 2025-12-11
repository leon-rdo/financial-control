from django import forms
from .models import Recurrence, Transaction, Purchase


class RecurrenceForm(forms.ModelForm):
    class Meta:
        model = Recurrence
        fields = [
            "description",
            "amount",
            "type",
            "category",
            "entity",
            "payment_method",
            "frequency",
            "reference_day",
            "start_date",
            "end_date",
            "active",
            "notes",
        ]
        widgets = {
            "description": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: Aluguel mensal",
                }
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "0.00",
                    "step": "0.01",
                }
            ),
            "type": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "entity": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "payment_method": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "frequency": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "reference_day": forms.NumberInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: 5",
                    "min": "1",
                    "max": "31",
                }
            ),
            "start_date": forms.DateInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "type": "date",
                },
                format="%Y-%m-%d",
            ),
            "end_date": forms.DateInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "type": "date",
                },
                format="%Y-%m-%d",
            ),
            "active": forms.CheckboxInput(
                attrs={
                    "class": "checkbox checkbox-primary",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered w-full",
                    "placeholder": "Observações adicionais...",
                    "rows": 3,
                }
            ),
        }


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = [
            "type",
            "description",
            "amount",
            "date",
            "category",
            "entity",
            "payment_method",
            "confirmed",
            "tags",
            "notes",
        ]
        widgets = {
            "type": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "description": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: Compra no supermercado",
                }
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "0.00",
                    "step": "0.01",
                }
            ),
            "date": forms.DateInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "type": "date",
                },
                format="%Y-%m-%d",
            ),
            "category": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "entity": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "payment_method": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "confirmed": forms.CheckboxInput(
                attrs={
                    "class": "checkbox checkbox-primary",
                }
            ),
            "tags": forms.SelectMultiple(
                attrs={
                    "class": "select select-bordered w-full",
                    "multiple": "multiple",
                    "size": "5",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered w-full",
                    "placeholder": "Observações adicionais...",
                    "rows": 3,
                }
            ),
        }


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = [
            "description",
            "total_amount",
            "purchase_date",
            "number_of_installments",
            "entity",
            "category",
            "payment_method",
            "notes",
        ]
        widgets = {
            "description": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: Notebook Dell",
                }
            ),
            "total_amount": forms.NumberInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "0.00",
                    "step": "0.01",
                }
            ),
            "purchase_date": forms.DateInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "type": "date",
                },
                format="%Y-%m-%d",
            ),
            "number_of_installments": forms.NumberInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Ex: 12",
                    "min": "1",
                }
            ),
            "entity": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "payment_method": forms.Select(
                attrs={
                    "class": "select select-bordered w-full",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "textarea textarea-bordered w-full",
                    "placeholder": "Observações adicionais...",
                    "rows": 3,
                }
            ),
        }
