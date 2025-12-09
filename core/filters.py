import django_filters
from django import forms
from .models import Category, Tag, Entity


class CategoryFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Buscar por nome...",
            }
        ),
    )

    type = django_filters.ChoiceFilter(
        choices=[("", "Todos")] + list(Category.TypeChoices.choices),
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )

    active = django_filters.ChoiceFilter(
        choices=[("", "Todos"), ("true", "Ativos"), ("false", "Inativos")],
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )

    class Meta:
        model = Category
        fields = ["name", "type", "active"]


class TagFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Buscar por nome...",
            }
        ),
    )

    class Meta:
        model = Tag
        fields = ["name"]


class EntityFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(
            attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Buscar por nome...",
            }
        ),
    )

    type = django_filters.ChoiceFilter(
        choices=[("", "Todos")] + list(Entity.TypeChoices.choices),
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )

    active = django_filters.ChoiceFilter(
        choices=[("", "Todos"), ("true", "Ativos"), ("false", "Inativos")],
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )

    class Meta:
        model = Entity
        fields = ["name", "type", "active"]
