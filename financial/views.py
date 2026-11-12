import json
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DeleteView, DetailView, TemplateView, UpdateView
from django_filters.views import FilterView

from accounts.models import PaymentMethod
from core.mixins import HtmxDeleteMixin, HtmxModalFormMixin, hx_trigger
from core.models import Category
from financial import forecast
from financial.filters import PurchaseFilter, RecurrenceFilter, TransactionFilter, TransferFilter, open_q
from financial.forms import PurchaseForm, RecurrenceForm, TransactionForm, TransferForm
from financial.models import InvoiceClosing, Installment, Purchase, Recurrence, Transaction, Transfer

MONTH_NAMES = forecast.MONTH_NAMES
NOT_INCOME = (forecast.REFUND_CATEGORY_NAME, forecast.REPAYMENT_CATEGORY_NAME)


def parse_month(value, default):
    """'2026-11' -> (2026, 11); qualquer coisa inválida volta o padrão."""
    try:
        year, month = (int(p) for p in (value or "").split("-"))
        if 1 <= month <= 12 and 2000 <= year <= 2100:
            return year, month
    except ValueError:
        pass
    return default


def month_label(year, month):
    return f"{MONTH_NAMES[month]} de {year}"


def family_income(start, end):
    """Receita da família: confirmada, sem devoluções de terceiros e sem estornos
    (estorno abate gasto, não é receita)."""
    return (Transaction.objects.filter(type="INCOME", confirmed=True, date__gte=start, date__lte=end,
                                       on_behalf_of__isnull=True)
            .exclude(category__name__in=NOT_INCOME)
            .aggregate(t=Sum("amount"))["t"] or Decimal("0"))


def upcoming_dues(today, days=30):
    """O que vence de agora até `days` dias: faturas, recorrências fora do cartão e
    lançamentos ainda não confirmados. Inclui faturas e lançamentos já vencidos e
    não pagos (aparecem primeiro, como atrasados)."""
    end = today + timedelta(days=days)
    items = []
    first = forecast.add_months(today.year, today.month, -1)
    last = (end.year, end.month)
    for bucket in forecast.invoice_forecast(first, last, include_items=True, today=today):
        for method in bucket["methods"]:
            dues = [it["due_date"] for it in method["items"] if it.get("due_date")]
            if not dues or method["total"] <= 0:
                continue
            due = max(dues)
            if due > end:
                continue
            items.append({"date": due, "title": f"Fatura {method['payment_method']}", "amount": method["total"],
                          "kind": "invoice", "late": due < today,
                          "href": f"{reverse('financial:invoice_forecast')}#m-{bucket['year']}-{bucket['month']:02d}",
                          "meta": "Venceu, sem pagamento registrado" if due < today else
                          f"{method['count']} lançamento{'s' if method['count'] != 1 else ''}"})
    for rec, d in forecast.projected_recurrences(today, end, credit_only=False):
        items.append({"date": d, "title": rec.description, "amount": rec.amount, "kind": "recurrence",
                      "modal": reverse("financial:recurrence_update", args=[rec.pk]) + "?depois=recarregar",
                      "income": rec.type == "INCOME", "late": False, "meta": "Recorrência"})
    pending = (Transaction.objects.filter(confirmed=False, date__lte=end, date__gte=today - timedelta(days=60))
               .exclude(payment_method__type="CREDIT").select_related("payment_method"))
    for tx in pending:
        items.append({"date": tx.date, "title": tx.description, "amount": tx.amount, "kind": "pending",
                      "modal": reverse("financial:transaction_update", args=[tx.pk]) + "?depois=recarregar",
                      "income": tx.type == "INCOME", "late": tx.date < today,
                      "meta": "Atrasado, ainda pendente" if tx.date < today else "Lançamento pendente"})
    items.sort(key=lambda i: (not i["late"], i["date"]))
    return items


