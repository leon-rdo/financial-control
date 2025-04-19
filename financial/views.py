from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.db.models import Sum

from .filters import CategoryFilter, FinancialRecordFilter, InstallmentFilter
from financial.forms import FinancialRecordForm
from .models import Category, FinancialRecord, Installment
from django.shortcuts import redirect
from django_filters.views import FilterView


class FinancialRecordCreateView(CreateView):
    template_name = "financial/financial-records/create.html"
    model = FinancialRecord
    form_class = FinancialRecordForm
    extra_context = {
        "title": "Criar Registro Financeiro",
        "description": "Formulário para criar um novo registro financeiro",
    }
    success_url = reverse_lazy("financial:financial_record_list")


class FinancialRecordListView(FilterView):
    template_name = "financial/financial-records/list.html"
    model = FinancialRecord
    filterset_class = FinancialRecordFilter
    paginate_by = 20
    extra_context = {
        "title": "Registros Financeiros",
        "description": "Lista de registros financeiros",
        "total_incomes": FinancialRecord.objects.filter(amount__gte=0).aggregate(Sum("amount"))["amount__sum"],
        "total_expenses": abs(FinancialRecord.objects.filter(amount__lt=0).aggregate(Sum("amount"))["amount__sum"] or 0),
        "total_balance": FinancialRecord.objects.aggregate(Sum("amount"))["amount__sum"]
    }


class InstallmentListView(FilterView):
    template_name = "financial/installments/list.html"
    model = Installment
    filterset_class = InstallmentFilter
    paginate_by = 20
    extra_context = {
        "title": "Parcelas",
        "description": "Lista de parcelas",
        "total_amount": Installment.objects.aggregate(Sum("amount"))["amount__sum"] or 0,
        "total_paid": Installment.objects.filter(is_paid=True).aggregate(Sum("amount"))["amount__sum"] or 0,
        "total_unpaid": abs(Installment.objects.filter(is_paid=False).aggregate(Sum("amount"))["amount__sum"] or 0),
    }


class CategoryListView(FilterView):
    template_name = "financial/categories/list.html"
    model = Category
    filterset_class = CategoryFilter
    paginate_by = 40
    extra_context = {"title": "Categorias", "description": "Lista de categorias"}

    def post(self, request, *args, **kwargs):
        name = request.POST.get("name")
        delete_id = request.POST.get("delete_id")
        edit_id = request.POST.get("edit_id")

        # Edit
        if edit_id:
            category = Category.objects.get(id=edit_id)
            category.name = request.POST.get("name")
            category.description = request.POST.get("description")
            category.is_income = request.POST.get("is_income") == "true"
            category.save()
            return redirect(request.path)

        # Create
        if name:
            Category.objects.create(
                name=name,
                description=request.POST.get("description"),
                is_income=request.POST.get("is_income") == "true"
            )

        # Delete
        if delete_id:
            Category.objects.filter(id=delete_id).delete()

        return redirect(request.path)
