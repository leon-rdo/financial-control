import json
import re

import requests
from django.db.models import Count, Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from django_filters.views import FilterView

from .filters import CategoryFilter, EntityFilter, TagFilter
from .forms import CategoryForm, EntityForm, FamilyMemberForm, TagForm
from .mixins import HtmxDeleteMixin, HtmxModalFormMixin
from .models import Category, Entity, FamilyMember, Tag


class InlineCreateMixin:
    """POST ?inline=1 com JSON: cria o registro a partir de outro formulário e
    devolve id e nome (usado no formulário de transação)."""

    inline_fields = ("name",)

    def dispatch(self, request, *args, **kwargs):
        if request.GET.get("inline") and request.method == "POST":
            return self.create_inline(request)
        return super().dispatch(request, *args, **kwargs)

    def create_inline(self, request):
        try:
            form = self.form_class(json.loads(request.body))
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "Dados inválidos"}, status=400)
        if form.is_valid():
            obj = form.save()
            return JsonResponse({"success": True, "object": {"id": obj.pk, "name": obj.name}})
        first = next(iter(form.errors.values()), ["Confira os campos."])[0]
        return JsonResponse({"success": False, "error": first, "errors": form.errors}, status=400)


class TableListView(FilterView):
    table_template = None
    paginate_by = 20
    context_object_name = "object_list"

    def get_template_names(self):
        if self.request.htmx:
            return [self.table_template]
        return [self.template_name]


# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------

def categories_qs():
    return Category.objects.annotate(
        uses=Count("transactions", distinct=True) + Count("purchases", distinct=True)
    ).order_by("-active", "type", "name")


class CategoryListView(TableListView):
    model = Category
    template_name = "core/category_list.html"
    table_template = "core/category_table.html"
    filterset_class = CategoryFilter

    def get_queryset(self):
        return categories_qs()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active = Category.objects.filter(active=True)
        context["counts"] = {"expense": active.exclude(type="INCOME").count(),
                             "income": active.exclude(type="EXPENSE").count(),
                             "inactive": Category.objects.filter(active=False).count()}
        return context


class CategoryTableMixin(HtmxModalFormMixin):
    model = Category
    form_class = CategoryForm
    template_name = "core/category_form.html"
    table_template = "core/category_table.html"
    table_target = "#category-table"
    success_url = reverse_lazy("core:category_list")
    success_message = "Categoria salva."

    def get_table_queryset(self):
        return categories_qs()


class CategoryCreateView(InlineCreateMixin, CategoryTableMixin, CreateView):
    def get_initial(self):
        return {"active": True, "type": "EXPENSE", "color": "#1B3F8F"}


class CategoryUpdateView(CategoryTableMixin, UpdateView):
    pass


class CategoryDeleteView(HtmxDeleteMixin, CategoryTableMixin, DeleteView):
    success_message = "Categoria excluída."


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

def tags_qs():
    return Tag.objects.annotate(uses=Count("transactions")).order_by("name")


class TagListView(TableListView):
    model = Tag
    template_name = "core/tag_list.html"
    table_template = "core/tag_table.html"
    filterset_class = TagFilter

    def get_queryset(self):
        return tags_qs()


class TagTableMixin(HtmxModalFormMixin):
    model = Tag
    form_class = TagForm
    template_name = "core/tag_form.html"
    table_template = "core/tag_table.html"
    table_target = "#tag-table"
    success_url = reverse_lazy("core:tag_list")
    success_message = "Tag salva."

    def get_table_queryset(self):
        return tags_qs()


class TagCreateView(InlineCreateMixin, TagTableMixin, CreateView):
    def get_initial(self):
        return {"color": "#1B3F8F"}


class TagUpdateView(TagTableMixin, UpdateView):
    pass


class TagDeleteView(HtmxDeleteMixin, TagTableMixin, DeleteView):
    success_message = "Tag excluída."


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------

def entities_qs():
    return Entity.objects.annotate(uses=Count("transactions", distinct=True)).order_by("-active", "name")


class EntityListView(TableListView):
    model = Entity
    template_name = "core/entity_list.html"
    table_template = "core/entity_table.html"
    filterset_class = EntityFilter

    def get_queryset(self):
        return entities_qs()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active = Entity.objects.filter(active=True)
        context["counts"] = {"total": active.count(), "people": active.filter(type="PERSON").count(),
                             "suppliers": active.filter(type="SUPPLIER").count()}
        return context