class DashboardView(TemplateView):
    template_name = "financial/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        year, month = parse_month(self.request.GET.get("mes"), (today.year, today.month))
        start, end = forecast.month_start(year, month), forecast.month_end(year, month)
        is_current = (year, month) == (today.year, today.month)
        is_future = start > today
        until = min(end, today) if is_current else end

        income = family_income(start, until)
        summary = forecast.spending_summary(start, until)
        expense = summary["total"]

        # Mesmo trecho do mês anterior, para comparar sem esperar o mês acabar
        prev_y, prev_m = forecast.add_months(year, month, -1)
        prev_start = forecast.month_start(prev_y, prev_m)
        prev_until = min(forecast.month_end(prev_y, prev_m), prev_start + (until - start)) if is_current \
            else forecast.month_end(prev_y, prev_m)
        prev_expense = forecast.spending_summary(prev_start, prev_until)["total"]

        balances = forecast.account_balances(today)

        rows = summary["rows"]
        top = rows[:5]
        rest = rows[5:]
        categories = [{"label": r["label"], "total": r["total"], "count": r["count"]} for r in top]
        if rest:
            categories.append({"label": f"Outras {len(rest)}", "total": sum((r["total"] for r in rest), Decimal("0")),
                               "count": sum(r["count"] for r in rest), "other": True})
        colors = dict(Category.objects.values_list("name", "color"))
        for c in categories:
            c["color"] = colors.get(c["label"]) or ""
        biggest = max((c["total"] for c in categories), default=Decimal("0"))

        dues = upcoming_dues(today)
        still_due = sum((d["amount"] for d in dues if not d.get("income") and d["date"] <= end
                         and (d["date"] >= today or d["late"])), Decimal("0"))

        recent = (Transaction.objects.select_related("category", "payment_method", "entity")
                  .order_by("-date", "-created_at")[:6])

        ending = (Purchase.objects.filter(installments__paid=False).distinct()
                  .annotate(left=Count("installments", filter=Q(installments__paid=False)),
                            total_count=Count("installments"))
                  .filter(left__lte=3).select_related("payment_method").order_by("left", "description")[:5])

        ny, nm = forecast.add_months(year, month, 1)
        spent_share = min(100, int(expense / income * 100)) if income > 0 else (100 if expense else 0)
        context.update({
            "year": year, "month": month, "month_title": month_label(year, month),
            "is_current": is_current, "is_future": is_future, "today": today, "until": until,
            "days_left": (end - today).days if is_current else None,
            "prev_param": f"{prev_y}-{prev_m:02d}", "next_param": f"{ny}-{nm:02d}",
            "prev_month_name": MONTH_NAMES[prev_m].lower(),
            "income_month": income, "expense_month": expense, "balance_month": income - expense,
            "prev_expense": prev_expense, "expense_diff": expense - prev_expense,
            "spent_share": spent_share, "kept_share": 100 - spent_share if income - expense > 0 else 0,
            "refunds": summary["refunds"], "third_party_total": summary["third_party_total"],
            "total_balance": balances["available"], "reserved_balance": balances["reserved"],
            "balance_by_holder": balances["by_holder"], "available_anchored": balances["available_anchored"],
            "account_balances": [a for a in balances["accounts"] if not a["reserve"]][:6],
            "categories": categories, "biggest_category": biggest,
            "dues": dues[:6], "still_due": still_due, "late_dues": [d for d in dues if d["late"]],
            "recent_transactions": recent, "ending_purchases": ending,
            "pending_transactions": Transaction.objects.filter(confirmed=False, date__lte=today).count(),
        })
        return context


# ---------------------------------------------------------------------------
# Transações
# ---------------------------------------------------------------------------

def money_totals(qs):
    agg = qs.aggregate(
        income=Sum("amount", filter=Q(type="INCOME")), expense=Sum("amount", filter=Q(type="EXPENSE")),
        n=Count("id"))
    return {"income": agg["income"] or Decimal("0"), "expense": agg["expense"] or Decimal("0"), "count": agg["n"]}


class HtmxListMixin:
    """Lista com filtros: com HTMX devolve só a tabela (que traz a faixa por fora, via oob)."""
    table_template = None

    def get_template_names(self):
        if getattr(self.request, "htmx", False):
            return [self.table_template]
        return [self.template_name]


