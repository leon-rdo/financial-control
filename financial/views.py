import json
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, UpdateView
from django.db.models import Sum

from utils.htmx_views import HxModalCreateView, HxModalDeleteView, HxModalUpdateView
from utils.page_for_object import get_page_number
from .filters import CategoryFilter, FinancialRecordFilter, InstallmentFilter
from financial.forms import CategoryForm, FinancialRecordForm
from .models import Category, FinancialRecord, Installment
from django.shortcuts import redirect, render
from django_filters.views import FilterView


class FinancialRecordCreateView(PermissionRequiredMixin, CreateView):
    permission_required = "financial.add_financialrecord"
    template_name = "financial/financial-records/form.html"
    model = FinancialRecord
    form_class = FinancialRecordForm
    extra_context = {
        "title": "Criar Registro Financeiro",
        "description": "Formulário para criar um novo registro financeiro",
    }

    def form_valid(self, form):
        response = super().form_valid(form)
        record = self.object
        qty = form.cleaned_data.get("installments_quantity") or 1
        layaway = form.cleaned_data.get("is_layaway")
        record.create_installments(qty, layaway)
        messages.success(self.request, "Registro financeiro criado com sucesso.")
        return response

    def get_success_url(self):
        return reverse_lazy(
            "financial:financial_record_detail", kwargs={"pk": self.object.pk}
        )


class FinancialRecordListView(PermissionRequiredMixin, FilterView):
    permission_required = "financial.view_financialrecord"
    template_name = "financial/financial-records/list.html"
    model = FinancialRecord
    filterset_class = FinancialRecordFilter
    paginate_by = 20
    extra_context = {
        "title": "Registros Financeiros",
        "description": "Lista de registros financeiros",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        full_queryset = (
            self.filterset.qs if hasattr(self, "filterset") else self.get_queryset()
        )

        total_incomes = (
            full_queryset.filter(amount__gte=0).aggregate(Sum("amount"))["amount__sum"]
            or 0
        )
        total_expenses = abs(
            full_queryset.filter(amount__lt=0).aggregate(Sum("amount"))["amount__sum"]
            or 0
        )
        total_balance = full_queryset.aggregate(Sum("amount"))["amount__sum"] or 0

        context["total_incomes"] = total_incomes
        context["total_expenses"] = total_expenses
        context["total_balance"] = total_balance
        return context

    def post(self, request):
        delete_id = request.POST.get("delete_id")

        if delete_id:
            if not request.user.has_perm("financial.delete_financialrecord"):
                messages.error(
                    request,
                    "Você não tem permissão para deletar este registro financeiro.",
                )
                return redirect(request.path)
            FinancialRecord.objects.filter(id=delete_id).delete()
            messages.success(request, "Registro financeiro deletado com sucesso.")

        return redirect(request.path)


class FinancialRecordDetailView(PermissionRequiredMixin, DetailView):
    permission_required = "financial.view_financialrecord"
    template_name = "financial/financial-records/detail.html"
    model = FinancialRecord
    extra_context = {
        "title": "Detalhes do Registro Financeiro",
        "description": "Detalhes do registro financeiro selecionado",
    }

    def post(self, request, *args, **kwargs):
        delete_id = request.POST.get("delete_id")

        if delete_id:
            if not request.user.has_perm("financial.delete_financialrecord"):
                messages.error(
                    request,
                    "Você não tem permissão para deletar este registro financeiro.",
                )
                return redirect(request.path)
            FinancialRecord.objects.filter(id=delete_id).delete()
            messages.success(request, "Registro financeiro deletado com sucesso.")
            return redirect(reverse_lazy("financial:financial_record_list"))

        return redirect(request.path)


class FinancialRecordUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = "financial.change_financialrecord"
    template_name = "financial/financial-records/form.html"
    model = FinancialRecord
    form_class = FinancialRecordForm
    extra_context = {
        "title": "Atualizar Registro Financeiro",
        "description": "Formulário para atualizar um registro financeiro existente",
    }

    def get_success_url(self):
        return reverse_lazy(
            "financial:financial_record_detail", kwargs={"pk": self.object.pk}
        )


class InstallmentListView(PermissionRequiredMixin, FilterView):
    permission_required = "financial.view_installment"
    template_name = "financial/installments/list.html"
    model = Installment
    filterset_class = InstallmentFilter
    paginate_by = 20
    extra_context = {
        "title": "Parcelas",
        "description": "Lista de parcelas",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        full_queryset = (
            self.filterset.qs if hasattr(self, "filterset") else self.get_queryset()
        )

        total_amount = full_queryset.aggregate(Sum("amount"))["amount__sum"] or 0
        total_paid = (
            full_queryset.filter(is_paid=True).aggregate(Sum("amount"))["amount__sum"]
            or 0
        )
        total_unpaid = abs(
            full_queryset.filter(is_paid=False).aggregate(Sum("amount"))["amount__sum"]
            or 0
        )

        context["total_amount"] = total_amount
        context["total_paid"] = total_paid
        context["total_unpaid"] = total_unpaid
        return context


class CategoryCreateView(HxModalCreateView):
    model = Category
    form_class = CategoryForm
    modal_title = "Criar Categoria"
    edit_url_name = "financial:category_update"
    delete_url_name = "financial:category_delete"
    row_template = "financial/categories/partials/category_row.html"


class CategoryListView(PermissionRequiredMixin, FilterView):
    permission_required = "financial.view_category"
    template_name = "financial/categories/list.html"
    model = Category
    ordering = ["name"]
    filterset_class = CategoryFilter
    paginate_by = 40
    extra_context = {"title": "Categorias", "description": "Lista de categorias"}


class CategoryUpdateView(HxModalUpdateView):
    model = Category
    form_class = CategoryForm
    modal_title = "Editar Categoria"
    edit_url_name = "financial:category_update"
    delete_url_name = None
    row_template = "financial/categories/partials/category_row.html"


class CategoryDeleteView(HxModalDeleteView):
    model = Category
    template_name = "snippets/partials/confirm_delete.html"
    modal_title = "Excluir Categoria"
    success_message = "Categoria excluída com sucesso."
