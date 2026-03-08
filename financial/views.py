from collections import OrderedDict
from decimal import Decimal
from datetime import timedelta

from django.views.generic import (
    CreateView,
    UpdateView,
    DeleteView,
    DetailView,
    TemplateView,
)
from django.urls import reverse_lazy
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django_filters.views import FilterView

from financial.models import Recurrence, Transaction, Purchase, Installment
from financial.forms import RecurrenceForm, TransactionForm, PurchaseForm
from financial.filters import RecurrenceFilter, TransactionFilter, PurchaseFilter
from accounts.models import BankAccount, PaymentMethod
from core.models import Category


class DashboardView(TemplateView):
    template_name = "financial/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Data atual
        today = timezone.now().date()
        first_day_month = today.replace(day=1)

        # Transações do mês atual
        transactions_month = Transaction.objects.filter(
            date__gte=first_day_month, date__lte=today
        )

        # Receitas e Despesas do mês
        income_month = transactions_month.filter(
            type="INCOME", confirmed=True
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        expense_month = transactions_month.filter(
            type="EXPENSE", confirmed=True
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        # Balanço do mês
        balance_month = income_month - expense_month

        # Saldo total (todas as transações confirmadas)
        total_income = Transaction.objects.filter(
            type="INCOME", confirmed=True
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        total_expense = Transaction.objects.filter(
            type="EXPENSE", confirmed=True
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        total_balance = total_income - total_expense

        # Transações recentes (últimas 5)
        recent_transactions = Transaction.objects.select_related(
            "category", "payment_method", "entity"
        ).order_by("-date", "-created_at")[:5]

        # Parcelas a vencer (próximos 30 dias)
        next_month = today + timedelta(days=30)
        upcoming_installments = (
            Installment.objects.filter(
                paid=False, due_date__gte=today, due_date__lte=next_month
            )
            .select_related("purchase", "purchase__payment_method")
            .order_by("due_date")[:10]
        )

        # Compras ativas (com parcelas pendentes)
        active_purchases = (
            Purchase.objects.filter(installments__paid=False)
            .distinct()
            .annotate(
                paid_count=Count("installments", filter=Q(installments__paid=True)),
                total_count=Count("installments"),
            )
            .select_related("category", "payment_method")[:5]
        )

        # Categorias mais utilizadas (mês atual)
        top_categories = (
            transactions_month.filter(type="EXPENSE")
            .values("category__name", "category__color", "category__icon")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")[:5]
        )

        # Estatísticas gerais
        context.update(
            {
                # Valores principais
                "total_balance": total_balance,
                "income_month": income_month,
                "expense_month": expense_month,
                "balance_month": balance_month,
                # Listas
                "recent_transactions": recent_transactions,
                "upcoming_installments": upcoming_installments,
                "active_purchases": active_purchases,
                "top_categories": top_categories,
                # Contadores
                "total_accounts": BankAccount.objects.filter(active=True).count(),
                "total_payment_methods": PaymentMethod.objects.filter(
                    active=True
                ).count(),
                "total_categories": Category.objects.filter(active=True).count(),
                "pending_transactions": Transaction.objects.filter(
                    confirmed=False
                ).count(),
                # Datas
                "current_month": f"{MONTH_NAMES[today.month]} {today.year}",
                "today": today,
            }
        )

        return context


class RecurrenceListView(FilterView):
    model = Recurrence
    template_name = "financial/recurrence_list.html"
    context_object_name = "object_list"
    filterset_class = RecurrenceFilter
    paginate_by = 20

    def get_template_names(self):
        if self.request.htmx:
            return ["financial/recurrence_table.html"]
        return [self.template_name]


class RecurrenceCreateView(CreateView):
    model = Recurrence
    form_class = RecurrenceForm
    template_name = "financial/recurrence_form.html"
    success_url = reverse_lazy("financial:recurrence_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "recurrenceCreated"
            context = {
                "object_list": Recurrence.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "financial/recurrence_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class RecurrenceUpdateView(UpdateView):
    model = Recurrence
    form_class = RecurrenceForm
    template_name = "financial/recurrence_form.html"
    success_url = reverse_lazy("financial:recurrence_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "recurrenceUpdated"
            context = {
                "object_list": Recurrence.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "financial/recurrence_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class RecurrenceDeleteView(DeleteView):
    model = Recurrence
    success_url = reverse_lazy("financial:recurrence_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        if request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "recurrenceDeleted"
            context = {
                "object_list": Recurrence.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "financial/recurrence_table.html", context, request=request
            )
            response.content = html
            return response

        return super().delete(request, *args, **kwargs)


class TransactionListView(FilterView):
    model = Transaction
    template_name = "financial/transaction_list.html"
    context_object_name = "object_list"
    filterset_class = TransactionFilter
    paginate_by = 20

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("category", "entity", "payment_method", "recurrence")
            .prefetch_related("tags")
        )

    def get_template_names(self):
        if self.request.htmx:
            return ["financial/transaction_table.html"]
        return [self.template_name]


class TransactionCreateView(CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "financial/transaction_form.html"
    success_url = reverse_lazy("financial:transaction_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "transactionCreated"
            context = {
                "object_list": Transaction.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "financial/transaction_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class TransactionUpdateView(UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "financial/transaction_form.html"
    success_url = reverse_lazy("financial:transaction_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "transactionUpdated"
            context = {
                "object_list": Transaction.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "financial/transaction_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class TransactionDeleteView(DeleteView):
    model = Transaction
    success_url = reverse_lazy("financial:transaction_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        if request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "transactionDeleted"
            context = {
                "object_list": Transaction.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "financial/transaction_table.html", context, request=request
            )
            response.content = html
            return response

        return super().delete(request, *args, **kwargs)


class PurchaseListView(FilterView):
    model = Purchase
    template_name = "financial/purchase_list.html"
    context_object_name = "object_list"
    filterset_class = PurchaseFilter
    paginate_by = 20

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("category", "entity", "payment_method")
            .prefetch_related("installments")
        )

    def get_template_names(self):
        if self.request.htmx:
            return ["financial/purchase_table.html"]
        return [self.template_name]


class PurchaseDetailView(DetailView):
    model = Purchase
    template_name = "financial/purchase_detail.html"
    context_object_name = "purchase"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["installments"] = self.object.installments.all().order_by(
            "installment_number"
        )
        return context


class PurchaseCreateView(CreateView):
    model = Purchase
    form_class = PurchaseForm
    template_name = "financial/purchase_form.html"
    success_url = reverse_lazy("financial:purchase_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "purchaseCreated"
            context = {
                "object_list": Purchase.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "financial/purchase_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class PurchaseUpdateView(UpdateView):
    model = Purchase
    form_class = PurchaseForm
    template_name = "financial/purchase_form.html"
    success_url = reverse_lazy("financial:purchase_list")

    def form_valid(self, form):
        self.object = form.save()
        # Regenerate installments if number changed
        if (
            "number_of_installments" in form.changed_data
            or "total_amount" in form.changed_data
        ):
            self.object.generate_installments()

        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "purchaseUpdated"
            context = {
                "object_list": Purchase.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "financial/purchase_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class PurchaseDeleteView(DeleteView):
    model = Purchase
    success_url = reverse_lazy("financial:purchase_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        if request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "purchaseDeleted"
            context = {
                "object_list": Purchase.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "financial/purchase_table.html", context, request=request
            )
            response.content = html
            return response

        return super().delete(request, *args, **kwargs)


MONTH_NAMES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


class InvoiceForecastView(TemplateView):
    template_name = "financial/invoice_forecast.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        qs = Installment.objects.filter(paid=False).select_related(
            "purchase__payment_method",
            "purchase__category",
            "purchase__entity",
        )

        payment_method_ids = self.request.GET.getlist("payment_method")
        payment_method_ids = [pid for pid in payment_method_ids if pid]
        if payment_method_ids:
            qs = qs.filter(purchase__payment_method_id__in=payment_method_ids)

        month_from = self.request.GET.get("month_from")
        if month_from:
            year, month = map(int, month_from.split("-"))
            qs = qs.filter(
                Q(reference_year__gt=year)
                | Q(reference_year=year, reference_month__gte=month)
            )

        month_to = self.request.GET.get("month_to")
        if month_to:
            year, month = map(int, month_to.split("-"))
            qs = qs.filter(
                Q(reference_year__lt=year)
                | Q(reference_year=year, reference_month__lte=month)
            )

        qs = qs.order_by(
            "reference_year",
            "reference_month",
            "purchase__payment_method__name",
            "due_date",
        )

        months_data = OrderedDict()
        grand_total = Decimal("0")

        for inst in qs:
            key = (inst.reference_year, inst.reference_month)
            pm = inst.purchase.payment_method

            if key not in months_data:
                months_data[key] = {
                    "month_name": MONTH_NAMES[key[1]],
                    "year": key[0],
                    "methods": OrderedDict(),
                    "total": Decimal("0"),
                }

            if pm.id not in months_data[key]["methods"]:
                months_data[key]["methods"][pm.id] = {
                    "payment_method": pm,
                    "installments": [],
                    "total": Decimal("0"),
                }

            months_data[key]["methods"][pm.id]["installments"].append(inst)
            months_data[key]["methods"][pm.id]["total"] += inst.amount
            months_data[key]["total"] += inst.amount
            grand_total += inst.amount

        context["months_data"] = months_data
        context["grand_total"] = grand_total
        context["payment_methods"] = PaymentMethod.objects.filter(active=True)
        context["selected_payment_methods"] = payment_method_ids
        context["selected_month_from"] = month_from or ""
        context["selected_month_to"] = month_to or ""

        return context


@require_http_methods(["POST"])
def toggle_installment_paid(request, pk):
    """Toggle paid status of an installment"""
    installment = get_object_or_404(Installment, pk=pk)
    installment.paid = not installment.paid
    installment.save()

    return JsonResponse(
        {
            "success": True,
            "paid": installment.paid,
            "installment_id": installment.pk,
        }
    )
