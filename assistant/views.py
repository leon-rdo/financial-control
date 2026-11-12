from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from core.mixins import HtmxDeleteMixin, HtmxModalFormMixin, hx_trigger
from core.templatetags.ui import rs
from financial.forecast import add_months

from accounts.models import BankAccount, PaymentMethod

from . import batch_service, costs
from .forms import UserRuleForm
from .models import ImportBatch, StagedEntry, UserRule
from .tools.rules import MAX_RULES


# ---------------------------------------------------------------------------
# Lotes do bot (só leitura: confirmar, descartar e desfazer continuam no Telegram)
# ---------------------------------------------------------------------------

def batches_qs():
    return (ImportBatch.objects.select_related("payment_method")
            .annotate(n_entries=Count("entries"),
                      n_new=Count("entries", filter=Q(entries__include=True, entries__match_status="new")),
                      n_dup=Count("entries", filter=Q(entries__match_status="duplicate")),
                      total=Sum("entries__amount", filter=Q(entries__include=True)))
            .order_by("-created_at"))


class BatchListView(ListView):
    model = ImportBatch
    template_name = "assistant/batch_list.html"
    context_object_name = "object_list"
    paginate_by = 20

    def get_queryset(self):
        qs = batches_qs()
        status, kind = self.request.GET.get("status"), self.request.GET.get("tipo")
        if status in ImportBatch.Status.values:
            qs = qs.filter(status=status)
        if kind in ImportBatch.Kind.values:
            qs = qs.filter(kind=kind)
        return qs

    def get_template_names(self):
        if self.request.htmx:
            return ["assistant/batch_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month_start = timezone.now().date().replace(day=1)
        recent = ImportBatch.objects.filter(created_at__date__gte=month_start)
        context.update({
            "statuses": ImportBatch.Status.choices, "kinds": ImportBatch.Kind.choices,
            "selected_status": self.request.GET.get("status", ""), "selected_kind": self.request.GET.get("tipo", ""),
            "month_confirmed": recent.filter(status=ImportBatch.Status.CONFIRMED).count(),
            "month_undone": recent.filter(status=ImportBatch.Status.UNDONE).count(),
            "waiting": ImportBatch.objects.filter(status=ImportBatch.Status.STAGED).count(),
        })
        return context


def last_confirmed(batch):
    """Só o último lote confirmado de cada chat pode ser desfeito (a mesma regra do /desfazer):
    lotes seguintes podem ter reconhecido como "já registrado" o que este gravou."""
    return (ImportBatch.objects.filter(chat_id=batch.chat_id, status=ImportBatch.Status.CONFIRMED)
            .order_by("-committed_at").first())


def batch_checks(batch, totals):
    """Conferências do resumo do bot, em linhas: (ok, texto)."""
    checks = []
    if "invoice_difference" in totals:
        diff = totals["invoice_difference"]
        ok = abs(diff) < Decimal("0.01")
        checks.append((ok, f"Total da fatura {rs(batch.invoice_total)}, soma dos itens "
                           f"{rs(totals['invoice_items_sum'])}" + ("" if ok else f": diferença de {rs(diff)}")))
    for name, amount in (totals.get("by_card") or {}).items():
        checks.append((None, f"Subtotal {name}: {rs(amount)}"))
    if "statement_difference" in totals:
        diff = totals["statement_difference"]
        ok = abs(diff) < Decimal("0.01")
        checks.append((ok, f"Extrato: saldo inicial {rs(batch.opening_balance)} mais os itens dá o final "
                           f"{rs(batch.balance_amount)}" + ("" if ok else f": diferença de {rs(diff)}")))
    if totals["weak"]:
        checks.append((False, f"{totals['weak']} possível(is) duplicado(s): confira os itens marcados"))
    if totals["missing_payment_method"]:
        positions = ", ".join(str(p) for p in totals["missing_payment_method"])
        checks.append((False, f"Itens sem forma de pagamento: {positions}"))
    for warning in batch.warnings or []:
        checks.append((False, warning))
    return checks


def batch_plans(batch):
    """O que mais acontece ao confirmar, além de gravar os itens."""
    plans = []
    spec = batch.new_payment_method or {}
    if spec and not batch.payment_method_id:
        plans.append(f"Cadastra o cartão {spec.get('name', '?')}"
                     + (f" e a conta {spec['new_bank_account_name']}" if spec.get("new_bank_account_name") else ""))
    if batch.additional_new_cards:
        plans.append("Cadastra os outros cartões desta fatura: "
                     + ", ".join(c.get("name", "?") for c in batch.additional_new_cards))
    if batch.link_cards:
        names = ", ".join(PaymentMethod.objects.filter(pk__in=batch.link_cards).values_list("name", flat=True))
        main = batch.payment_method.name if batch.payment_method_id else "o cartão principal"
        plans.append(f"Liga à fatura de {main}: {names}")
    pots = sorted({n for e in batch.entries.all() for n in (e.from_account_name, e.to_account_name) if n}
                  | {b["account_name"] for b in batch.other_balances or [] if b.get("account_name")})
    if pots:
        plans.append("Cria as caixinhas que ainda não existem: " + ", ".join(pots))
    labels = {"closing_day": "fechamento dia", "due_day": "vencimento dia"}
    updates = batch_service.planned_card_updates(batch)
    if updates:
        plans.append("Salva no cartão: " + " e ".join(f"{labels[k]} {v}" for k, v in updates.items()))
    if batch.balance_account_id and batch.balance_amount is not None and batch.balance_date:
        plans.append(f"Registra o saldo de {batch.balance_account.name} em {batch.balance_date:%d/%m/%Y}: "
                     f"{rs(batch.balance_amount)}")
    for item in batch.other_balances or []:
        name = item.get("account_name") or getattr(BankAccount.objects.filter(pk=item.get("account_id")).first(),
                                                   "name", "?")
        plans.append(f"Registra o saldo de {name}: {rs(Decimal(str(item['amount'])))}")
    if batch.invoice_closing_date or batch.invoice_due_date:
        plans.append("Guarda o fechamento real desta fatura")
    return plans


class BatchDetailView(DetailView):
    model = ImportBatch
    template_name = "assistant/batch_detail.html"
    context_object_name = "batch"

    def get_queryset(self):
        return batches_qs().select_related("balance_account", "payment_method__billing_card")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch = self.object
        context["entries"] = (batch.entries.select_related("category", "payment_method", "on_behalf_of")
                              .order_by("position"))
        totals = batch_service.batch_totals(batch)
        context["totals"] = totals
        context["included_total"] = batch.entries.filter(include=True).aggregate(t=Sum("amount"))["t"] \
            or Decimal("0")
        if batch.status == ImportBatch.Status.STAGED:
            context["checks"] = batch_checks(batch, totals)
            context["checks_ok"] = all(ok is not False for ok, _text in context["checks"])
            context["plans"] = batch_plans(batch)
        if batch.status == ImportBatch.Status.CONFIRMED:
            latest = last_confirmed(batch)
            context["can_undo"] = latest is not None and latest.pk == batch.pk
            context["latest_confirmed"] = latest
        return context


def tell_bot(batch, chat_text, note):
    """Mantém o chat em dia com o que foi feito pelo site: troca o resumo do lote
    (para os botões antigos não confundirem) e avisa o assistente."""
    if not batch.chat_id:
        return
    from assistant import agent

    agent.add_note(batch.chat_id, note)
    if settings.TELEGRAM_BOT_TOKEN and batch.telegram_message_id:
        from telegram_bot import client

        client.edit_message(batch.chat_id, batch.telegram_message_id, chat_text)


@require_http_methods(["POST"])
def batch_action(request, pk, action):
    """Confirmar, descartar ou desfazer um lote pelo site, pelas mesmas funções do bot."""
    batch = get_object_or_404(ImportBatch, pk=pk)
    try:
        version = int(request.POST.get("version", ""))
    except ValueError:
        version = None

    if action == "confirmar":
        if version is None:
            messages.error(request, "Recarregue a página e tente de novo.")
        else:
            result = batch_service.commit(batch.pk, version)
            if result.ok:
                messages.success(request, f"Lote confirmado: {result.message}")
                tell_bot(batch, f"✅ Lote #{batch.pk} confirmado pelo site.\n{result.message}\nPara desfazer: /desfazer",
                         f"O usuário confirmou o lote #{batch.pk} pelo site: {result.message}")
            else:
                messages.error(request, result.message)
    elif action == "descartar":
        if batch_service.discard(batch.pk, version):
            messages.success(request, "Lote descartado. Nada foi gravado.")
            tell_bot(batch, f"❌ Lote #{batch.pk} descartado pelo site.",
                     f"O usuário descartou o lote #{batch.pk} pelo site.")
        else:
            messages.error(request, "Este lote já foi processado ou mudou depois que a página abriu. Recarregue.")
    elif action == "desfazer":
        latest = last_confirmed(batch)
        if batch.status != ImportBatch.Status.CONFIRMED:
            messages.error(request, "Só dá para desfazer um lote confirmado.")
        elif latest is None or latest.pk != batch.pk:
            messages.error(request, "Só o último lote confirmado deste chat pode ser desfeito, como no /desfazer.")
        else:
            result = batch_service.undo(batch.pk)
            if result.ok:
                messages.success(request, result.message)
                if batch.chat_id:
                    from assistant import agent

                    agent.add_note(batch.chat_id, f"O usuário desfez o lote #{batch.pk} pelo site (registros removidos).")
            else:
                messages.error(request, result.message)
    else:
        raise Http404
    return redirect("assistant:batch_detail", pk=batch.pk)


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------

def rules_context():
    return {"object_list": UserRule.objects.order_by("-active", "id"),
            "active_count": UserRule.objects.filter(active=True).count(), "max_rules": MAX_RULES}


class RuleListView(TemplateView):
    template_name = "assistant/rule_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(rules_context())
        return context


class RuleTableMixin(HtmxModalFormMixin):
    model = UserRule
    form_class = UserRuleForm
    template_name = "assistant/rule_form.html"
    table_template = "assistant/rule_table.html"
    table_target = "#rule-table"
    success_url = reverse_lazy("assistant:rule_list")
    success_message = "Regra salva. O bot usa a partir da próxima mensagem."

    def get_table_context(self):
        return rules_context()


class RuleCreateView(RuleTableMixin, CreateView):
    def get_initial(self):
        return {"active": True}


class RuleUpdateView(RuleTableMixin, UpdateView):
    pass


class RuleDeleteView(HtmxDeleteMixin, RuleTableMixin, DeleteView):
    success_message = "Regra excluída."


@require_http_methods(["POST"])
def rule_toggle(request, pk):
    rule = get_object_or_404(UserRule, pk=pk)
    if not rule.active and UserRule.objects.filter(active=True).count() >= MAX_RULES:
        response = HttpResponse(status=409)
        response["HX-Reswap"] = "none"
        return hx_trigger(response, None, f"Já há {MAX_RULES} regras ativas. Desative alguma antes.", "error")
    rule.active = not rule.active
    rule.save(update_fields=["active"])

    html = render_to_string("assistant/rule_table.html", rules_context(), request=request)
    return hx_trigger(HttpResponse(html), None, "Regra ativada." if rule.active else "Regra desativada.")


# ---------------------------------------------------------------------------
# Gasto com IA (o mesmo cálculo do /custo do bot)
# ---------------------------------------------------------------------------

class CostView(TemplateView):
    template_name = "assistant/cost.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        spend = costs.month_spend(today)
        history = []
        for i in range(5, -1, -1):
            y, m = add_months(today.year, today.month, -i)
            s = spend if i == 0 else costs.month_spend(date(y, m, 1))
            history.append({"year": y, "month": m, "total": s["total"], "chat": s["chat"],
                            "documents": s["documents"], "calls": s["calls"], "current": i == 0})
        budget, limit = spend["budget"] or Decimal("0"), spend["limit"] or Decimal("0")
        top = max([h["total"] for h in history] + [budget], default=Decimal("0"))
        context.update({
            "spend": spend, "history": history, "history_top": top,
            "by_model": sorted(spend["by_model"].items(), key=lambda kv: -kv[1]),
            "budget": budget, "limit": limit,
            "budget_share": int(spend["total"] / budget * 100) if budget else None,
            "limit_share": int(spend["total"] / limit * 100) if limit else None,
            "over_limit": bool(limit) and spend["total"] >= limit,
            "provider": getattr(settings, "AI_PROVIDER", ""),
        })
        return context
