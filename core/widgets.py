"""Widgets com as classes do design system (static/css/confin.css).

`field` serve para input, select e textarea; `check` para caixas de seleção.
"""
from django import forms


def text(placeholder="", **attrs):
    return forms.TextInput(attrs={"class": "field", "placeholder": placeholder, **attrs})


def money(placeholder="0,00", **attrs):
    return forms.NumberInput(attrs={"class": "field field-num", "placeholder": placeholder, "step": "0.01",
                                    "inputmode": "decimal", **attrs})


def number(placeholder="", **attrs):
    return forms.NumberInput(attrs={"class": "field field-num", "placeholder": placeholder, "inputmode": "numeric",
                                    **attrs})


def day(placeholder=""):
    return number(placeholder, min="1", max="31")


def date():
    return forms.DateInput(attrs={"class": "field", "type": "date"}, format="%Y-%m-%d")


def select(**attrs):
    return forms.Select(attrs={"class": "field", **attrs})


def multi(**attrs):
    return forms.SelectMultiple(attrs={"class": "field", "multiple": "multiple", **attrs})


def area(placeholder="", rows=3):
    return forms.Textarea(attrs={"class": "field", "placeholder": placeholder, "rows": rows})


def check():
    return forms.CheckboxInput(attrs={"class": "check"})


class FriendlyEmptyLabels:
    """Troca o '---------' das listas de escolha por um texto que diz o que fazer."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.forms import ModelChoiceField

        for field in self.fields.values():
            if isinstance(field, ModelChoiceField) and str(field.empty_label or "").startswith("---"):
                field.empty_label = "Escolha" if field.required else "Nenhuma"
