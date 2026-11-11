"""Cartão emprestado: compras de pessoas de fora da família feitas no cartão (ou
na conta) da família, e o que cada uma já devolveu.

`mark_third_party` grava direto, sem lote: só diz de quem é uma compra que já
existe (não cria nem altera valores) e só deve ser usada a pedido explícito.
"""

from pydantic import Field

from accounts.models import PaymentMethod
from core.models import Entity, FamilyMember
from financial import forecast
from financial.models import Purchase, Transaction

from .registry import Tool, ToolError, ToolInput


def find_person(name):
    qs = Entity.objects.filter(name__iexact=name.strip())
    return qs.filter(type=Entity.TypeChoices.PERSON).first() or qs.first()


def people_view():
    """Pessoas com compras/devoluções registradas ou com um cartão emprestado."""
    balances = {p["person_id"]: p for p in forecast.third_party_balances()["people"]}
    lent = {}
    for card in PaymentMethod.objects.filter(lent_to__isnull=False, active=True).select_related("lent_to"):
        lent.setdefault(card.lent_to_id, (card.lent_to.name, []))[1].append(card.name)
    view = []
    for pk in sorted(set(balances) | set(lent), key=lambda k: (balances.get(k, {}).get("person") or lent[k][0]).lower()):
        row = {"id": pk, "name": balances[pk]["person"] if pk in balances else lent[pk][0]}
        if pk in balances:
            row["owes"] = balances[pk]["balance"]
            row["owes_with_upcoming"] = balances[pk]["balance_with_upcoming"]
        if pk in lent:
            row["uses_cards"] = lent[pk][1]
        view.append(row)
    return view


class ThirdPartyBalancesInput(ToolInput):
    person: str | None = Field(default=None, description="Nome da pessoa. Vazio: todas.")
    include_items: bool = Field(
        default=False, description="Listar cada compra, parcela e devolução (para montar uma cobrança)."
    )


def get_third_party_balances(args, ctx):
    person_ids = None
    if args.person:
        person = find_person(args.person)
        if person is None:
            raise ToolError(f"Não há compras registradas em nome de '{args.person}'.")
        person_ids = [person.pk]
    data = forecast.third_party_balances(person_ids=person_ids, include_items=args.include_items)
    data["note"] = ("Por pessoa de fora da família: charged_total = tudo que gastou no cartão/conta da família; "
                    "due = o que já venceu ou vence nas faturas até o mês atual; upcoming = parcelas em faturas "
                    "futuras; repaid = o que já devolveu; balance = due - repaid (quanto deve agora; negativo = "
                    "adiantou); by_month = mês de vencimento da fatura. Nada disso entra nos gastos nem nas "
                    "receitas da família.")
    return data


class MarkThirdPartyInput(ToolInput):
    person_name: str | None = Field(
        default=None, description="Nome da pessoa de fora da família. Vazio com clear=true: tira a marcação."
    )
    transaction_ids: list[int] = Field(
        default_factory=list, description="Lançamentos já gravados (id de query_transactions, kind=transaction)."
    )
    purchase_ids: list[int] = Field(
        default_factory=list, description="Compras parceladas já gravadas (purchase_id de query_transactions)."
    )
    payment_method_ids: list[int] = Field(
        default_factory=list,
        description=("Cartões que ficam com essa pessoa: as compras importadas neles passam a ser dela por "
                     "padrão. Não muda o que já está gravado, a menos que apply_to_existing=true."),
    )
    apply_to_existing: bool = Field(
        default=False, description="Com payment_method_ids: marca também tudo que já foi gravado nesses cartões."
    )
    clear: bool = Field(default=False, description="true = tira a marcação (a compra volta a ser gasto da família).")


def mark_third_party(args, ctx):
    if not (args.transaction_ids or args.purchase_ids or args.payment_method_ids):
        raise ToolError("Informe transaction_ids, purchase_ids ou payment_method_ids.")
    if args.clear:
        person = None
    else:
        name = (args.person_name or "").strip()
        if not name:
            raise ToolError("Informe person_name (ou clear=true para tirar a marcação).")
        for member in FamilyMember.objects.filter(active=True):
            if name.lower() in {member.name.lower(), *(a.lower() for a in member.alias_list)}:
                raise ToolError(f"'{name}' é da família: use assign_holder para dizer que o cartão é dela.")
        person = find_person(name) or Entity.objects.create(name=name[:200], type=Entity.TypeChoices.PERSON)

    transactions = Transaction.objects.filter(pk__in=args.transaction_ids)
    purchases = Purchase.objects.filter(pk__in=args.purchase_ids)
    cards = PaymentMethod.objects.filter(pk__in=args.payment_method_ids)
    missing = (set(args.transaction_ids) - set(transactions.values_list("pk", flat=True))) \
        | (set(args.purchase_ids) - set(purchases.values_list("pk", flat=True))) \
        | (set(args.payment_method_ids) - set(cards.values_list("pk", flat=True)))
    if missing:
        raise ToolError(f"IDs não encontrados: {sorted(missing)}. Consulte query_transactions / get_reference_data.")

    result = {"person": person.name if person else None,
              "transactions": transactions.update(on_behalf_of=person),
              "purchases": purchases.update(on_behalf_of=person)}
    if args.payment_method_ids:
        result["cards"] = list(cards.values_list("name", flat=True))
        cards.update(lent_to=person)
        if args.apply_to_existing:
            result["transactions"] += Transaction.objects.filter(
                payment_method_id__in=args.payment_method_ids, type="EXPENSE").update(on_behalf_of=person)
            result["purchases"] += Purchase.objects.filter(
                payment_method_id__in=args.payment_method_ids).update(on_behalf_of=person)
    if person:
        result["balance"] = forecast.third_party_balances(person_ids=[person.pk])["people"]
    return result


TOOLS = [
    Tool(
        name="get_third_party_balances",
        description=(
            "Cartão emprestado: quanto cada pessoa de fora da família gastou no cartão/conta da família, "
            "quanto já devolveu e quanto deve (agora e com as parcelas futuras), por fatura. Use para "
            "'quanto o João me deve?', 'quanto da fatura de dezembro é da Ana?' e para montar uma cobrança."
        ),
        input_model=ThirdPartyBalancesInput,
        handler=get_third_party_balances,
    ),
    Tool(
        name="mark_third_party",
        description=(
            "Diz que compras JÁ GRAVADAS são de uma pessoa de fora da família (cartão emprestado), ou que um "
            "cartão fica com ela. Não cria lançamento nem muda valores: só tira a compra dos gastos da "
            "família e a põe na conta da pessoa. Grava na hora, sem lote; use só a pedido explícito do "
            "usuário. Para itens de um lote ainda não confirmado, use edit_staged_entries."
        ),
        input_model=MarkThirdPartyInput,
        handler=mark_third_party,
    ),
]
