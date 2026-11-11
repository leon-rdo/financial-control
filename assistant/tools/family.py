"""Cadastro das pessoas da família e de quem é cada conta/cartão.

São as únicas ferramentas que gravam direto, sem lote: mexem só em cadastro
(quem é quem), nunca em lançamentos, e só devem ser usadas a pedido explícito.
"""

from pydantic import Field

from accounts.models import BankAccount, PaymentMethod
from core.models import FamilyMember

from .registry import Tool, ToolError, ToolInput


def members_view(chat_id=None):
    return [
        {"id": m.pk, "name": m.name, "names_on_documents": m.alias_list,
         "has_telegram": m.telegram_chat_id is not None,
         "is_speaker": chat_id is not None and m.telegram_chat_id == chat_id}
        for m in FamilyMember.objects.filter(active=True)
    ]


class SaveFamilyMemberInput(ToolInput):
    name: str = Field(description="Primeiro nome ou como a pessoa é chamada, ex.: 'Maria'.")
    names_on_documents: list[str] | None = Field(
        default=None,
        description="Como o nome aparece em extratos e faturas (nome completo, em maiúsculas se for o caso).",
    )
    is_speaker: bool = Field(
        default=False, description="true se esta pessoa é quem está falando agora (liga este chat a ela)."
    )


def save_family_member(args, ctx):
    name = args.name.strip()
    if not name:
        raise ToolError("Informe o nome.")
    member = FamilyMember.objects.filter(name__iexact=name).first()
    created = member is None
    if created:
        member = FamilyMember(name=name[:100])
    if args.names_on_documents:
        merged = member.alias_list
        for alias in args.names_on_documents:
            alias = alias.strip()
            if alias and alias.lower() not in {a.lower() for a in merged}:
                merged.append(alias)
        member.aliases = "\n".join(merged)
    member.active = True
    if args.is_speaker:
        FamilyMember.objects.filter(telegram_chat_id=ctx.chat_id).exclude(pk=member.pk).update(telegram_chat_id=None)
        member.telegram_chat_id = ctx.chat_id
    member.save()
    return {"saved": {"id": member.pk, "name": member.name, "created": created},
            "family_members": members_view(ctx.chat_id)}


class AssignHolderInput(ToolInput):
    family_member_id: int = Field(description="ID da pessoa (de get_reference_data ou save_family_member).")
    bank_account_ids: list[int] = Field(default_factory=list, description="Contas (ou caixinhas) dessa pessoa.")
    payment_method_ids: list[int] = Field(
        default_factory=list,
        description="Cartões/métodos usados por essa pessoa. Só é preciso quando difere do titular da conta.",
    )


def assign_holder(args, ctx):
    member = FamilyMember.objects.filter(pk=args.family_member_id, active=True).first()
    if member is None:
        raise ToolError(f"Pessoa id={args.family_member_id} não existe. Use save_family_member antes.")
    if not (args.bank_account_ids or args.payment_method_ids):
        raise ToolError("Informe ao menos uma conta ou um método de pagamento.")
    accounts = list(BankAccount.objects.filter(pk__in=args.bank_account_ids))
    methods = list(PaymentMethod.objects.filter(pk__in=args.payment_method_ids))
    missing = (set(args.bank_account_ids) - {a.pk for a in accounts}) | \
              (set(args.payment_method_ids) - {m.pk for m in methods})
    if missing:
        raise ToolError(f"IDs não encontrados: {sorted(missing)}. Consulte get_reference_data.")
    BankAccount.objects.filter(pk__in=[a.pk for a in accounts]).update(holder=member)
    PaymentMethod.objects.filter(pk__in=[m.pk for m in methods]).update(holder=member)
    return {"holder": member.name, "bank_accounts": [a.name for a in accounts],
            "payment_methods": [m.name for m in methods]}


TOOLS = [
    Tool(
        name="save_family_member",
        description=(
            "Cadastra ou atualiza uma pessoa da família (as finanças são conjuntas; isto diz quem é quem). "
            "Use quando o usuário se apresentar ('sou a Maria') ou pedir para cadastrar alguém da família. "
            "Grava na hora, sem lote. Não use por conta própria."
        ),
        input_model=SaveFamilyMemberInput,
        handler=save_family_member,
    ),
    Tool(
        name="assign_holder",
        description=(
            "Define de quem é uma conta, caixinha ou cartão ('o Inter é da Maria'). Caixinhas herdam o "
            "titular da conta e métodos herdam o da conta ou do cartão principal, então só informe o que "
            "for diferente. Grava na hora, sem lote. Use só a pedido explícito do usuário."
        ),
        input_model=AssignHolderInput,
        handler=assign_holder,
    ),
]
