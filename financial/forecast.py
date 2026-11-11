"""Cálculos de previsão e resumo financeiro (funções puras sobre o ORM).

Usado pelo assistente de IA e, futuramente, pelas views, para que web e bot
mostrem os mesmos números.

Convenção: o "mês de referência" de uma fatura é o mês do seu **vencimento**.
"""

import calendar
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Q, Sum

MONTH_NAMES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

REFUND_CATEGORY_NAME = "Estornos"
# Receita marcada com `on_behalf_of`: a pessoa devolvendo o que gastou no cartão emprestado
REPAYMENT_CATEGORY_NAME = "Devoluções de terceiros"
NO_HOLDER_LABEL = "Sem titular"


@dataclass(frozen=True)
class InvoicePeriod:
    year: int
    month: int
    due_date: date


def _clamp_day(year, month, day):
    return min(day, calendar.monthrange(year, month)[1])


def month_start(year, month):
    return date(year, month, 1)


def month_end(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def add_months(year, month, n):
    d = date(year, month, 1) + relativedelta(months=n)
    return d.year, d.month


def invoice_card(payment_method):
    """Cartão principal da fatura (adicionais/virtuais são cobrados na fatura dele)."""
    return getattr(payment_method, "billing_card", None) or payment_method


def card_family_ids(payment_method):
    """IDs de todos os cartões cobrados na mesma fatura deste cartão."""
    from accounts.models import PaymentMethod

    root = invoice_card(payment_method)
    return [root.pk, *PaymentMethod.objects.filter(billing_card=root).values_list("pk", flat=True)]


def family_q(prefix, ids):
    """Filtro: método em `ids` ou cartão cobrado na fatura de um cartão em `ids`."""
    return Q(**{f"{prefix}_id__in": ids}) | Q(**{f"{prefix}__billing_card_id__in": ids})


def load_closings(card_ids=None):
    """Fechamentos reais conhecidos: {cartão principal: {(ano, mês de vencimento): (fechamento, vencimento)}}."""
    from .models import InvoiceClosing

    qs = InvoiceClosing.objects.all()
    if card_ids is not None:
        qs = qs.filter(card_id__in=card_ids)
    result = {}
    for card_id, year, month, closing, due in qs.values_list("card_id", "year", "month", "closing_date", "due_date"):
        result.setdefault(card_id, {})[(year, month)] = (closing, due)
    return result


def _known_closings(card, closings):
    if closings is not None:
        return closings.get(card.pk, {})
    if not getattr(card, "pk", None):
        return {}
    return load_closings([card.pk]).get(card.pk, {})


def invoice_period_for(payment_method, d, closings=None):
    """Em qual fatura (mês de vencimento) cai uma compra feita na data `d`.

    `closings` (de `load_closings`) evita uma consulta por chamada em laços; sem
    ele, os fechamentos reais do cartão são buscados na hora.

    Estimativa: pelo `closing_day` do cartão. Onde há fechamento REAL conhecido
    (fatura já importada), ele vale mais: a compra vai para a fatura cujo
    fechamento ela ainda não passou, e a anterior já fechou.

    - Cartão com `closing_day`: compra no dia do fechamento ou depois vai para a
      fatura seguinte. O vencimento é `due_day` no mês do fechamento (se
      due_day > closing_day) ou no mês seguinte; sem `due_day`, fechamento + 7 dias.
    - Sem `closing_day` (ou não é cartão): reproduz o comportamento antigo do
      app: referência = mês da própria data, vencimento = a própria data.
    """
    card = invoice_card(payment_method)  # fechamento e vencimento são os da fatura
    closing_day = getattr(card, "closing_day", None)
    is_credit = getattr(payment_method, "type", None) == "CREDIT"
    known = _known_closings(card, closings) if is_credit else {}
    if not is_credit or not (closing_day or known):
        return InvoicePeriod(d.year, d.month, d)
    if not closing_day:
        # Sem dia de fechamento cadastrado, mas com faturas importadas: parte do mês da compra
        closing_day = next(iter(known.values()))[0].day

    closing_this_month = date(d.year, d.month, _clamp_day(d.year, d.month, closing_day))
    if d >= closing_this_month:
        cy, cm = add_months(d.year, d.month, 1)
    else:
        cy, cm = d.year, d.month
    closing_date = date(cy, cm, _clamp_day(cy, cm, closing_day))

    due_day = getattr(card, "due_day", None)
    if due_day:
        if due_day > closing_day:
            dy, dm = cy, cm
        else:
            dy, dm = add_months(cy, cm, 1)
        due_date = date(dy, dm, _clamp_day(dy, dm, due_day))
    else:
        due_date = closing_date + timedelta(days=7)
    year, month = due_date.year, due_date.month
    if known:
        moved = False
        for _ in range(3):  # a estimativa erra no máximo uma fatura; 3 é folga
            previous = known.get(add_months(year, month, -1))
            current = known.get((year, month))
            if previous and d < previous[0]:
                year, month = add_months(year, month, -1)
            elif current and d >= current[0]:
                year, month = add_months(year, month, 1)
            else:
                break
            moved = True
        real_due = known.get((year, month), (None, None))[1]
        if real_due:
            due_date = real_due
        elif moved:
            day = getattr(card, "due_day", None) or due_date.day
            due_date = date(year, month, _clamp_day(year, month, day))
    return InvoicePeriod(due_date.year, due_date.month, due_date)


def transaction_invoice_period(tx, closings=None):
    """Fatura de uma compra à vista no cartão: a fatura em que ela realmente veio
    (`invoice_month`, gravado ao importar a fatura) ou, se não se sabe, a calculada
    pelo dia de fechamento do cartão."""
    if tx.invoice_month:
        year, month = tx.invoice_month.year, tx.invoice_month.month
        due_day = invoice_card(tx.payment_method).due_day or 1
        return InvoicePeriod(year, month, date(year, month, _clamp_day(year, month, due_day)))
    return invoice_period_for(tx.payment_method, tx.date, closings)


def first_installment_due_date(payment_method, purchase_date, first_invoice_month=None):
    """Vencimento da 1ª parcela. As demais são +1 mês cada."""
    if first_invoice_month:
        due_day = getattr(invoice_card(payment_method), "due_day", None) or purchase_date.day
        y, m = first_invoice_month.year, first_invoice_month.month
        return date(y, m, _clamp_day(y, m, due_day))
    return invoice_period_for(payment_method, purchase_date).due_date


# ---------------------------------------------------------------------------
# Recorrências
# ---------------------------------------------------------------------------

def recurrence_occurrences(rec, start, end):
    """Datas em que a recorrência ocorre entre `start` e `end` (inclusive).

    Não grava nada. CUSTOM não é projetada.
    """
    lo = max(start, rec.start_date)
    hi = min(end, rec.end_date) if rec.end_date else end
    if lo > hi:
        return []

    dates = []
    if rec.frequency == "MONTHLY":
        y, m = lo.year, lo.month
        while date(y, m, 1) <= hi:
            d = date(y, m, _clamp_day(y, m, rec.reference_day))
            if lo <= d <= hi:
                dates.append(d)
            y, m = add_months(y, m, 1)
    elif rec.frequency == "WEEKLY":
        weekday = min(max(rec.reference_day, 1), 7)
        d = lo + timedelta(days=(weekday - lo.isoweekday()) % 7)
        while d <= hi:
            dates.append(d)
            d += timedelta(days=7)
    elif rec.frequency == "YEARLY":
        month = rec.start_date.month
        for y in range(lo.year, hi.year + 1):
            d = date(y, month, _clamp_day(y, month, rec.reference_day))
            if lo <= d <= hi:
                dates.append(d)
    return dates


def _period_key(rec, d):
    if rec.frequency == "WEEKLY":
        iso = d.isocalendar()
        return ("W", iso[0], iso[1])
    if rec.frequency == "YEARLY":
        return ("Y", d.year)
    return ("M", d.year, d.month)


def projected_recurrences(start, end, payment_method_ids=None, credit_only=None):
    """Ocorrências futuras de recorrências ativas ainda sem Transaction gerada.

    Retorna lista de (recurrence, date).
    """
    from .models import Recurrence, Transaction

    qs = Recurrence.objects.filter(active=True, start_date__lte=end).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=start)
    ).select_related("payment_method__billing_card", "category", "entity")
    if payment_method_ids:
        qs = qs.filter(family_q("payment_method", payment_method_ids))
    if credit_only is True:
        qs = qs.filter(payment_method__type="CREDIT")
    elif credit_only is False:
        qs = qs.exclude(payment_method__type="CREDIT")

    result = []
    for rec in qs:
        existing = {
            _period_key(rec, d)
            for d in Transaction.objects.filter(recurrence=rec).values_list("date", flat=True)
        }
        for d in recurrence_occurrences(rec, start, end):
            if _period_key(rec, d) not in existing:
                result.append((rec, d))
    return result


