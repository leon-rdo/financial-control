from django import forms
from .models import PaymentMethod
from django_select2.forms import ModelSelect2Widget, Select2Widget
import requests


class PaymentMethodForm(forms.ModelForm):
    fin_institution = forms.ChoiceField(
        widget=Select2Widget(attrs={"class": "form-select"}),
        choices=[],
        label="Instituição Financeira"
    )

    class Meta:
        model = PaymentMethod
        fields = "__all__"
        widgets = {
            "owner": ModelSelect2Widget(
                search_fields=["name__icontains"],
                attrs={
                    "class": "form-select",
                    "data-minimum-input-length": "0",
                    "data-ajax--delay": "250",
                }
            ),
            "description": forms.Textarea(attrs={"class": "form-control"}),
            "payment_type": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            response = requests.get("https://brasilapi.com.br/api/banks/v1")
            response.raise_for_status()
            banks = response.json()
        except Exception:
            banks = []

        choices = [('', 'Selecione uma Instituição')]
        for bank in banks:
            if bank['code']:
                option = f"{bank['code']} - {bank['name']}"
                choices.append((option, option))
        self.fields["fin_institution"].choices = choices
