from django import forms
from django.utils.translation import gettext_lazy as _
import re
from .models import Category, Tag, Entity


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


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "color"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Nome da tag",
                }
            ),
            "color": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "#FF5733",
                    "x-model": "color",
                    "x-ref": "colorInput",
                    "type": "color",
                }
            ),
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


class EntityForm(forms.ModelForm):
    class Meta:
        model = Entity
        fields = ["name", "type", "document", "email", "phone", "active"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "Nome da entidade",
                }
            ),
            "type": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "document": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full join-item",
                    "placeholder": "00.000.000/0000-00",
                    "x-mask": "99.999.999/9999-99",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "email@exemplo.com",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "input input-bordered w-full",
                    "placeholder": "(00) 00000-0000",
                    "x-mask": "(99) 99999-9999",
                }
            ),
            "active": forms.CheckboxInput(attrs={"class": "checkbox checkbox-primary"}),
        }

    def clean_document(self):
        document = self.cleaned_data.get("document", "")
        if not document:
            return document

        # Remove formatação
        clean_doc = re.sub(r"\D", "", document)

        # Valida tamanho (CPF: 11 dígitos, CNPJ: 14 dígitos)
        if clean_doc and len(clean_doc) not in [11, 14]:
            raise forms.ValidationError(
                _(
                    "Documento inválido. Digite um CPF (11 dígitos) ou CNPJ (14 dígitos)."
                )
            )

        return clean_doc
