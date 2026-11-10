from datetime import date
from decimal import Decimal
from typing import Literal

from django.db.models import Q
from pydantic import Field

from financial import forecast
from financial.models import Installment, Transaction

from .registry import Tool, ToolError, ToolInput, parse_month


class QueryTransactionsInput(ToolInput):
    start_date: date = Field(description="Data inicial (inclusive).")
    end_date: date = Field(description="Data final (inclusive).")
    type: Literal["EXPENSE", "INCOME"] | None = Field(default=None, description="Filtra por tipo.")
    category_ids: list[int] | None = Field(default=None, description="IDs de categoria.")
    payment_method_ids: list[int] | None = Field(default=None, description="IDs de método de pagamento.")
    text: str | None = Field(default=None, description="Trecho da descrição ou nome da entidade.")
    include_installments: bool = Field(
        default=True, description="Incluir parcelas de compras parceladas (pelo vencimento)."
    )
    limit: int = Field(default=50, description="Máximo de itens listados (os totais consideram tudo).")


def query_transactions(args, ctx):
    if args.end_date < args.start_date:
        raise ToolError("end_date anterior a start_date.")
    limit = max(1, min(args.limit, 200))

    tx_qs = Transaction.objects.filter(date__gte=args.start_date, date__lte=args.end_date).select_related(
        "category", "payment_method", "entity")
    if args.type:
        tx_qs = tx_qs.filter(type=args.type)
    if args.category_ids:
        tx_qs = tx_qs.filter(category_id__in=args.category_ids)
    if args.payment_method_ids:
        tx_qs = tx_qs.filter(payment_method_id__in=args.payment_method_ids)
    if args.text:
        tx_qs = tx_qs.filter(Q(description__icontains=args.text) | Q(entity__name__icontains=args.text))

    items = []
    totals = {"income": Decimal("0"), "expense": Decimal("0"), "installments": Decimal("0"),
              "unconfirmed": Decimal("0")}
    for tx in tx_qs.order_by("-date"):
        key = "income" if tx.type == "INCOME" else "expense"
        totals[key] += tx.amount
        if not tx.confirmed:
            totals["unconfirmed"] += tx.amount
        items.append({
            "kind": "transaction", "id": tx.id, "type": tx.type, "date": tx.date,
            "description": tx.description, "amount": tx.amount,
            "category": tx.category.name, "payment_method": tx.payment_method.name,
            "entity": tx.entity.name if tx.entity else None, "confirmed": tx.confirmed,
        })

    if args.include_installments and args.type != "INCOME":
        inst_qs = Installment.objects.filter(
            due_date__gte=args.start_date, due_date__lte=args.end_date
        ).select_related("purchase__category", "purchase__payment_method", "purchase__entity")
        if args.category_ids:
            inst_qs = inst_qs.filter(purchase__category_id__in=args.category_ids)
        if args.payment_method_ids:
            inst_qs = inst_qs.filter(purchase__payment_method_id__in=args.payment_method_ids)
        if args.text:
            inst_qs = inst_qs.filter(Q(purchase__description__icontains=args.text)
                                     | Q(purchase__entity__name__icontains=args.text))
        for inst in inst_qs.order_by("-due_date"):
            totals["installments"] += inst.amount
            p = inst.purchase
            items.append({
                "kind": "installment", "id": inst.id, "type": "EXPENSE", "date": inst.due_date,
                "description": f"{p.description} ({inst.installment_number}/{p.number_of_installments})",
                "amount": inst.amount, "category": p.category.name, "payment_method": p.payment_method.name,
                "entity": p.entity.name if p.entity else None, "paid": inst.paid,
            })

    items.sort(key=lambda i: i["date"], reverse=True)
    return {"count": len(items), "totals": totals, "items": items[:limit],
            "truncated": len(items) > limit}


class SpendingSummaryInput(ToolInput):
    start_date: date
    end_date: date
    group_by: Literal["category", "payment_method", "entity", "month"] = "category"
    include_unconfirmed: bool = Field(default=False, description="Incluir despesas não confirmadas (previstas).")
    category_ids: list[int] | None = None
    payment_method_ids: list[int] | None = None


def spending_summary(args, ctx):
    if args.end_date < args.start_date:
        raise ToolError("end_date anterior a start_date.")
    return forecast.spending_summary(
        args.start_date, args.end_date, group_by=args.group_by,
        include_unconfirmed=args.include_unconfirmed,
        payment_method_ids=args.payment_method_ids, category_ids=args.category_ids,
    )