class TransactionListView(HtmxListMixin, FilterView):
    model = Transaction
    template_name = "financial/transaction_list.html"
    table_template = "financial/transaction_table.html"
    context_object_name = "object_list"
    filterset_class = TransactionFilter
    paginate_by = 20

    def get_queryset(self):
        return (super().get_queryset().select_related("category", "entity", "payment_method", "on_behalf_of")
                .prefetch_related("tags").order_by("-date", "-created_at"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        first = today.replace(day=1)
        last = first + relativedelta(months=1) - timedelta(days=1)
        prev_first = first - relativedelta(months=1)
        context.update({
            "this_month_start": first.isoformat(), "this_month_end": last.isoformat(),
            "last_month_start": prev_first.isoformat(), "last_month_end": (first - timedelta(days=1)).isoformat(),
            "totals": money_totals(self.object_list),
            "pending_count": Transaction.objects.filter(confirmed=False).count(),
        })
        return context


class TransactionTableMixin(HtmxModalFormMixin):
    model = Transaction
    form_class = TransactionForm
    template_name = "financial/transaction_form.html"
    table_template = "financial/transaction_table.html"
    table_target = "#transaction-table"
    success_url = reverse_lazy("financial:transaction_list")
    event = "transactionSaved"
    success_message = "Transação salva."

    def get_table_queryset(self):
        return Transaction.objects.select_related("category", "entity", "payment_method", "on_behalf_of") \
            .prefetch_related("tags").order_by("-date", "-created_at")

    def get_table_context(self):
        ctx = super().get_table_context()
        ctx["totals"] = money_totals(Transaction.objects.all())
        return ctx


class TransactionCreateView(TransactionTableMixin, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        initial.setdefault("date", timezone.now().date())
        initial.setdefault("type", self.request.GET.get("tipo", "EXPENSE"))
        initial.setdefault("confirmed", True)
        return initial


class TransactionDuplicateView(TransactionTableMixin, CreateView):
    success_message = "Cópia salva."

    def get_initial(self):
        source = get_object_or_404(Transaction, pk=self.kwargs["pk"])
        return {"type": source.type, "description": source.description, "amount": source.amount,
                "date": timezone.now().date(), "category": source.category_id,
                "payment_method": source.payment_method_id, "entity": source.entity_id,
                "on_behalf_of": source.on_behalf_of_id, "notes": source.notes, "confirmed": False,
                "tags": list(source.tags.values_list("pk", flat=True))}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["duplicating"] = True
        return context


class TransactionUpdateView(TransactionTableMixin, UpdateView):
    pass


class TransactionDeleteView(HtmxDeleteMixin, DeleteView):
    model = Transaction
    table_template = "financial/transaction_table.html"
    success_url = reverse_lazy("financial:transaction_list")
    event = "transactionDeleted"
    success_message = "Transação excluída."

    def get_table_queryset(self):
        return TransactionTableMixin.get_table_queryset(self)

    def get_table_context(self):
        ctx = super().get_table_context()
        ctx["totals"] = money_totals(Transaction.objects.all())
        return ctx


# ---------------------------------------------------------------------------
# Recorrências
# ---------------------------------------------------------------------------

class RecurrenceListView(HtmxListMixin, FilterView):
    model = Recurrence
    template_name = "financial/recurrence_list.html"
    table_template = "financial/recurrence_table.html"
    context_object_name = "object_list"
    filterset_class = RecurrenceFilter
    paginate_by = 20

    def get_queryset(self):
        return super().get_queryset().select_related("category", "payment_method", "entity")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active = Recurrence.objects.filter(active=True, frequency="MONTHLY")
        context["monthly_out"] = active.filter(type="EXPENSE").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        context["monthly_in"] = active.filter(type="INCOME").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        context["active_count"] = Recurrence.objects.filter(active=True).count()
        return context


class RecurrenceTableMixin(HtmxModalFormMixin):
    model = Recurrence
    form_class = RecurrenceForm
    template_name = "financial/recurrence_form.html"
    table_template = "financial/recurrence_table.html"
    table_target = "#recurrence-table"
    success_url = reverse_lazy("financial:recurrence_list")
    event = "recurrenceSaved"
    success_message = "Recorrência salva."

    def get_table_queryset(self):
        return Recurrence.objects.select_related("category", "payment_method", "entity")


class RecurrenceCreateView(RecurrenceTableMixin, CreateView):
    def get_initial(self):
        return {"start_date": timezone.now().date(), "type": "EXPENSE", "frequency": "MONTHLY", "active": True}


class RecurrenceUpdateView(RecurrenceTableMixin, UpdateView):
    pass


class RecurrenceDeleteView(HtmxDeleteMixin, DeleteView):
    model = Recurrence
    table_template = "financial/recurrence_table.html"
    success_url = reverse_lazy("financial:recurrence_list")
    success_message = "Recorrência excluída."

    def get_table_queryset(self):
        return RecurrenceTableMixin.get_table_queryset(self)


# ---------------------------------------------------------------------------
# Parcelados
# ---------------------------------------------------------------------------

def purchases_qs():
    return (Purchase.objects.select_related("category", "entity", "payment_method", "on_behalf_of")
            .annotate(paid_count=Count("installments", filter=Q(installments__paid=True)),
                      total_count=Count("installments"),
                      left_amount=Sum("installments__amount", filter=Q(installments__paid=False)))
            .order_by("-purchase_date", "-created_at"))


class PurchaseListView(HtmxListMixin, FilterView):
    model = Purchase
    template_name = "financial/purchase_list.html"
    table_template = "financial/purchase_table.html"
    context_object_name = "object_list"
    filterset_class = PurchaseFilter
    paginate_by = 20

    def get_queryset(self):
        return purchases_qs()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(purchase_stats())
        return context


def purchase_stats():
    today = timezone.now().date()
    unpaid = Installment.objects.filter(paid=False)
    nxt = forecast.add_months(today.year, today.month, 1)
    return {
        "left_total": unpaid.aggregate(t=Sum("amount"))["t"] or Decimal("0"),
        "this_month": unpaid.filter(reference_year=today.year, reference_month=today.month)
        .aggregate(t=Sum("amount"))["t"] or Decimal("0"),
        "next_month": unpaid.filter(reference_year=nxt[0], reference_month=nxt[1])
        .aggregate(t=Sum("amount"))["t"] or Decimal("0"),
        "open_count": Purchase.objects.filter(installments__paid=False).distinct().count(),
    }


class PurchaseDetailView(DetailView):
    model = Purchase
    template_name = "financial/purchase_detail.html"
    context_object_name = "purchase"

    def get_queryset(self):
        return purchases_qs()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        installments = self.object.installments.all().order_by("installment_number")
        context["installments"] = installments
        context["today"] = timezone.now().date()
        context["paid_amount"] = sum((i.amount for i in installments if i.paid), Decimal("0"))
        context["left_count"] = sum(1 for i in installments if not i.paid)
        return context


class PurchaseTableMixin(HtmxModalFormMixin):
    model = Purchase
    form_class = PurchaseForm
    template_name = "financial/purchase_form.html"
    table_template = "financial/purchase_table.html"
    table_target = "#purchase-table"
    success_url = reverse_lazy("financial:purchase_list")
    event = "purchaseSaved"
    success_message = "Parcelado salvo."

    def get_table_queryset(self):
        return purchases_qs()

    def get_table_context(self):
        ctx = super().get_table_context()
        ctx.update(purchase_stats())
        return ctx


class PurchaseCreateView(PurchaseTableMixin, CreateView):
    def get_initial(self):
        return {"purchase_date": timezone.now().date(), "number_of_installments": 2}


class PurchaseUpdateView(PurchaseTableMixin, UpdateView):
    def form_valid(self, form):
        response = super().form_valid(form)
        if "number_of_installments" in form.changed_data or "total_amount" in form.changed_data:
            self.object.generate_installments()
            if getattr(self.request, "htmx", False):
                return self.table_response(self.success_message)
        return response


class PurchaseDeleteView(HtmxDeleteMixin, DeleteView):
    model = Purchase
    table_template = "financial/purchase_table.html"
    success_url = reverse_lazy("financial:purchase_list")
    success_message = "Parcelado excluído."

    def get_table_queryset(self):
        return purchases_qs()

    def get_table_context(self):
        ctx = super().get_table_context()
        ctx.update(purchase_stats())
        return ctx


# ---------------------------------------------------------------------------
# Transferências e pagamentos de fatura
# ---------------------------------------------------------------------------

def transfers_qs():
    return Transfer.objects.select_related("from_account__parent", "to_account__parent", "to_card")


def transfer_stats(qs):
    agg = qs.aggregate(n=Count("id"), total=Sum("amount"),
                       invoices=Sum("amount", filter=Q(to_card__isnull=False)))
    total, invoices = agg["total"] or Decimal("0"), agg["invoices"] or Decimal("0")
    share = int(round(invoices / total * 100)) if total else 0
    return {"count": agg["n"], "total": total, "invoices": invoices, "between_share": 100 - share if total else 0,
            "open_count": Transfer.objects.filter(open_q()).count()}


class TransferListView(HtmxListMixin, FilterView):
    model = Transfer
    template_name = "financial/transfer_list.html"
    table_template = "financial/transfer_table.html"
    context_object_name = "object_list"
    filterset_class = TransferFilter
    paginate_by = 20

    def get_queryset(self):
        return transfers_qs()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stats"] = transfer_stats(self.object_list)
        return context


class TransferTableMixin(HtmxModalFormMixin):
    model = Transfer
    form_class = TransferForm
    template_name = "financial/transfer_form.html"
    table_template = "financial/transfer_table.html"
    table_target = "#transfer-table"
    success_url = reverse_lazy("financial:transfer_list")
    event = "transferSaved"
    success_message = "Transferência salva."

    def get_table_queryset(self):
        return transfers_qs()

    def get_table_context(self):
        ctx = super().get_table_context()
        ctx["stats"] = transfer_stats(Transfer.objects.all())
        return ctx


class TransferCreateView(TransferTableMixin, CreateView):
    def get_initial(self):
        initial = {"date": timezone.now().date()}
        card = self.request.GET.get("cartao")
        if card:
            initial["to_card"] = card
            initial["description"] = "Pagamento de fatura"
        if self.request.GET.get("fatura"):
            initial["invoice"] = self.request.GET["fatura"]
        if self.request.GET.get("valor"):
            initial["amount"] = self.request.GET["valor"]
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        # Pagar a fatura marca as parcelas daquele cartão e mês como pagas (igual ao bot)
        self.object.mark_invoice_paid()
        return response


class TransferUpdateView(TransferTableMixin, UpdateView):
    pass


class TransferDeleteView(HtmxDeleteMixin, DeleteView):
    model = Transfer
    table_template = "financial/transfer_table.html"
    success_url = reverse_lazy("financial:transfer_list")
    success_message = "Transferência excluída."

    def get_table_queryset(self):
        return transfers_qs()

    def get_table_context(self):
        ctx = super().get_table_context()
        ctx["stats"] = transfer_stats(Transfer.objects.all())
        return ctx


# ---------------------------------------------------------------------------
# Faturas
# ---------------------------------------------------------------------------

class InvoiceForecastView(TemplateView):
    template_name = "financial/invoice_forecast.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payment_method_ids = [pid for pid in self.request.GET.getlist("payment_method") if pid]
        month_from = self.request.GET.get("month_from")
        month_to = self.request.GET.get("month_to")

        today = timezone.now().date()
        current = (today.year, today.month)
        unpaid = Installment.objects.filter(paid=False).order_by("reference_year", "reference_month")
        first = unpaid.values_list("reference_year", "reference_month").first()
        last = unpaid.values_list("reference_year", "reference_month").last()

        if month_from:
            range_from = parse_month(month_from, current)
        else:
            range_from = min(first, current) if first else current  # inclui parcelas vencidas e não pagas
        if month_to:
            range_to = parse_month(month_to, forecast.add_months(*current, 2))
        else:
            range_to = max(last, forecast.add_months(*current, 2)) if last else forecast.add_months(*current, 2)

        months_data = forecast.invoice_forecast(range_from, range_to, payment_method_ids or None,
                                                include_items=True, today=today)
        for m in months_data:
            m["key"] = f"{m['year']}-{m['month']:02d}"
            m["is_past"] = (m["year"], m["month"]) < current
            m["is_current"] = (m["year"], m["month"]) == current
            for method in m["methods"]:
                dues = [it["due_date"] for it in method["items"] if it.get("due_date")]
                method["due_date"] = max(dues) if dues else None
                method["late"] = bool(method["due_date"] and method["due_date"] < today)

        biggest = max((m["total"] for m in months_data), default=Decimal("0"))
        grand_total = sum((m["total"] for m in months_data), Decimal("0"))
        this_month_total = next((m["total"] for m in months_data if m["is_current"]), Decimal("0"))
        context.update({
            "months_data": months_data,
            "grand_total": grand_total,
            "biggest_month": biggest,
            "this_month_total": this_month_total,
            "later_share": 100 - (int(round(this_month_total / grand_total * 100)) if grand_total > 0 else 0),
            "next_due": next((meth for m in months_data for meth in m["methods"]
                              if meth["due_date"] and meth["due_date"] >= today), None),
            "payment_methods": PaymentMethod.objects.filter(active=True, type="CREDIT", billing_card__isnull=True),
            "selected_payment_methods": payment_method_ids,
            "selected_month_from": month_from or "",
            "selected_month_to": month_to or "",
            "today": today,
        })
        return context


class CardsView(TemplateView):
    """Cartões principais, os cartões cobrados na mesma fatura e os fechamentos reais."""
    template_name = "financial/cards.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        mains = (PaymentMethod.objects.filter(type="CREDIT", billing_card__isnull=True)
                 .select_related("holder", "bank_account__holder", "lent_to")
                 .prefetch_related("billed_cards__holder").order_by("-active", "name"))
        closings = InvoiceClosing.objects.order_by("-year", "-month")
        by_card = {}
        for c in closings:
            by_card.setdefault(c.card_id, []).append(c)
        paid = forecast.paid_invoices()
        cards = []
        for card in mains:
            rows = by_card.get(card.pk, [])[:6]
            for r in rows:
                r.is_paid = (card.pk, r.year, r.month) in paid
            nxt = forecast.invoice_period_for(card, today) if card.closing_day and card.due_day else None
            cards.append({"card": card, "closings": rows, "next": nxt,
                          "known": len(by_card.get(card.pk, [])), "linked": list(card.billed_cards.all())})
        context.update({
            "cards": cards,
            "main_count": sum(1 for c in cards if c["card"].active),
            "linked_count": PaymentMethod.objects.filter(billing_card__isnull=False, active=True).count(),
            "closings_count": closings.count(),
            "missing_days": sum(1 for c in cards if c["card"].active and not (c["card"].closing_day and c["card"].due_day)),
        })
        return context


class ThirdPartyView(TemplateView):
    """Cartão emprestado: quanto cada pessoa de fora da família gastou, devolveu e deve."""
    template_name = "financial/third_party.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = forecast.third_party_balances(include_items=True)
        for p in data["people"]:
            p["items"] = sorted(p["items"], key=lambda i: (i["month"], str(i["date"])), reverse=True)[:12]
            p["repayments"] = sorted(p["repayments"], key=lambda r: r["date"], reverse=True)[:6]
        context["data"] = data
        context["owed"] = sum((p["balance"] for p in data["people"] if p["balance"] > 0), Decimal("0"))
        context["advanced"] = -sum((p["balance"] for p in data["people"] if p["balance"] < 0), Decimal("0"))
        context["upcoming"] = sum((p["upcoming"] for p in data["people"]), Decimal("0"))
        context["lent_cards"] = PaymentMethod.objects.filter(lent_to__isnull=False).select_related("lent_to")
        charged = sum((p["charged_total"] for p in data["people"]), Decimal("0"))
        repaid = sum((p["repaid"] for p in data["people"]), Decimal("0"))
        context["charged"], context["repaid"] = charged, repaid
        context["open_share"] = max(0, 100 - (int(round(repaid / charged * 100)) if charged > 0 else 0))
        return context


# ---------------------------------------------------------------------------
# Ações rápidas
# ---------------------------------------------------------------------------

@require_http_methods(["POST"])
def toggle_installment_paid(request, pk):
    installment = get_object_or_404(Installment, pk=pk)
    installment.paid = not installment.paid
    installment.save()
    return JsonResponse({"success": True, "paid": installment.paid, "installment_id": installment.pk})


@require_http_methods(["POST"])
def toggle_transaction_confirmed(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk)
    transaction.confirmed = not transaction.confirmed
    transaction.save()
    return JsonResponse({"success": True, "confirmed": transaction.confirmed, "transaction_id": transaction.pk})


@require_http_methods(["POST"])
def generate_recurrences_view(request):
    from financial.services import generate_transactions_for_date

    created = generate_transactions_for_date(timezone.now().date())
    if request.headers.get("HX-Request"):
        msg = f"{created} lançamento(s) gerado(s)." if created else "Nada novo para gerar hoje."
        response = HttpResponse()
        if created:
            response["HX-Refresh"] = "true"
        return hx_trigger(response, None, msg)
    return JsonResponse({"success": True, "created": created})


@require_http_methods(["POST"])
def bulk_toggle_installments_paid(request):
    try:
        ids = json.loads(request.body).get("installment_ids", [])
    except (json.JSONDecodeError, AttributeError):
        ids = request.POST.getlist("installment_ids")
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return JsonResponse({"success": False, "error": "Nenhuma parcela selecionada"}, status=400)
    updated = Installment.objects.filter(pk__in=ids, paid=False).update(paid=True)
    return JsonResponse({"success": True, "updated": updated})


# ---------------------------------------------------------------------------
# Comparativo mensal
# ---------------------------------------------------------------------------

class MonthlyReportView(TemplateView):
    template_name = "financial/monthly_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        fy, fm = parse_month(self.request.GET.get("month_from"),
                             forecast.add_months(today.year, today.month, -5))
        ty, tm = parse_month(self.request.GET.get("month_to"), (today.year, today.month))
        start_date = date(fy, fm, 1)
        end_date = min(forecast.month_end(ty, tm), today) if (ty, tm) == (today.year, today.month) \
            else forecast.month_end(ty, tm)
        if end_date < start_date:
            start_date, end_date = date(ty, tm, 1), forecast.month_end(fy, fm)

        month_keys = []
        cursor = start_date.replace(day=1)
        while cursor <= end_date:
            month_keys.append(f"{cursor.year}-{cursor.month:02d}")
            cursor += relativedelta(months=1)

        # Receitas da família (sem terceiros, sem estornos e devoluções)
        income_qs = (Transaction.objects.filter(type="INCOME", confirmed=True, date__gte=start_date,
                                                date__lte=end_date, on_behalf_of__isnull=True)
                     .exclude(category__name__in=NOT_INCOME)
                     .values("date__year", "date__month", "category__name", "category__color")
                     .annotate(total=Sum("amount")))
        income_categories = OrderedDict()
        income_totals = {mk: Decimal("0") for mk in month_keys}
        for row in income_qs.order_by("category__name"):
            mk = f"{row['date__year']}-{row['date__month']:02d}"
            cat = income_categories.setdefault(row["category__name"], {"color": row["category__color"] or "",
                                                                       "months": {}, "total": Decimal("0")})
            cat["months"][mk] = row["total"]
            cat["total"] += row["total"]
            if mk in income_totals:
                income_totals[mk] += row["total"]

        # Gastos: a mesma conta do bot (despesas + parcelas pelo vencimento − estornos, sem terceiros)
        expense_categories = {}
        expense_totals = {mk: Decimal("0") for mk in month_keys}
        colors = dict(Category.objects.values_list("name", "color"))
        for mk in month_keys:
            y, m = (int(p) for p in mk.split("-"))
            s, e = date(y, m, 1), min(forecast.month_end(y, m), end_date)
            summary = forecast.spending_summary(s, e)
            expense_totals[mk] = summary["total"]
            for r in summary["rows"]:
                cat = expense_categories.setdefault(r["label"], {"color": colors.get(r["label"]) or "",
                                                                 "months": {}, "total": Decimal("0")})
                cat["months"][mk] = r["total"]
                cat["total"] += r["total"]
        expense_categories = OrderedDict(sorted(expense_categories.items(), key=lambda kv: -kv[1]["total"]))

        balance_totals = {mk: income_totals[mk] - expense_totals[mk] for mk in month_keys}
        months_display = []
        for mk in month_keys:
            y, m = (int(p) for p in mk.split("-"))
            months_display.append({"key": mk, "name": MONTH_NAMES[m], "year": y,
                                   "short": f"{MONTH_NAMES[m][:3].lower()}/{y % 100:02d}"})
        n = len(month_keys) or 1
        total_income = sum(income_totals.values(), Decimal("0"))
        total_expense = sum(expense_totals.values(), Decimal("0"))
        kept = max(0, min(100, int((total_income - total_expense) / total_income * 100))) if total_income > 0 else 0
        context.update({
            "month_keys": month_keys, "months_display": months_display,
            "income_categories": income_categories, "expense_categories": expense_categories,
            "income_totals": income_totals, "expense_totals": expense_totals, "balance_totals": balance_totals,
            "avg_income": total_income / n, "avg_expense": total_expense / n,
            "total_balance": total_income - total_expense,
            "kept_share": kept,
            "spent_share": 100 - kept,
            "selected_month_from": start_date.strftime("%Y-%m"), "selected_month_to": end_date.strftime("%Y-%m"),
            "cols": len(month_keys) + 2,
        })
        return context
