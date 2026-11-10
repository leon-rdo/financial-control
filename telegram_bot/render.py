"""Textos e teclados do bot para lotes (HTML escapado, só templates próprios)."""

from decimal import Decimal
from html import escape

from accounts.models import BankAccount
from assistant import batch_service
from assistant.models import StagedEntry
from financial.forecast import MONTH_NAMES


def brl(value):
    value = Decimal(value or 0)
    text = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {text}" if value < 0 else f"R$ {text}"


def batch_keyboard(batch, included):
    return {
        "inline_keyboard": [
            [
                {"text": f"✅ Confirmar ({included})", "callback_data": f"b:c:{batch.pk}:{batch.version}"},
                {"text": "📋 Ver itens", "callback_data": f"b:v:{batch.pk}"},
            ],
            [{"text": "❌ Descartar", "callback_data": f"b:d:{batch.pk}:{batch.version}"}],
        ]
    }


def batch_summary(batch):
    """Resumo do lote (HTML) e teclado de confirmação."""
    t = batch_service.batch_totals(batch)
    title = batch.title or batch.get_kind_display()
    lines = [f"🧾 <b>Lote #{batch.pk}</b> · {escape(title)}"]
    if batch.payment_method_id:
        lines.append(f"Cartão/conta: {escape(batch.payment_method.name)}")
    elif batch.new_payment_method:
        spec = batch.new_payment_method
        days = []
        if spec.get("closing_day") or batch.invoice_closing_date:
            days.append(f"fecha dia {spec.get('closing_day') or batch.invoice_closing_date.day}")
        if spec.get("due_day") or batch.invoice_due_date:
            days.append(f"vence dia {spec.get('due_day') or batch.invoice_due_date.day}")
        extra = f" ({', '.join(days)})" if days else ""
        lines.append(f"🆕 Ao confirmar, cadastro o cartão: <b>{escape(spec['name'])}</b>{extra}")
        if spec.get("new_bank_account_name"):
            lines.append(f"🆕 e a conta: {escape(spec['new_bank_account_name'])}")
    if batch.additional_new_cards:
        names = ", ".join(escape(c["name"]) for c in batch.additional_new_cards)
        lines.append(f"🆕 Outros cartões desta fatura a cadastrar: {names}")
    pots = sorted({n for e in batch.entries.all() for n in (e.from_account_name, e.to_account_name) if n}
                  | {b["account_name"] for b in batch.other_balances or [] if b.get("account_name")})
    if pots:
        where = f" em {escape(batch.balance_account.name)}" if batch.balance_account_id else ""
        lines.append(f"🆕 Caixinhas a cadastrar{where}: {', '.join(escape(n) for n in pots)}")
    if batch.invoice_year:
        due = f" (vence {batch.invoice_due_date:%d/%m/%Y})" if batch.invoice_due_date else ""
        lines.append(f"Fatura: {MONTH_NAMES[batch.invoice_month]}/{batch.invoice_year}{due}")
    lines.append("")
    lines.append(f"• A gravar: <b>{t['included']}</b> item(ns)" + (
        f", {brl(t['included_amount'])} em despesas" if t["included_amount"] else ""))
    if t["included_income"]:
        lines.append(f"• Receitas: {brl(t['included_income'])}")
    if t["included_transfers"]:
        lines.append(f"• Transferências (caixinhas, contas próprias, fatura): {brl(t['included_transfers'])}, "
                     "não contam como gasto")
    if t["confirm_existing"]:
        lines.append(f"  (dos quais {t['confirm_existing']} atualizam lançamentos já existentes)")
    if t["excluded"]:
        lines.append(f"• Já registrados / ignorados: {t['excluded']} item(ns), {brl(t['excluded_amount'])}")
    if t["weak"]:
        lines.append(f"• ⚠️ Possíveis duplicados: {t['weak']} (veja em Ver itens)")
    if t["refunds"]:
        lines.append(f"• Estornos: {brl(t['refunds'])}")
    if "invoice_difference" in t:
        diff = t["invoice_difference"]
        status = "✅ bate" if abs(diff) < Decimal("0.01") else f"diferença de {brl(diff)}"
        lines.append(f"• Total da fatura: {brl(batch.invoice_total)} · soma dos itens "
                     f"{brl(t['invoice_items_sum'])} ({status})")
    for name, amount in (t.get("by_card") or {}).items():
        lines.append(f"   ◦ {escape(name)}: {brl(amount)}")
    if "statement_difference" in t:
        diff = t["statement_difference"]
        status = "✅ bate" if abs(diff) < Decimal("0.01") else f"diferença de {brl(diff)}"
        lines.append(f"• Extrato: saldo inicial {brl(batch.opening_balance)} → final {brl(batch.balance_amount)} "
                     f"({status})")
    if t["missing_payment_method"]:
        positions = ", ".join(str(p) for p in t["missing_payment_method"])
        lines.append(f"• ❗ Sem método de pagamento: itens {positions}")
    if batch.balance_amount is not None and batch.balance_account_id:
        lines.append(f"• Saldo de {escape(batch.balance_account.name)} em {batch.balance_date:%d/%m/%Y}: "
                     f"{brl(batch.balance_amount)}")
    for item in batch.other_balances or []:
        name = item.get("account_name")
        if not name and item.get("account_id"):
            account = BankAccount.objects.filter(pk=item["account_id"]).first()
            name = account.name if account else "?"
        lines.append(f"• Saldo de {escape(name)} em {item['date'][8:10]}/{item['date'][5:7]}/{item['date'][:4]}: "
                     f"{brl(item['amount'])}")
    updates = batch_service.planned_card_updates(batch)
    if updates:
        labels = {"closing_day": "fechamento dia", "due_day": "vencimento dia"}
        desc = " e ".join(f"{labels[k]} {v}" for k, v in updates.items())
        lines.append(f"• Ao confirmar, salvo no cartão: {desc}")
    for warning in batch.warnings or []:
        lines.append(f"⚠️ {escape(warning)}")
    lines.append("")
    lines.append("Nada foi gravado ainda. Peça ajustes no chat ou toque em Confirmar.")
    return "\n".join(lines), batch_keyboard(batch, t["included"])