# ---------------------------------------------------------------------------
# Previsão de faturas
# ---------------------------------------------------------------------------

def paid_invoices():
    """Faturas já pagas, conforme as transferências registradas: {(cartão, ano, mês)}."""
    from .models import Transfer

    return set(
        Transfer.objects.filter(to_card__isnull=False, invoice_year__isnull=False, invoice_month__isnull=False)
        .values_list("to_card_id", "invoice_year", "invoice_month")
    )


def invoice_forecast(month_from=None, month_to=None, payment_method_ids=None, include_items=True,
                     include_paid=False, today=None):
    """Faturas por mês de vencimento e método de pagamento.

    Soma: parcelas + compras à vista em cartão de crédito (pelo mês da fatura,
    menos estornos) + recorrências cobradas no cartão ainda não geradas.

    Por padrão mostra só o que falta pagar: parcelas não pagas e, para compras à
    vista, faturas do mês atual em diante que não tenham pagamento registrado.
    Com `include_paid=True` mostra a composição completa (faturas passadas).

    `month_from`/`month_to` são tuplas (ano, mês). Padrão: mês atual + 5 meses.
    """
    from .models import Installment, Transaction

    today = today or date.today()
    current = (today.year, today.month)
    if month_from is None:
        month_from = current
    if month_to is None:
        month_to = add_months(*month_from, 5)
    range_start = month_start(*month_from)
    range_end = month_end(*month_to)
    paid = set() if include_paid else paid_invoices()
    closings = load_closings()

    months = {}

    def add(ref_year, ref_month, pm, item):
        key = (ref_year, ref_month)
        if not (month_from <= key <= month_to):
            return
        root = invoice_card(pm)  # uma fatura por cartão principal
        bucket = months.setdefault(key, {"year": ref_year, "month": ref_month,
                                         "month_name": MONTH_NAMES[ref_month],
                                         "total": Decimal("0"), "methods": OrderedDict()})
        mb = bucket["methods"].setdefault(root.id, {"payment_method_id": root.id,
                                                    "payment_method": root.name,
                                                    "total": Decimal("0"), "count": 0,
                                                    "cards": OrderedDict(), "third_party": OrderedDict(),
                                                    "items": []})
        mb["total"] += item["amount"]
        mb["count"] += 1
        mb["cards"][pm.name] = mb["cards"].get(pm.name, Decimal("0")) + item["amount"]
        bucket["total"] += item["amount"]
        person = item.get("on_behalf_of")
        if person:
            # Compra de terceiro (cartão emprestado): está na fatura, mas a pessoa devolve
            mb["third_party"][person] = mb["third_party"].get(person, Decimal("0")) + item["amount"]
        if include_items:
            item["card"] = pm.name
            mb["items"].append(item)

    def open_invoice(pm_id, year, month):
        """Fatura de compras à vista ainda conta como 'a pagar'?"""
        if include_paid:
            return True
        return (year, month) >= current and (pm_id, year, month) not in paid

    # 1) Parcelas
    inst_qs = Installment.objects.filter(
        Q(reference_year__gt=month_from[0]) | Q(reference_year=month_from[0], reference_month__gte=month_from[1])
    ).filter(
        Q(reference_year__lt=month_to[0]) | Q(reference_year=month_to[0], reference_month__lte=month_to[1])
    ).select_related("purchase__payment_method__billing_card", "purchase__category",
                     "purchase__entity", "purchase__on_behalf_of").order_by("due_date", "purchase__description")
    if not include_paid:
        inst_qs = inst_qs.filter(paid=False)
    if payment_method_ids:
        inst_qs = inst_qs.filter(family_q("purchase__payment_method", payment_method_ids))
    for inst in inst_qs:
        purchase = inst.purchase
        add(inst.reference_year, inst.reference_month, purchase.payment_method, {
            "kind": "installment",
            "description": purchase.description,
            "installment": f"{inst.installment_number}/{purchase.number_of_installments}",
            "amount": inst.amount,
            "due_date": inst.due_date,
            "paid": inst.paid,
            "installment_id": inst.pk,
            "purchase_id": purchase.pk,
            "category": purchase.category.name,
            "category_color": purchase.category.color,
            "entity": purchase.entity.name if purchase.entity else None,
            "on_behalf_of": purchase.on_behalf_of.name if purchase.on_behalf_of_id else None,
        })

    # 2) Compras à vista no crédito (e estornos, que abatem a fatura)
    tx_qs = Transaction.objects.filter(payment_method__type="CREDIT").filter(
        Q(invoice_month__gte=range_start, invoice_month__lte=range_end)
        | Q(invoice_month__isnull=True, date__gte=range_start - relativedelta(months=2), date__lte=range_end)
    ).filter(Q(type="EXPENSE") | Q(type="INCOME", category__name=REFUND_CATEGORY_NAME)).select_related(
        "payment_method__billing_card", "category", "entity", "on_behalf_of").order_by("date")
    if payment_method_ids:
        tx_qs = tx_qs.filter(family_q("payment_method", payment_method_ids))
    for tx in tx_qs:
        period = transaction_invoice_period(tx, closings)
        if not open_invoice(invoice_card(tx.payment_method).pk, period.year, period.month):
            continue
        is_refund = tx.type == "INCOME"
        add(period.year, period.month, tx.payment_method, {
            "kind": "refund" if is_refund else "credit_purchase",
            "description": tx.description,
            "amount": -tx.amount if is_refund else tx.amount,
            "date": tx.date,
            "due_date": period.due_date,
            "transaction_id": tx.pk,
            "category": tx.category.name,
            "category_color": tx.category.color,
            "entity": tx.entity.name if tx.entity else None,
            "on_behalf_of": tx.on_behalf_of.name if tx.on_behalf_of_id else None,
        })

    # 3) Recorrências no cartão ainda não geradas (de hoje em diante)
    rec_start = max(range_start - relativedelta(months=2), today)
    for rec, d in projected_recurrences(rec_start, range_end, payment_method_ids, credit_only=True):
        if rec.type != "EXPENSE":
            continue
        period = invoice_period_for(rec.payment_method, d, closings)
        if not open_invoice(invoice_card(rec.payment_method).pk, period.year, period.month):
            continue
        add(period.year, period.month, rec.payment_method, {
            "kind": "recurrence",
            "description": rec.description,
            "amount": rec.amount,
            "date": d,
            "due_date": period.due_date,
            "category": rec.category.name,
            "category_color": rec.category.color,
            "entity": rec.entity.name if rec.entity else None,
        })

    result = []
    for key in sorted(months):
        bucket = months[key]
        bucket["methods"] = sorted(bucket["methods"].values(), key=lambda m: m["payment_method"])
        for method in bucket["methods"]:
            # Subtotal por cartão só interessa quando a fatura junta mais de um
            cards = method.pop("cards")
            if len(cards) > 1:
                method["cards"] = [{"card": name, "total": total} for name, total in cards.items()]
            # Quanto desta fatura é de terceiros (só aparece quando há)
            people = method.pop("third_party")
            if people:
                method["third_party"] = [{"person": name, "total": total} for name, total in people.items()]
                method["third_party_total"] = sum(people.values(), Decimal("0"))
        result.append(bucket)
    return result


