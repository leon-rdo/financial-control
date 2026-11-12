import json
from decimal import Decimal

import requests
from django.db.models import Count, F
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView
from django_filters.views import FilterView

from core.mixins import HtmxDeleteMixin, HtmxModalFormMixin
from financial import forecast

from .filters import BankAccountFilter, PaymentMethodFilter
from .forms import BalanceSnapshotForm, BankAccountForm, PaymentMethodForm, SimplePaymentMethodForm
from .models import BalanceSnapshot, BankAccount, PaymentMethod


# ---------------------------------------------------------------------------
# Contas e caixinhas
# ---------------------------------------------------------------------------

def accounts_qs():
    """Contas-mãe primeiro, cada uma seguida das suas caixinhas."""
    return (BankAccount.objects.select_related("parent", "holder", "parent__holder")
            .annotate(group=Coalesce("parent__name", "name"))
            .order_by("-active", "group", F("parent").asc(nulls_first=True), "name"))


def account_table_context(object_list):
    today = timezone.now().date()
    balances = forecast.account_balances(today)
    by_id = {a["account_id"]: a for a in balances["accounts"]}
    last = {}
    for snap in BalanceSnapshot.objects.order_by("account_id", "-date"):
        last.setdefault(snap.account_id, snap)
    rows = []
    for acct in object_list:
        info = by_id.get(acct.pk)
        rows.append({"account": acct, "info": info, "snapshot": last.get(acct.pk),
                     "stale": bool(info and info["anchor_date"] and (today - info["anchor_date"]).days > 45)})
    return {"rows": rows, "balances": balances, "today": today}


