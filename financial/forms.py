from django import forms
from django_select2.forms import ModelSelect2Widget, Select2Widget
from .models import FinancialRecord


class FinancialRecordForm(forms.ModelForm):
    class Meta:
        model = FinancialRecord
        fields = [
            "date",
            "amount",
            "description",
            "payment_method",
            "category",
            "entity",
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
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "amount": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