STATUS_MARK = {
    StagedEntry.Match.NEW: "",
    StagedEntry.Match.DUPLICATE: " [já registrado]",
    StagedEntry.Match.WEAK: " [⚠️ possível duplicado]",
    StagedEntry.Match.CONFIRM_EXISTING: " [atualiza existente]",
}


def batch_items(batch):
    """Lista de itens (texto simples, pode ser longa: o cliente quebra em blocos)."""
    lines = [f"Itens do lote #{batch.pk}:"]
    for e in batch.entries.select_related("category", "from_account", "to_account").order_by("position"):
        mark = "✓" if e.include else "✗"
        inst = f" {e.installment_number}/{e.installments_total}" if e.installments_total else ""
        cat = e.category.name if e.category_id else (e.category_name or "sem categoria")
        if e.kind == StagedEntry.Kind.TRANSFER:
            src = e.from_account.name if e.from_account_id else e.from_account_name
            dst = e.to_account.name if e.to_account_id else e.to_account_name
            if e.to_card_id:
                cat = "pagamento de fatura"
            elif src and dst:
                cat = f"transferência: {src} → {dst}"
            else:
                cat = "transferência"
        elif e.kind == StagedEntry.Kind.INCOME:
            cat = f"receita, {cat}"
        sign = "-" if e.kind == StagedEntry.Kind.REFUND else ""
        lines.append(f"{mark} {e.position}. {e.date:%d/%m} {e.description}{inst} — {sign}{brl(e.amount)} "
                     f"({cat}){STATUS_MARK.get(e.match_status, '')}")
        if e.match_note and e.match_status != StagedEntry.Match.NEW:
            lines.append(f"     {e.match_note}")
    lines.append("")
    lines.append("✓ = será gravado, ✗ = ignorado. Para mudar, peça no chat (ex.: \"inclui o item 4\").")
    return "\n".join(lines)
