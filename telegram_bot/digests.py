"""Avisos automáticos (sem IA): vencimento de fatura, saldo projetado negativo
e resumo mensal. Cada aviso tem uma chave; o comando `send_digests` só envia
chaves ainda não registradas em DigestLog."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from accounts.models import PaymentMethod
from financial import forecast

from .render import brl

INVOICE_SOON_DAYS = 3
MONTHLY_SUMMARY_UNTIL_DAY = 5


@dataclass
class Digest:
    key: str
    text: str


def _due_date(pm, year, month):
    return date(year, month, forecast._clamp_day(year, month, pm.due_day))


def invoice_due_digests(today):
    """Fatura vencendo em até 3 dias (um aviso) e no dia do vencimento (outro)."""
    digests = []
    frm = (today.year, today.month)
    to = forecast.add_months(*frm, 1)
    # Só cartões principais: os adicionais são cobrados na fatura deles
    cards = {pm.pk: pm for pm in PaymentMethod.objects.filter(
        type="CREDIT", active=True, due_day__isnull=False, billing_card__isnull=True)}
    for bucket in forecast.invoice_forecast(frm, to, list(cards) or [0], include_items=False, today=today):
        for method in bucket["methods"]:
            pm = cards.get(method["payment_method_id"])
            if pm is None or method["total"] <= 0:
                continue
            due = _due_date(pm, bucket["year"], bucket["month"])
            days = (due - today).days
            base = f"invoice:{pm.pk}:{bucket['year']}-{bucket['month']:02d}"
            if days == 0:
                digests.append(Digest(f"{base}:today",
                                      f"💳 A fatura do {pm.name} vence hoje ({due:%d/%m}): {brl(method['total'])}."))
            elif 0 < days <= INVOICE_SOON_DAYS:
                when = "amanhã" if days == 1 else f"em {days} dias"
                digests.append(Digest(f"{base}:soon",
                                      f"💳 A fatura do {pm.name} vence {when} ({due:%d/%m}): {brl(method['total'])}."))
    return digests


def negative_balance_digests(today):
    """Saldo disponível projetado negativo neste mês ou no próximo (no máximo um aviso
    por semana). Só faz sentido quando as contas do dia a dia têm saldo de partida."""
    flow = forecast.monthly_cash_flow(1, today=today)
    if not flow["all_anchored"]:
        return []
    for month in flow["months"]:
        if month["projected_end_balance"] < 0:
            week = today.isocalendar()
            text = (
                f"⚠️ Saldo projetado negativo no fim de {month['month_name'].lower()}: "
                f"{brl(month['projected_end_balance'])}.\n"
                f"Disponível hoje {brl(flow['start_balance'])} · receitas previstas {brl(month['expected_income'])} · "
                f"despesas previstas {brl(month['expected_expenses'])} · faturas {brl(month['card_invoices'])}."
            )
            if flow["reserved"] > 0:
                text += f"\nGuardado em caixinhas: {brl(flow['reserved'])}."

            return [Digest(f"negative:{month['year']}-{month['month']:02d}:w{week[0]}-{week[1]:02d}", text)]
    return []


def monthly_summary_digests(today):
    """Nos primeiros dias do mês: resumo do mês anterior e faturas do mês atual."""
    if today.day > MONTHLY_SUMMARY_UNTIL_DAY:
        return []
    py, pm = forecast.add_months(today.year, today.month, -1)
    ppy, ppm = forecast.add_months(today.year, today.month, -2)
    last = forecast.spending_summary(forecast.month_start(py, pm), forecast.month_end(py, pm), "category")
    before = forecast.spending_summary(forecast.month_start(ppy, ppm), forecast.month_end(ppy, ppm), "category")
    if last["total"] <= 0:
        return []

    lines = [f"📊 Resumo de {forecast.MONTH_NAMES[pm].lower()}/{py}", f"Gastos: {brl(last['total'])}"]
    if before["total"] > 0:
        diff = last["total"] - before["total"]
        pct = (diff / before["total"] * 100).quantize(Decimal("1"))
        arrow = "a mais" if diff > 0 else "a menos"
        lines[-1] += f" ({brl(abs(diff))} {arrow} que em {forecast.MONTH_NAMES[ppm].lower()}, {abs(pct)}%)"
    lines.append("")
    lines.append("Maiores categorias:")
    for row in last["rows"][:5]:
        lines.append(f"• {row['label']}: {brl(row['total'])}")

    invoices = forecast.invoice_forecast((today.year, today.month), (today.year, today.month),
                                         include_items=False, today=today)
    if invoices and invoices[0]["total"] > 0:
        lines.append("")
        lines.append(f"Faturas que vencem em {forecast.MONTH_NAMES[today.month].lower()}: {brl(invoices[0]['total'])}")
        for method in invoices[0]["methods"]:
            lines.append(f"• {method['payment_method']}: {brl(method['total'])}")
    return [Digest(f"monthly:{py}-{pm:02d}", "\n".join(lines))]


def build_digests(today=None):
    today = today or date.today()
    return [*invoice_due_digests(today), *negative_balance_digests(today), *monthly_summary_digests(today)]