class EntityTableMixin(HtmxModalFormMixin):
    model = Entity
    form_class = EntityForm
    template_name = "core/entity_form.html"
    table_template = "core/entity_table.html"
    table_target = "#entity-table"
    success_url = reverse_lazy("core:entity_list")
    success_message = "Entidade salva."

    def get_table_queryset(self):
        return entities_qs()


class EntityCreateView(InlineCreateMixin, EntityTableMixin, CreateView):
    def get_initial(self):
        return {"active": True, "type": self.request.GET.get("tipo", "SUPPLIER")}


class EntityUpdateView(EntityTableMixin, UpdateView):
    pass


class EntityDeleteView(HtmxDeleteMixin, EntityTableMixin, DeleteView):
    success_message = "Entidade excluída."


# ---------------------------------------------------------------------------
# Família
# ---------------------------------------------------------------------------

def family_qs():
    return FamilyMember.objects.annotate(
        accounts=Count("bank_accounts", distinct=True), methods=Count("payment_methods", distinct=True)
    ).prefetch_related("bank_accounts", "payment_methods").order_by("-active", "name")


class FamilyListView(ListView):
    model = FamilyMember
    template_name = "core/family_list.html"
    context_object_name = "object_list"

    def get_queryset(self):
        return family_qs()

    def get_context_data(self, **kwargs):
        from accounts.models import BankAccount, PaymentMethod

        context = super().get_context_data(**kwargs)
        no_holder = {
            "accounts": BankAccount.objects.filter(active=True, holder__isnull=True, parent__isnull=True).count(),
            "methods": PaymentMethod.objects.filter(active=True, holder__isnull=True).filter(
                Q(bank_account__isnull=True) | Q(bank_account__holder__isnull=True),
                billing_card__isnull=True).count(),
        }
        no_holder["total"] = no_holder["accounts"] + no_holder["methods"]
        context["no_holder"] = no_holder
        context["with_telegram"] = FamilyMember.objects.filter(active=True, telegram_chat_id__isnull=False).count()
        return context


class FamilyTableMixin(HtmxModalFormMixin):
    model = FamilyMember
    form_class = FamilyMemberForm
    template_name = "core/family_form.html"
    table_template = "core/family_table.html"
    table_target = "#family-table"
    success_url = reverse_lazy("core:family_list")
    success_message = "Pessoa salva."

    def get_table_queryset(self):
        return family_qs()


class FamilyCreateView(FamilyTableMixin, CreateView):
    def get_initial(self):
        return {"active": True}


class FamilyUpdateView(FamilyTableMixin, UpdateView):
    pass


class FamilyDeleteView(HtmxDeleteMixin, FamilyTableMixin, DeleteView):
    success_message = "Pessoa removida."


# ---------------------------------------------------------------------------
# CNPJ
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def fetch_cnpj_data(request):
    """Dados de um CNPJ na API aberta da CNPJá."""
    cnpj = re.sub(r"\D", "", request.GET.get("cnpj", ""))
    if len(cnpj) != 14:
        return JsonResponse({"error": "CNPJ inválido: digite os 14 números."}, status=400)
    try:
        response = requests.get(f"https://open.cnpja.com/office/{cnpj}", timeout=10)
    except requests.Timeout:
        return JsonResponse({"error": "A consulta do CNPJ demorou demais. Tente de novo."}, status=500)
    except requests.RequestException:
        return JsonResponse({"error": "Não deu para consultar o CNPJ agora."}, status=500)
    if response.status_code == 404:
        return JsonResponse({"error": "CNPJ não encontrado."}, status=404)
    if response.status_code != 200:
        return JsonResponse({"error": "Não deu para consultar o CNPJ. Tente de novo."}, status=500)
    data = response.json()
    emails, phones = data.get("emails", []), data.get("phones", [])
    phone = ""
    if phones and phones[0].get("area") and phones[0].get("number"):
        phone = f"({phones[0]['area']}) {phones[0]['number']}"
    return JsonResponse({"success": True, "data": {
        "name": data.get("alias") or data.get("company", {}).get("name", ""),
        "email": emails[0].get("address", "") if emails else "",
        "phone": phone,
        "document": cnpj,
    }})
