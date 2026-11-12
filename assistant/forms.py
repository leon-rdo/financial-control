from django import forms

from core import widgets as w

from .models import UserRule
from .tools.rules import MAX_RULES


class UserRuleForm(forms.ModelForm):
    class Meta:
        model = UserRule
        fields = ["text", "active"]
        widgets = {
            "text": forms.Textarea(attrs={"class": "field", "rows": 3, "maxlength": "300",
                                          "placeholder": "Ex.: Compras no Posto Avenida são sempre Transporte."}),
            "active": w.check(),
        }
        labels = {"text": "Regra", "active": "Ativa"}

    def clean(self):
        data = super().clean()
        becoming_active = data.get("active") and not (self.instance.pk and self.instance.active)
        if becoming_active and UserRule.objects.filter(active=True).count() >= MAX_RULES:
            raise forms.ValidationError(
                f"Já há {MAX_RULES} regras ativas. Desative ou junte alguma antes de ativar outra.")
        return data