# ---------------------------------------------------------------------------
# Saldos e fluxo de caixa
# ---------------------------------------------------------------------------

def account_balances(as_of=None):
    """Saldo de cada conta bancária ativa em `as_of` (padrão: hoje).

    Ponto de partida: o snapshot de saldo mais recente (ou o saldo inicial da
    conta). Depois dele somam-se receitas e subtraem-se despesas confirmadas
    feitas por métodos da conta (cartão de crédito NÃO entra: o gasto do cartão
    só sai da conta no pagamento da fatura, que é uma transferência).
    """
    from accounts.models import BankAccount

    from .models import Transaction, Transfer

    as_of = as_of or date.today()

    def total(qs):
        return (qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")).quantize(Decimal("0.01"))

    accounts = []
    reserved_unknown = []
    grand_total = available = reserved = Decimal("0")
    by_holder = {}
    for acct in BankAccount.objects.filter(active=True).select_related(
            "parent__holder", "holder").order_by("name"):
        snapshot = acct.balance_snapshots.filter(date__lte=as_of).order_by("-date").first()
        if snapshot:
            anchor_date, base, anchor = snapshot.date, snapshot.balance, "snapshot"
        elif acct.opening_balance_date and acct.opening_balance_date <= as_of:
            anchor_date, base, anchor = acct.opening_balance_date, acct.opening_balance, "opening"
        else:
            anchor_date, base, anchor = None, acct.opening_balance, None

        tx = Transaction.objects.filter(
            payment_method__bank_account=acct, confirmed=True, date__lte=as_of
        ).exclude(payment_method__type="CREDIT")
        out = Transfer.objects.filter(from_account=acct, date__lte=as_of)
        into = Transfer.objects.filter(to_account=acct, date__lte=as_of)
        if anchor_date:
            tx = tx.filter(date__gt=anchor_date)
            out = out.filter(date__gt=anchor_date)
            into = into.filter(date__gt=anchor_date)

        income = total(tx.filter(type="INCOME"))
        expense = total(tx.filter(type="EXPENSE"))
        transfers_out, transfers_in = total(out), total(into)
        balance = base + income - expense - transfers_out + transfers_in
        net_movements = income - expense - transfers_out + transfers_in
        holder = acct.effective_holder
        person = by_holder.setdefault(holder.name if holder else NO_HOLDER_LABEL,
                                      {"available": Decimal("0"), "reserved": Decimal("0")})
        if acct.is_reserve and anchor is None:
            # Caixinha sem saldo informado: só conhecemos entradas e saídas, não o saldo
            balance = None
            reserved_unknown.append(acct.name)
        elif acct.is_reserve:
            reserved += balance
            grand_total += balance
            person["reserved"] += balance
        else:
            available += balance
            grand_total += balance
            person["available"] += balance
        accounts.append({
            "account_id": acct.pk, "account": acct.name, "type": acct.type, "balance": balance,
            "holder": holder.name if holder else None,
            "net_movements_since_anchor": net_movements,
            "reserve": acct.is_reserve, "parent_account": acct.parent.name if acct.parent_id else None,
            "anchor": anchor, "anchor_date": anchor_date, "anchor_balance": base,
            "income_since": income, "expense_since": expense,
            "transfers_out_since": transfers_out, "transfers_in_since": transfers_in,
        })
    # Contas-mãe primeiro, cada uma seguida das suas caixinhas
    accounts.sort(key=lambda a: (a["parent_account"] or a["account"], a["parent_account"] is not None, a["account"]))
    return {
        "as_of": as_of, "total": grand_total, "available": available, "reserved": reserved,
        "reserved_unknown": reserved_unknown,  # caixinhas ainda sem saldo informado (fora dos totais)
        # Quanto está com cada pessoa da família (só aparece com mais de um grupo)
        "by_holder": by_holder if len(by_holder) > 1 else {},
        "accounts": accounts,
        "all_anchored": bool(accounts) and all(a["anchor"] for a in accounts),
        # O dinheiro do dia a dia tem ponto de partida? (caixinhas à parte)
        "available_anchored": any(not a["reserve"] for a in accounts)
        and all(a["anchor"] for a in accounts if not a["reserve"]),
    }


def monthly_cash_flow(months_ahead=3, today=None):
    """Projeção do saldo: saldo atual + receitas previstas - despesas previstas
    - faturas de cartão a vencer, mês a mês (o mês atual conta de hoje em diante).

    Previsto = lançamentos não confirmados com data futura + recorrências ativas
    ainda não geradas. Despesas no cartão entram pela fatura, não pela compra.
    """
    from .models import Transaction

    today = today or date.today()
    balances = account_balances(today)
    running = balances["available"]  # caixinhas/investimentos ficam de fora da projeção

    def total(qs):
        return (qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")).quantize(Decimal("0.01"))

    months = []
    for i in range(months_ahead + 1):
        year, month = add_months(today.year, today.month, i)
        start = today if i == 0 else month_start(year, month)
        end = month_end(year, month)

        pending = Transaction.objects.filter(confirmed=False, date__gte=start, date__lte=end).exclude(
            payment_method__type="CREDIT")
        income = total(pending.filter(type="INCOME"))
        expenses = total(pending.filter(type="EXPENSE"))
        for rec, _d in projected_recurrences(start, end, credit_only=False):
            if rec.type == "INCOME":
                income += rec.amount
            else:
                expenses += rec.amount

        invoices = []
        invoices_total = third_party_total = Decimal("0")
        for bucket in invoice_forecast((year, month), (year, month), include_items=True, today=today):
            for method in bucket["methods"]:
                due_items = [it for it in method["items"] if it["due_date"] >= start]
                amount = sum((it["amount"] for it in due_items), Decimal("0"))
                if due_items:
                    invoices.append({"payment_method": method["payment_method"], "amount": amount,
                                     "due_date": max(it["due_date"] for it in due_items)})
                    invoices_total += amount
                    third_party_total += sum((it["amount"] for it in due_items if it.get("on_behalf_of")),
                                             Decimal("0"))

        net = income - expenses - invoices_total
        running += net
        months.append({
            "year": year, "month": month, "month_name": MONTH_NAMES[month], "from": start, "to": end,
            "expected_income": income, "expected_expenses": expenses,
            "card_invoices": invoices_total, "invoices": invoices,
            # Parte das faturas que é de terceiros (cartão emprestado). A família paga o banco de
            # qualquer jeito; o que a pessoa devolver entra a mais, e não está contado no saldo.
            "third_party_in_invoices": third_party_total,
            "net": net, "projected_end_balance": running,
        })
    return {
        "today": today, "start_balance": balances["available"], "reserved": balances["reserved"],
        "all_anchored": balances["available_anchored"],
        "accounts": [{"account": a["account"], "balance": a["balance"], "reserve": a["reserve"],
                      "anchor": a["anchor"], "anchor_date": a["anchor_date"]} for a in balances["accounts"]],
        "months": months,
    }


# ---------------------------------------------------------------------------
# Resumos de gastos
# ---------------------------------------------------------------------------

GROUP_FIELDS = {
    "category": ("category_id", "category__name", "purchase__category_id", "purchase__category__name"),
    "payment_method": ("payment_method_id", "payment_method__name",
                       "purchase__payment_method_id", "purchase__payment_method__name"),
    "entity": ("entity_id", "entity__name", "purchase__entity_id", "purchase__entity__name"),
}


def spending_summary(start, end, group_by="category", include_unconfirmed=False,
                     payment_method_ids=None, category_ids=None, third_party="exclude"):
    """Gastos no período, agrupados.

    Regime: despesas (Transaction EXPENSE) pela data; parcelas de compras
    parceladas pelo vencimento. Estornos (receita na categoria "Estornos")
    são descontados.

    Compras de terceiros (`on_behalf_of`, cartão emprestado) não são gasto da
    família: por padrão ficam fora dos grupos e do total, e somam à parte em
    `third_party_total`. `third_party="only"` mostra só elas; `"include"`, tudo junto.
    """
    from .models import Installment, Transaction

    if group_by not in (*GROUP_FIELDS, "month", "holder"):
        raise ValueError(f"group_by inválido: {group_by}")
    if third_party not in ("exclude", "only", "include"):
        raise ValueError(f"third_party inválido: {third_party}")

    holder_paths = ("__holder", "__bank_account__holder", "__bank_account__parent__holder",
                    "__billing_card__holder", "__billing_card__bank_account__holder")
    tx_qs = Transaction.objects.filter(date__gte=start, date__lte=end).select_related(
        "category", "payment_method", "entity", *(f"payment_method{p}" for p in holder_paths))
    if not include_unconfirmed:
        tx_qs = tx_qs.filter(confirmed=True)
    if payment_method_ids:
        tx_qs = tx_qs.filter(family_q("payment_method", payment_method_ids))
    if category_ids:
        tx_qs = tx_qs.filter(category_id__in=category_ids)

    inst_qs = Installment.objects.filter(due_date__gte=start, due_date__lte=end).select_related(
        "purchase__category", "purchase__payment_method", "purchase__entity",
        *(f"purchase__payment_method{p}" for p in holder_paths))
    if payment_method_ids:
        inst_qs = inst_qs.filter(family_q("purchase__payment_method", payment_method_ids))
    if category_ids:
        inst_qs = inst_qs.filter(purchase__category_id__in=category_ids)

    groups = {}

    def bucket(key, label):
        return groups.setdefault(key, {"key": key, "label": label, "total": Decimal("0"), "count": 0})

    def holder_key(payment_method):
        holder = payment_method.effective_holder
        return (holder.pk, holder.name) if holder else (None, NO_HOLDER_LABEL)

    def key_for_tx(tx):
        if group_by == "month":
            k = f"{tx.date.year}-{tx.date.month:02d}"
            return k, k
        if group_by == "holder":
            return holder_key(tx.payment_method)
        obj = getattr(tx, group_by)
        return (obj.id if obj else None), (obj.name if obj else "(sem)")

    def key_for_inst(inst):
        if group_by == "month":
            k = f"{inst.due_date.year}-{inst.due_date.month:02d}"
            return k, k
        if group_by == "holder":
            return holder_key(inst.purchase.payment_method)
        obj = getattr(inst.purchase, group_by)
        return (obj.id if obj else None), (obj.name if obj else "(sem)")

    total = Decimal("0")
    refunds = Decimal("0")
    third_party_total = Decimal("0")

    def counts(is_third_party):
        """Este lançamento entra nos grupos? (terceiros: conforme `third_party`)"""
        if third_party == "include":
            return True
        return is_third_party == (third_party == "only")

    for tx in tx_qs:
        is_refund = tx.type == "INCOME" and tx.category and tx.category.name == REFUND_CATEGORY_NAME
        if tx.type != "EXPENSE" and not is_refund:
            continue  # receitas (inclusive devoluções de terceiros) não são gasto
        signed = -tx.amount if is_refund else tx.amount
        if tx.on_behalf_of_id:
            third_party_total += signed
        if not counts(bool(tx.on_behalf_of_id)):
            continue
        b = bucket(*key_for_tx(tx))
        b["total"] += signed
        total += signed
        if is_refund:
            refunds += tx.amount
        else:
            b["count"] += 1
    for inst in inst_qs:
        is_third_party = bool(inst.purchase.on_behalf_of_id)
        if is_third_party:
            third_party_total += inst.amount
        if not counts(is_third_party):
            continue
        b = bucket(*key_for_inst(inst))
        b["total"] += inst.amount
        b["count"] += 1
        total += inst.amount

    rows = sorted(groups.values(), key=lambda r: (r["key"] if group_by == "month" else -r["total"]))
    return {"start": start, "end": end, "group_by": group_by, "total": total,
            "refunds": refunds, "third_party": third_party, "third_party_total": third_party_total,
            "rows": rows}


# ---------------------------------------------------------------------------
# Terceiros (cartão emprestado)
# ---------------------------------------------------------------------------

def third_party_balances(today=None, person_ids=None, include_items=False):
    """Conta corrente de cada pessoa de fora da família que usa um cartão (ou
    conta) da família: o que ela gastou, o que já devolveu e quanto deve.

    - Gasto: despesas e parcelas marcadas com `on_behalf_of` (menos estornos).
      Compra no crédito conta no mês de vencimento da fatura em que cai; o resto,
      na própria data.
    - Devolvido: receitas confirmadas marcadas com a mesma pessoa.
    - `due` = o que já venceu ou vence até o fim do mês atual; `upcoming` = faturas
      dos meses seguintes (parcelas futuras). `balance` = due - devolvido (negativo:
      a pessoa adiantou); `balance_with_upcoming` soma o que ainda vai vencer.
    """
    from .models import Installment, Transaction

    today = today or date.today()
    current = (today.year, today.month)
    closings = load_closings()
    people = {}

    def entry(entity):
        return people.setdefault(entity.pk, {
            "person_id": entity.pk, "person": entity.name,
            "charged_total": Decimal("0"), "due": Decimal("0"), "upcoming": Decimal("0"),
            "repaid": Decimal("0"), "by_month": {}, "items": [], "repayments": [],
        })

    def charge(entity, year, month, amount, item):
        p = entry(entity)
        p["charged_total"] += amount
        p["due" if (year, month) <= current else "upcoming"] += amount
        key = f"{year}-{month:02d}"
        p["by_month"][key] = p["by_month"].get(key, Decimal("0")) + amount
        if include_items:
            p["items"].append({"month": key, "amount": amount, **item})

    tx_qs = Transaction.objects.filter(on_behalf_of__isnull=False).select_related(
        "on_behalf_of", "category", "payment_method__billing_card").order_by("date")
    inst_qs = Installment.objects.filter(purchase__on_behalf_of__isnull=False).select_related(
        "purchase__on_behalf_of", "purchase__payment_method").order_by("due_date")
    if person_ids:
        tx_qs = tx_qs.filter(on_behalf_of_id__in=person_ids)
        inst_qs = inst_qs.filter(purchase__on_behalf_of_id__in=person_ids)

    for tx in tx_qs:
        is_refund = tx.type == "INCOME" and tx.category.name == REFUND_CATEGORY_NAME
        if tx.type == "INCOME" and not is_refund:
            if tx.confirmed:
                p = entry(tx.on_behalf_of)
                p["repaid"] += tx.amount
                if include_items:
                    p["repayments"].append({"date": tx.date, "amount": tx.amount, "description": tx.description,
                                            "transaction_id": tx.pk})
            continue
        if tx.payment_method.type == "CREDIT":
            period = transaction_invoice_period(tx, closings)
            year, month = period.year, period.month
        else:
            year, month = tx.date.year, tx.date.month
        charge(tx.on_behalf_of, year, month, -tx.amount if is_refund else tx.amount, {
            "kind": "refund" if is_refund else "purchase", "date": tx.date, "description": tx.description,
            "payment_method": tx.payment_method.name, "transaction_id": tx.pk,
        })
    for inst in inst_qs:
        purchase = inst.purchase
        charge(purchase.on_behalf_of, inst.reference_year, inst.reference_month, inst.amount, {
            "kind": "installment", "date": purchase.purchase_date,
            "description": f"{purchase.description} ({inst.installment_number}/{purchase.number_of_installments})",
            "payment_method": purchase.payment_method.name, "purchase_id": purchase.pk,
        })

    result = []
    for p in sorted(people.values(), key=lambda p: p["person"].lower()):
        p["balance"] = p["due"] - p["repaid"]
        p["balance_with_upcoming"] = p["charged_total"] - p["repaid"]
        p["by_month"] = [{"month": k, "amount": v} for k, v in sorted(p["by_month"].items())]
        if not include_items:
            del p["items"], p["repayments"]
        result.append(p)
    return {
        "as_of": today, "people": result,
        "total_due": sum((p["balance"] for p in result), Decimal("0")),
        "total_with_upcoming": sum((p["balance_with_upcoming"] for p in result), Decimal("0")),
    }
