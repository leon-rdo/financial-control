from django import forms
from django_select2.forms import ModelSelect2Widget, Select2Widget
from .models import FinancialRecord


class FinancialRecordForm(forms.ModelForm):

    is_income = forms.TypedChoiceField(
        label="Tipo",
        choices={(True, "Entrada"), (False, "Saída")},
        coerce=lambda x: x == "True",
        widget=forms.RadioSelect(attrs={"class": "btn-check", "autocomplete": "off"}),
        required=True,
    )

    is_layaway = forms.BooleanField(
        label="Pagamento à prazo?",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    installments_quantity = forms.IntegerField(
        label="Quantidade de parcelas",
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = FinancialRecord
        fields = [
            "is_income",
            "date",
            "amount",
            "description",
            "payment_method",
            "category",
            "entity",
            "is_layaway",
            "installments_quantity",
        ]
        widgets = {
            "entity": ModelSelect2Widget(
                model=FinancialRecord._meta.get_field("entity").remote_field.model,
                search_fields=["name__icontains"],
                attrs={
                    "class": "form-select",
                    "data-minimum-input-length": "0",
                    "data-ajax--delay": "250",
                },
            ),
            "category": Select2Widget(
                attrs={
                    "class": "form-select",
                }
            ),
            "payment_method": Select2Widget(
                attrs={
                    "class": "form-select",
                }
            ),
            "date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
            "amount": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_income = cleaned_data.get("is_income")
        is_layaway = cleaned_data.get("is_layaway")
        qty = cleaned_data.get("installments_quantity")
        amount = cleaned_data.get("amount")

        if is_layaway and not qty:
            self.add_error("installments_quantity", "Informe a quantidade de parcelas.")

        if amount is not None and is_income is not None:
            cleaned_data["amount"] = abs(amount) if is_income else -abs(amount)

        return cleaned_data
