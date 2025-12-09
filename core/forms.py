from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Category


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "type", "color", "icon", "active"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Nome da categoria",
                }
            ),
            "type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "color": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "#FF5733",
                    "x-model": "color",
                    "x-ref": "colorInput",
                    "type": "color",
                }
            ),
            "icon": forms.TextInput(
                attrs={"class": "input input-bordered w-full", "placeholder": "ex: 🏠"}
            ),
            "active": forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
        }

    def clean_color(self):
        color = self.cleaned_data.get("color")
        if color and not color.startswith("#"):
            color = f"#{color}"
        if color and len(color) not in [4, 7]:
            raise forms.ValidationError(
                _("Formato de cor inválido. Use #RGB ou #RRGGBB")
            )
        return color
