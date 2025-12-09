from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.http import HttpResponse
from django_filters.views import FilterView
from .models import Category
from .forms import CategoryForm
from .filters import CategoryFilter


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
            # Retorna a tabela atualizada
            from django.template.loader import render_to_string

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

    def form_invalid(self, form):
        if self.request.htmx:
            return super().form_invalid(form)
        return super().form_invalid(form)


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
            # Retorna a tabela atualizada
            from django.template.loader import render_to_string

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
            # Retorna a tabela atualizada
            from django.template.loader import render_to_string

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