class BankAccountListView(FilterView):
    model = BankAccount
    template_name = "accounts/bankaccount_list.html"
    context_object_name = "object_list"
    filterset_class = BankAccountFilter

    def get_queryset(self):
        return accounts_qs()

    def get_template_names(self):
        if self.request.htmx:
            return ["accounts/bankaccount_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(account_table_context(context["object_list"]))
        return context


class BankAccountTableMixin(HtmxModalFormMixin):
    model = BankAccount
    form_class = BankAccountForm
    template_name = "accounts/bankaccount_form.html"
    table_template = "accounts/bankaccount_table.html"
    table_target = "#bankaccount-table"
    success_url = reverse_lazy("accounts:bankaccount_list")
    event = "bankAccountSaved"
    success_message = "Conta salva."

    def get_table_context(self):
        objects = accounts_qs()
        return {"object_list": objects, **account_table_context(objects)}


class BankAccountCreateView(BankAccountTableMixin, CreateView):
    def get_initial(self):
        initial = {"active": True}
        if self.request.GET.get("dentro_de"):
            initial["parent"] = self.request.GET["dentro_de"]
            initial["type"] = BankAccount.TypeChoices.SAVINGS
        return initial


class BankAccountUpdateView(BankAccountTableMixin, UpdateView):
    pass


class BankAccountDeleteView(HtmxDeleteMixin, BankAccountTableMixin, DeleteView):
    success_message = "Conta excluída."
    protected_message = "Não dá para excluir: a conta tem lançamentos, caixinhas ou formas de pagamento. Desative-a."


class BalanceSnapshotCreateView(BankAccountTableMixin, CreateView):
    """Informar o saldo de uma conta ou caixinha (substitui o do mesmo dia)."""
    model = BalanceSnapshot
    form_class = BalanceSnapshotForm
    template_name = "accounts/snapshot_form.html"
    success_message = "Saldo informado."

    def get_initial(self):
        initial = {"date": timezone.now().date()}
        acct = self.request.GET.get("conta")
        if acct:
            initial["account"] = acct
            info = next((a for a in forecast.account_balances()["accounts"] if str(a["account_id"]) == acct), None)
            if info and info["balance"] is not None:
                initial["balance"] = info["balance"]
        return initial

    def form_valid(self, form):
        data = form.cleaned_data
        BalanceSnapshot.objects.update_or_create(
            account=data["account"], date=data["date"],
            defaults={"balance": data["balance"], "notes": data.get("notes", ""),
                      "source": BalanceSnapshot.SourceChoices.MANUAL})
        if getattr(self.request, "htmx", False):
            return self.table_response(self.success_message)
        return HttpResponseRedirect(self.success_url)


class SnapshotHistoryView(DetailView):
    """Saldos informados de uma conta (modal)."""
    model = BankAccount
    template_name = "accounts/snapshot_history.html"
    context_object_name = "account"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["snapshots"] = self.object.balance_snapshots.order_by("-date")[:24]
        return context


class BalanceSnapshotDeleteView(HtmxDeleteMixin, DeleteView):
    """Remove um saldo informado; a página recarrega com os saldos recalculados."""
    model = BalanceSnapshot
    success_url = reverse_lazy("accounts:bankaccount_list")
    success_message = "Saldo removido."


# ---------------------------------------------------------------------------
# Formas de pagamento
# ---------------------------------------------------------------------------

def payment_methods_qs():
    return (PaymentMethod.objects.select_related("bank_account", "holder", "billing_card", "lent_to",
                                                 "bank_account__holder", "billing_card__holder")
            .annotate(linked=Count("billed_cards"))
            .order_by("-active", "type", Coalesce("billing_card__name", "name"),
                      F("billing_card").asc(nulls_first=True), "name"))


class PaymentMethodListView(FilterView):
    model = PaymentMethod
    template_name = "accounts/paymentmethod_list.html"
    context_object_name = "object_list"
    filterset_class = PaymentMethodFilter
    paginate_by = 20

    def get_queryset(self):
        return payment_methods_qs()

    def get_template_names(self):
        if self.request.htmx:
            return ["accounts/paymentmethod_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active = PaymentMethod.objects.filter(active=True)
        context["counts"] = {
            "cards": active.filter(type="CREDIT", billing_card__isnull=True).count(),
            "linked": active.filter(billing_card__isnull=False).count(),
            "others": active.exclude(type="CREDIT").count(),
            "limit": active.filter(type="CREDIT").exclude(credit_limit=None)
            .values_list("credit_limit", flat=True),
        }
        context["counts"]["limit"] = sum(context["counts"]["limit"], Decimal("0"))
        return context


class PaymentMethodTableMixin(HtmxModalFormMixin):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "accounts/paymentmethod_form.html"
    table_template = "accounts/paymentmethod_table.html"
    table_target = "#paymentmethod-table"
    success_url = reverse_lazy("accounts:paymentmethod_list")
    event = "paymentMethodSaved"
    success_message = "Forma de pagamento salva."

    def get_table_queryset(self):
        return payment_methods_qs()


class PaymentMethodCreateView(PaymentMethodTableMixin, CreateView):
    def get_initial(self):
        return {"active": True, "type": self.request.GET.get("tipo", "CREDIT")}

    def dispatch(self, request, *args, **kwargs):
        if request.GET.get("inline") and request.method == "POST":
            return self.create_inline(request)
        return super().dispatch(request, *args, **kwargs)

    def create_inline(self, request):
        try:
            form = SimplePaymentMethodForm(json.loads(request.body))
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "Dados inválidos"}, status=400)
        if form.is_valid():
            obj = form.save()
            return JsonResponse({"success": True, "object": {"id": obj.pk, "name": str(obj), "type": obj.type}})
        return JsonResponse({"success": False, "error": "Confira o nome e o tipo.", "errors": form.errors},
                            status=400)


class PaymentMethodUpdateView(PaymentMethodTableMixin, UpdateView):
    pass


class PaymentMethodDeleteView(HtmxDeleteMixin, PaymentMethodTableMixin, DeleteView):
    success_message = "Forma de pagamento excluída."
    protected_message = "Não dá para excluir: há lançamentos ou cartões ligados a ela. Desative-a."


# ---------------------------------------------------------------------------
# API de bancos
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def fetch_banks(request):
    """Lista de bancos da BrasilAPI."""
    try:
        response = requests.get("https://brasilapi.com.br/api/banks/v1", timeout=10)
        if response.status_code != 200:
            return JsonResponse({"error": "Não deu para carregar a lista de bancos. Tente de novo."}, status=500)
        banks = []
        for bank in response.json():
            code, full_name, name = bank.get("code"), bank.get("fullName", ""), bank.get("name", "")
            banks.append({"name": name, "bank": f"{code} - {full_name}" if code else full_name})
        banks.sort(key=lambda x: x["name"])
        return JsonResponse({"success": True, "banks": banks})
    except requests.Timeout:
        return JsonResponse({"error": "A lista de bancos demorou demais. Tente de novo."}, status=500)
    except requests.RequestException:
        return JsonResponse({"error": "Não deu para consultar a lista de bancos agora."}, status=500)

