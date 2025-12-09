from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.http import HttpResponse, JsonResponse
from django_filters.views import FilterView
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
import requests
import re
from .models import Category, Tag, Entity
from .forms import CategoryForm, TagForm, EntityForm
from .filters import CategoryFilter, TagFilter, EntityFilter


# Category Views
class CategoryListView(FilterView):
    model = Category
    template_name = "core/category_list.html"
    context_object_name = "object_list"
    filterset_class = CategoryFilter
    paginate_by = 20

    def get_template_names(self):
        if self.request.htmx:
            return ["core/category_table.html"]
        return [self.template_name]


class CategoryCreateView(CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "core/category_form.html"
    success_url = reverse_lazy("category_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "categoryCreated"
            context = {
                "object_list": Category.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "core/category_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class CategoryUpdateView(UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "core/category_form.html"
    success_url = reverse_lazy("category_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "categoryUpdated"
            context = {
                "object_list": Category.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "core/category_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class CategoryDeleteView(DeleteView):
    model = Category
    success_url = reverse_lazy("category_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        if request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "categoryDeleted"
            context = {
                "object_list": Category.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "core/category_table.html", context, request=request
            )
            response.content = html
            return response

        return super().delete(request, *args, **kwargs)


# Tag Views
class TagListView(FilterView):
    model = Tag
    template_name = "core/tag_list.html"
    context_object_name = "object_list"
    filterset_class = TagFilter
    paginate_by = 20

    def get_template_names(self):
        if self.request.htmx:
            return ["core/tag_table.html"]
        return [self.template_name]


class TagCreateView(CreateView):
    model = Tag
    form_class = TagForm
    template_name = "core/tag_form.html"
    success_url = reverse_lazy("tag_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "tagCreated"
            context = {
                "object_list": Tag.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "core/tag_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class TagUpdateView(UpdateView):
    model = Tag
    form_class = TagForm
    template_name = "core/tag_form.html"
    success_url = reverse_lazy("tag_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "tagUpdated"
            context = {
                "object_list": Tag.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "core/tag_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class TagDeleteView(DeleteView):
    model = Tag
    success_url = reverse_lazy("tag_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        if request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "tagDeleted"
            context = {
                "object_list": Tag.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string("core/tag_table.html", context, request=request)
            response.content = html
            return response

        return super().delete(request, *args, **kwargs)


# Entity Views
class EntityListView(FilterView):
    model = Entity
    template_name = "core/entity_list.html"
    context_object_name = "object_list"
    filterset_class = EntityFilter
    paginate_by = 20

    def get_template_names(self):
        if self.request.htmx:
            return ["core/entity_table.html"]
        return [self.template_name]


class EntityCreateView(CreateView):
    model = Entity
    form_class = EntityForm
    template_name = "core/entity_form.html"
    success_url = reverse_lazy("entity_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "entityCreated"
            context = {
                "object_list": Entity.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "core/entity_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class EntityUpdateView(UpdateView):
    model = Entity
    form_class = EntityForm
    template_name = "core/entity_form.html"
    success_url = reverse_lazy("entity_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "entityUpdated"
            context = {
                "object_list": Entity.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "core/entity_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class EntityDeleteView(DeleteView):
    model = Entity
    success_url = reverse_lazy("entity_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        if request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "entityDeleted"
            context = {
                "object_list": Entity.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string("core/entity_table.html", context, request=request)
            response.content = html
            return response

        return super().delete(request, *args, **kwargs)


# CNPJ Fetch API
@require_http_methods(["GET"])
def fetch_cnpj_data(request):
    """Busca dados de CNPJ na API CNPJA"""
    cnpj = request.GET.get("cnpj", "")

    # Remove formatação do CNPJ
    cnpj_clean = re.sub(r"\D", "", cnpj)

    if not cnpj_clean or len(cnpj_clean) != 14:
        return JsonResponse(
            {"error": "CNPJ inválido. Digite um CNPJ válido com 14 dígitos."},
            status=400,
        )

    try:
        # Chama a API CNPJA
        response = requests.get(
            f"https://open.cnpja.com/office/{cnpj_clean}", timeout=10
        )

        if response.status_code == 404:
            return JsonResponse(
                {"error": "CNPJ não encontrado na base de dados."}, status=404
            )

        if response.status_code != 200:
            return JsonResponse(
                {"error": "Erro ao consultar CNPJ. Tente novamente."}, status=500
            )

        data = response.json()

        # Extrai informações relevantes
        company_name = data.get("company", {}).get("name", "")
        alias = data.get("alias", "")

        # Nome: usa alias se existir, senão usa o nome da empresa
        name = alias if alias else company_name

        # Email: pega o primeiro email corporativo
        emails = data.get("emails", [])
        email = ""
        if emails:
            email = emails[0].get("address", "")

        # Telefone: pega o primeiro telefone
        phones = data.get("phones", [])
        phone = ""
        if phones:
            area = phones[0].get("area", "")
            number = phones[0].get("number", "")
            if area and number:
                phone = f"({area}) {number}"

        return JsonResponse(
            {
                "success": True,
                "data": {
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "document": cnpj_clean,
                },
            }
        )

    except requests.Timeout:
        return JsonResponse(
            {"error": "Tempo esgotado ao consultar CNPJ. Tente novamente."}, status=500
        )
    except requests.RequestException as e:
        return JsonResponse({"error": f"Erro ao consultar CNPJ: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Erro inesperado: {str(e)}"}, status=500)
