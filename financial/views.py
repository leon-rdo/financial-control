from django.views.generic import CreateView, ListView
from django.db.models import Sum

from financial.forms import FinancialRecordForm
from .models import FinancialRecord


class FinancialRecordCreateView(CreateView):
    template_name = "financial/financial-records/create.html"
    model = FinancialRecord
    form_class = FinancialRecordForm
    extra_context = {
        "title": "Criar Registro Financeiro",
        "description": "Formulário para criar um novo registro financeiro",
    }
    success_url = "financial:financial_record_list"


class FinancialRecordListView(ListView):
    template_name = "financial/financial-records/list.html"
    model = FinancialRecord
    paginate_by = 20
    extra_context = {
        "title": "Registros Financeiros",
        "description": "Lista de registros financeiros",
        "count": FinancialRecord.objects.count(),
        "total_incomes": FinancialRecord.objects.filter(amount__gte=0).aggregate(Sum("amount"))["amount__sum"],
        "total_expenses": abs(FinancialRecord.objects.filter(amount__lt=0).aggregate(Sum("amount"))["amount__sum"] or 0),
        "total_balance": FinancialRecord.objects.aggregate(Sum("amount"))["amount__sum"]
    }
