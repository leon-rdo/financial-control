from django.db.models import Q
from pydantic import Field

from accounts.models import BankAccount, PaymentMethod
from core.models import Category, Entity

from .family import members_view
from .rules import rules_view
from .third_party import people_view
from .registry import Tool, ToolInput


class GetReferenceDataInput(ToolInput):
    entity_query: str | None = Field(
        default=None,
        description="Filtra entidades (estabelecimentos/pessoas) pelo nome. Vazio: as 50 primeiras.",
    )


def get_reference_data(args, ctx):
    entities = Entity.objects.filter(active=True)
    if args.entity_query:
        q = Q(name__icontains=args.entity_query)
        for word in args.entity_query.split():
            if len(word) > 3:
                q |= Q(name__icontains=word)
        entities = entities.filter(q)
    chat_id = getattr(ctx, "chat_id", None)
    return {
        # Finanças conjuntas: quem é da família e quem está falando/enviou o documento
        "family_members": members_view(chat_id),
        # Regras permanentes ditas pelo usuário: seguir sem perguntar de novo
        "user_rules": rules_view(),
        # Pessoas de fora da família que usam um cartão da família (cartão emprestado)
        "third_parties": people_view(),
        "categories": list(Category.objects.filter(active=True).values("id", "name", "type")),
        "payment_methods": [
            {
                "id": pm.id, "name": pm.name, "type": pm.type,
                "closing_day": pm.invoice_card.closing_day, "due_day": pm.invoice_card.due_day,
                "bank_account": pm.bank_account.name if pm.bank_account else None,
                "holder": pm.effective_holder.name if pm.effective_holder else None,
                # cartão adicional/virtual: cobrado na fatura deste outro cartão
                "billed_on_invoice_of": pm.billing_card.name if pm.billing_card_id else None,
                # cartão que fica com alguém de fora da família: as compras nele são dessa pessoa
                "lent_to": pm.lent_to.name if pm.lent_to_id else None,
            }
            for pm in PaymentMethod.objects.filter(active=True).select_related(
                "holder", "bank_account__holder", "bank_account__parent__holder", "billing_card__holder",
                "billing_card__bank_account__holder", "lent_to")
        ],
        "bank_accounts": [
            {
                "id": a.id, "name": a.name, "bank": a.bank, "type": a.type,
                # caixinha/cofrinho: dinheiro guardado dentro desta outra conta
                "pot_of": a.parent.name if a.parent_id else None,
                "holder": a.effective_holder.name if a.effective_holder else None,
            }
            for a in BankAccount.objects.filter(active=True).select_related("parent__holder", "holder")
        ],
        "entities": list(entities.values("id", "name", "type")[:50]),
    }


TOOLS = [
    Tool(
        name="get_reference_data",
        description=(
            "Lista as pessoas da família, as regras permanentes do usuário (user_rules), as pessoas de fora que "
            "usam cartão da família (third_parties), categorias, métodos de pagamento (com tipo, dia de fechamento e vencimento "
            "dos cartões, e de qual fatura cada cartão adicional faz parte), contas bancárias com "
            "suas caixinhas e entidades cadastradas, com seus IDs. Chame antes de montar "
            "lançamentos ou filtrar consultas; nunca invente IDs."
        ),
        input_model=GetReferenceDataInput,
        handler=get_reference_data,
    ),
]