class InvoiceForecastInput(ToolInput):
    month_from: str | None = Field(default=None, description="Mês de vencimento inicial, AAAA-MM. Padrão: mês atual.")
    month_to: str | None = Field(default=None, description="Mês de vencimento final, AAAA-MM. Padrão: +5 meses.")
    payment_method_ids: list[int] | None = Field(default=None, description="Restringe a estes cartões/métodos.")
    include_items: bool = Field(default=False, description="Listar cada parcela/compra (resposta maior).")
    include_paid: bool = Field(
        default=False,
        description="true = composição completa da fatura, inclusive o que já foi pago (use para meses passados).",
    )


def get_invoice_forecast(args, ctx):
    month_from = parse_month(args.month_from) if args.month_from else None
    month_to = parse_month(args.month_to) if args.month_to else None
    months = forecast.invoice_forecast(month_from, month_to, args.payment_method_ids,
                                       include_items=args.include_items, include_paid=args.include_paid)
    return {"months": months, "note": "Mês = mês de vencimento da fatura. Inclui parcelas, compras à vista "
                                      "no crédito (menos estornos) e recorrências no cartão. Sem include_paid, "
                                      "só o que falta pagar."}


class AccountBalancesInput(ToolInput):
    as_of: date | None = Field(default=None, description="Data do saldo. Padrão: hoje.")


def get_account_balances(args, ctx):
    data = forecast.account_balances(args.as_of)
    data["note"] = ("available = dinheiro do dia a dia (contas); reserved = guardado em caixinhas/cofrinhos e "
                    "investimentos (reserve=true). anchor = ponto de partida do cálculo (saldo informado, extrato "
                    "ou saldo inicial). Conta com anchor null não tem saldo de partida: o valor é só a soma dos "
                    "lançamentos registrados; peça ao usuário o saldo atual dela para registrar. Caixinha sem saldo "
                    "informado aparece com balance null (em reserved_unknown) e fica fora dos totais.")
    return data


class CashFlowInput(ToolInput):
    months_ahead: int = Field(default=3, description="Quantos meses à frente, além do mês atual (0 a 12).")


def get_cash_flow_forecast(args, ctx):
    data = forecast.monthly_cash_flow(max(0, min(args.months_ahead, 12)))
    data["note"] = ("Saldo projetado = saldo disponível nas contas (sem caixinhas) + receitas previstas - despesas "
                    "previstas - faturas de cartão a vencer. `reserved` é o que está guardado em caixinhas e pode "
                    "cobrir um mês negativo. Previsto = lançamentos não confirmados e recorrências ativas. "
                    "Se all_anchored for false, o saldo inicial é incompleto: avise o usuário.")
    return data


TOOLS = [
    Tool(
        name="query_transactions",
        description=(
            "Lista lançamentos de um período com totais: transações (receitas e despesas) e, "
            "opcionalmente, parcelas de compras parceladas pelo vencimento. Use para perguntas "
            "como 'quanto gastei no iFood em outubro' ou para conferir se algo já foi registrado."
        ),
        input_model=QueryTransactionsInput,
        handler=query_transactions,
    ),
    Tool(
        name="spending_summary",
        description=(
            "Total de gastos do período agrupado por categoria, método de pagamento, entidade ou "
            "mês. Despesas pela data e parcelas pelo vencimento; estornos são descontados."
        ),
        input_model=SpendingSummaryInput,
        handler=spending_summary,
    ),
    Tool(
        name="get_invoice_forecast",
        description=(
            "Previsão das faturas de cartão por mês de vencimento e por cartão: parcelas a pagar, "
            "compras à vista no crédito e recorrências cobradas no cartão."
        ),
        input_model=InvoiceForecastInput,
        handler=get_invoice_forecast,
    ),
    Tool(
        name="get_account_balances",
        description=(
            "Saldo atual (ou em uma data) de cada conta e de cada caixinha/cofrinho, com os totais disponível "
            "e guardado. Calculado a partir do último saldo informado/extrato mais os lançamentos posteriores; "
            "cartão de crédito não entra."
        ),
        input_model=AccountBalancesInput,
        handler=get_account_balances,
    ),
    Tool(
        name="get_cash_flow_forecast",
        description=(
            "Projeção mês a mês do saldo das contas: receitas previstas, despesas previstas, faturas de "
            "cartão a vencer e saldo projetado no fim de cada mês. Use para 'vai sobrar dinheiro?', "
            "'qual meu saldo previsto em janeiro?'."
        ),
        input_model=CashFlowInput,
        handler=get_cash_flow_forecast,
    ),
]
