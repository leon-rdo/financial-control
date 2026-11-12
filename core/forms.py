import re

from django import forms

from . import widgets as w
from .models import Category, Entity, FamilyMember, Tag


def clean_hex(color):
    if color and not color.startswith("#"):
        color = f"#{color}"
    if color and len(color) not in (4, 7):
        raise forms.ValidationError("Cor inválida. Use #RGB ou #RRGGBB.")
    return color


class CategoryForm(w.FriendlyEmptyLabels, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "type", "color", "icon", "active"]
        widgets = {
            "name": w.text("Ex.: Mercado"),
            "type": w.select(),
            "color": forms.TextInput(attrs={"class": "field", "type": "color"}),
            "icon": w.text("Opcional"),
            "active": w.check(),
        }

    def clean_color(self):
        return clean_hex(self.cleaned_data.get("color"))


class TagForm(w.FriendlyEmptyLabels, forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "color"]
        widgets = {
            "name": w.text("Ex.: viagem"),
            "color": forms.TextInput(attrs={"class": "field", "type": "color"}),
        }

    def clean_color(self):
        return clean_hex(self.cleaned_data.get("color"))


class EntityForm(w.FriendlyEmptyLabels, forms.ModelForm):
    class Meta:
        model = Entity
        fields = ["name", "type", "document", "email", "phone", "active"]
        widgets = {
            "name": w.text("Ex.: Supermercado do bairro"),
            "type": w.select(),
            "document": w.text("CPF ou CNPJ", inputmode="numeric"),
            "email": forms.EmailInput(attrs={"class": "field", "placeholder": "email@exemplo.com"}),
            "phone": w.text("(00) 00000-0000", inputmode="tel", **{"x-mask": "(99) 99999-9999"}),
            "active": w.check(),
        }

    def clean_document(self):
        document = re.sub(r"\D", "", self.cleaned_data.get("document", "") or "")
        if document and len(document) not in (11, 14):
            raise forms.ValidationError("Documento inválido: use um CPF (11 dígitos) ou CNPJ (14 dígitos).")
        return document


class FamilyMemberForm(w.FriendlyEmptyLabels, forms.ModelForm):
    class Meta:
        model = FamilyMember
        fields = ["name", "aliases", "telegram_chat_id", "active"]
        widgets = {
            "name": w.text("Ex.: Maria"),
            "aliases": w.area("Um nome por linha, como aparece em faturas e extratos", rows=3),
            "telegram_chat_id": w.number("Opcional"),
            "active": w.check(),
        }
