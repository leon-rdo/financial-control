import django_filters

from . import widgets as w
from .models import Category, Entity, Tag


def active_choice():
    return django_filters.ChoiceFilter(choices=[("1", "Ativos"), ("0", "Inativos")], empty_label="Todos",
                                       widget=w.select())


class CategoryFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr="icontains", widget=w.text("Buscar pelo nome", type="search"))
    type = django_filters.ChoiceFilter(choices=Category.TypeChoices.choices, empty_label="Todos", widget=w.select())
    active = active_choice()

    class Meta:
        model = Category
        fields = ["name", "type", "active"]


class TagFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr="icontains", widget=w.text("Buscar pelo nome", type="search"))

    class Meta:
        model = Tag
        fields = ["name"]


class EntityFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr="icontains", widget=w.text("Buscar pelo nome", type="search"))
    type = django_filters.ChoiceFilter(choices=Entity.TypeChoices.choices, empty_label="Todos", widget=w.select())
    active = active_choice()

    class Meta:
        model = Entity
        fields = ["name", "type", "active"]
