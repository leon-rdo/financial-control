"""Regras permanentes ditas pelo usuário ("Pix para a empresa X é gasto").

Vão junto com os cadastros (`user_rules`) para o agente e para o extrator de
documentos, para ninguém perguntar de novo o que já foi respondido. Grava na
hora, sem lote: não mexe em lançamentos."""

from pydantic import Field

from ..models import UserRule
from .registry import Tool, ToolError, ToolInput

MAX_RULES = 40


def rules_view():
    return list(UserRule.objects.filter(active=True).values("id", "text"))


class SaveUserRuleInput(ToolInput):
    text: str | None = Field(
        default=None,
        description=("A regra, em uma frase completa e autossuficiente, ex.: 'Pix para a empresa ACME LTDA é "
                     "despesa, categoria Serviços' ou 'Pagamento de fatura no extrato do banco X é do cartão "
                     "final 1234'."),
    )
    remove_rule_id: int | None = Field(default=None, description="ID de uma regra a remover (ou a substituir).")


def save_user_rule(args, ctx):
    if not args.text and args.remove_rule_id is None:
        raise ToolError("Informe text (regra nova) e/ou remove_rule_id.")
    removed = None
    if args.remove_rule_id is not None:
        if not UserRule.objects.filter(pk=args.remove_rule_id, active=True).update(active=False):
            raise ToolError(f"Regra id={args.remove_rule_id} não existe.")
        removed = args.remove_rule_id
    saved = None
    if args.text:
        text = " ".join(args.text.split())[:300]
        if UserRule.objects.filter(active=True).count() >= MAX_RULES:
            raise ToolError(f"Já há {MAX_RULES} regras. Remova ou junte alguma antes de criar outra.")
        rule = UserRule.objects.filter(text__iexact=text).first()
        if rule:
            rule.active = True
            rule.save(update_fields=["active"])
        else:
            rule = UserRule.objects.create(text=text)
        saved = {"id": rule.pk, "text": rule.text}
    return {"saved": saved, "removed_rule_id": removed, "user_rules": rules_view()}


TOOLS = [
    Tool(
        name="save_user_rule",
        description=(
            "Guarda (ou remove) uma regra permanente do usuário sobre como classificar lançamentos, para "
            "valer nos próximos documentos e conversas. Use quando o usuário responder uma dúvida que vai "
            "se repetir ('esse Pix é sempre gasto', 'isso é sempre do cartão X') ou pedir 'lembre disso'. "
            "Grava na hora. Não use para fatos de um lançamento só."
        ),
        input_model=SaveUserRuleInput,
        handler=save_user_rule,
    ),
]
