"""Ferramentas que montam lotes (rascunhos). Nada aqui grava Transaction/Purchase/
Transfer: isso só acontece em batch_service.commit, pelo botão Confirmar."""

import datetime as dt
from collections import Counter
from typing import Literal

from django.db import transaction
from django.db.models import Max
from pydantic import Field

from accounts.models import BankAccount, PaymentMethod
from core.models import Category, Entity

from .. import batch_service, dedup
from ..models import Attachment, ImportBatch, StagedEntry
from .registry import Tool, ToolError, ToolInput, parse_amount, parse_month, parse_signed_amount

EntryKind = Literal["EXPENSE", "INCOME", "REFUND", "INSTALLMENT_PURCHASE", "INSTALLMENT_CHARGE", "TRANSFER"]


class NewPaymentMethod(ToolInput):
    name: str = Field(description="Nome do cartão/método, ex.: 'Final 1234'.")
    type: Literal["CREDIT", "DEBIT", "PIX", "CASH", "TRANSFER", "BOLETO"] = "CREDIT"
    closing_day: int | None = Field(default=None, description="Cartão: dia do fechamento da fatura (1-31).")
    due_day: int | None = Field(default=None, description="Cartão: dia do vencimento da fatura (1-31).")
    bank_account_id: int | None = Field(default=None, description="Conta bancária existente à qual pertence.")
    new_bank_account_name: str | None = Field(
        default=None, description="Se a conta/banco também não existe: nome para criá-la, ex.: 'Banco X'."
    )


class NewCard(ToolInput):
    name: str = Field(description="Nome do cartão, no padrão dos já cadastrados, ex.: 'Final 1234 (adicional)'.")


class BalanceIn(ToolInput):
    account_id: int | None = Field(default=None, description="ID da conta ou caixinha cadastrada.")
    account_name: str | None = Field(
        default=None, description="Nome da caixinha ainda não cadastrada (criada dentro da conta do lote)."
    )
    amount: str = Field(description="Saldo no fim do dia `date` (pode ser negativo).")
    date: dt.date


class BatchMeta(ToolInput):
    kind: Literal["invoice", "statement", "receipt", "chat"] = Field(
        description="invoice = fatura de cartão; statement = extrato de conta; receipt = comprovante; chat = digitado."
    )
    title: str | None = Field(default=None, description="Título curto, ex.: 'Fatura Banco X nov/2026'.")
    payment_method_id: int | None = Field(
        default=None, description="Cartão/método padrão dos itens (obrigatório em fatura)."
    )
    new_payment_method: NewPaymentMethod | None = Field(
        default=None,
        description=("Use no lugar de payment_method_id quando o cartão/método do documento ainda não está "
                     "cadastrado: ele é criado quando o usuário confirmar o lote e vira o método padrão dos itens."),
    )
    additional_new_cards: list[NewCard] | None = Field(
        default=None,
        description=("Fatura com vários cartões: os outros cartões ainda não cadastrados. São criados na "
                     "confirmação, cobrados na fatura do cartão principal do lote."),
    )
    invoice_month: str | None = Field(default=None, description="Fatura: mês de VENCIMENTO, AAAA-MM.")
    invoice_total: str | None = Field(default=None, description="Fatura: valor total a pagar, ex.: 3250.10.")
    invoice_due_date: dt.date | None = Field(default=None, description="Fatura: data de vencimento.")
    invoice_closing_date: dt.date | None = Field(default=None, description="Fatura: data de fechamento.")
    account_id: int | None = Field(
        default=None, description="Extrato ou saldo informado: ID da conta bancária."
    )
    balance_amount: str | None = Field(
        default=None, description="Saldo da conta no fim de balance_date (pode ser negativo), ex.: 1520.33."
    )
    balance_date: dt.date | None = Field(default=None, description="Data do saldo informado.")
    opening_balance: str | None = Field(
        default=None, description="Extrato: saldo inicial do período (para conferir com as linhas e o saldo final)."
    )
    other_balances: list[BalanceIn] | None = Field(
        default=None, description="Saldos de outras contas ou caixinhas informados pelo usuário."
    )


class EntryIn(ToolInput):
    kind: EntryKind = Field(description=(
        "EXPENSE despesa; INCOME receita; REFUND estorno/crédito de compra; "
        "INSTALLMENT_PURCHASE compra parcelada nova (amount = valor TOTAL); "
        "INSTALLMENT_CHARGE linha 'parcela k/N' de fatura (amount = valor da parcela); "
        "TRANSFER pagamento de fatura de cartão ou transferência entre contas próprias (não é gasto)."
    ))
    description: str = Field(description="Descrição curta, ex.: 'Supermercado Costazul'.")
    amount: str = Field(description="Valor positivo com ponto decimal, ex.: 123.45.")
    date: dt.date = Field(description="Data da compra/pagamento.")
    category_id: int | None = Field(default=None, description="ID de categoria existente.")
    category_name: str | None = Field(default=None, description="Se não houver categoria adequada: nome da nova.")
    payment_method_id: int | None = Field(default=None, description="Método do item (padrão: o do lote).")
    payment_method_name: str | None = Field(
        default=None,
        description=("Cartão do item quando ele ainda não tem ID: o nome exato de um cartão proposto em "
                     "batch.new_payment_method ou batch.additional_new_cards."),
    )
    entity_id: int | None = Field(default=None, description="ID de entidade existente.")
    entity_name: str | None = Field(default=None, description="Nome do estabelecimento/pessoa, se não cadastrado.")
    installment_number: int | None = Field(default=None, description="k em 'parcela k/N'.")
    installments_total: int | None = Field(default=None, description="N (total de parcelas).")
    notes: str | None = Field(default=None, description="Observação curta, se ajudar o usuário.")
    external_ref: str | None = Field(
        default=None, description="Identificador do lançamento no banco, se houver (FITID do OFX)."
    )
    from_account_id: int | None = Field(default=None, description="TRANSFER: conta de onde saiu o dinheiro.")
    to_account_id: int | None = Field(default=None, description="TRANSFER: conta de destino (entre contas próprias).")
    from_account_name: str | None = Field(
        default=None, description="TRANSFER: caixinha de origem ainda não cadastrada (criada dentro da conta do lote)."
    )
    to_account_name: str | None = Field(
        default=None, description="TRANSFER: caixinha de destino ainda não cadastrada (criada dentro da conta do lote)."
    )
    to_card_id: int | None = Field(
        default=None, description="TRANSFER: cartão cuja fatura foi paga (em lote de fatura, padrão: o cartão do lote)."
    )
    paid_invoice_month: str | None = Field(
        default=None, description="TRANSFER de pagamento de fatura: mês de vencimento da fatura paga, AAAA-MM."
    )


class StageEntriesInput(ToolInput):
    batch_id: int | None = Field(
        default=None, description="Lote existente para acrescentar itens. Vazio: cria um lote novo."
    )
    batch: BatchMeta | None = Field(default=None, description="Dados do lote (obrigatório ao criar).")
    entries: list[EntryIn] = Field(
        default_factory=list, description="Itens a acrescentar (pode ser vazio se o lote só registra um saldo)."
    )


class EntryEdit(ToolInput):
    position: int = Field(description="Número do item no lote.")
    remove: bool = Field(default=False, description="Remove o item do lote.")
    include: bool | None = Field(
        default=None, description="Força incluir (true) ou ignorar (false) na gravação, ex.: duplicados."
    )
    kind: EntryKind | None = None
    description: str | None = None
    amount: str | None = None
    date: dt.date | None = None
    category_id: int | None = None
    category_name: str | None = None
    payment_method_id: int | None = None
    payment_method_name: str | None = None
    entity_id: int | None = None
    entity_name: str | None = None
    installment_number: int | None = None
    installments_total: int | None = None
    notes: str | None = None
    from_account_id: int | None = None
    to_account_id: int | None = None
    from_account_name: str | None = None
    to_account_name: str | None = None
    to_card_id: int | None = None
    paid_invoice_month: str | None = None


class EditStagedEntriesInput(ToolInput):
    batch_id: int
    edits: list[EntryEdit] = Field(default_factory=list)
    batch: BatchMeta | None = Field(default=None, description="Opcional: corrige os dados do lote.")


class BatchIdInput(ToolInput):
    batch_id: int


# ---------------------------------------------------------------------------

def _get_open_batch(batch_id, ctx):
    batch = ImportBatch.objects.filter(pk=batch_id, chat_id=ctx.chat_id).select_related(
        "payment_method", "attachment", "balance_account").first()
    if batch is None:
        raise ToolError(f"Lote #{batch_id} não encontrado.")
    if batch.status != ImportBatch.Status.STAGED:
        raise ToolError(f"Lote #{batch_id} está {batch.get_status_display().lower()} e não pode ser alterado. "
                        "Crie um lote novo se precisar.")
    return batch


def _check_fk(model, pk, label):
    if pk is None:
        return None
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        raise ToolError(f"{label} id={pk} não existe. Consulte get_reference_data.")
    return obj


def _check_card(pk):
    card = _check_fk(PaymentMethod, pk, "Cartão")
    if card is not None and card.type != "CREDIT":
        raise ToolError(f"to_card_id={pk} não é um cartão de crédito.")
    return card


def _apply_meta(batch, meta):
    batch.kind = meta.kind
    if meta.title:
        batch.title = meta.title[:200]
    if meta.payment_method_id is not None:
        batch.payment_method = _check_fk(PaymentMethod, meta.payment_method_id, "Método de pagamento")
        batch.new_payment_method = {}
    elif meta.new_payment_method is not None:
        new_pm = meta.new_payment_method
        for day in (new_pm.closing_day, new_pm.due_day):
            if day is not None and not 1 <= day <= 31:
                raise ToolError("closing_day e due_day devem estar entre 1 e 31.")
        _check_fk(BankAccount, new_pm.bank_account_id, "Conta bancária")
        existing = PaymentMethod.objects.filter(name__iexact=new_pm.name.strip(), active=True).first()
        if existing:
            raise ToolError(f"Já existe um método chamado '{existing.name}' (id={existing.pk}). "
                            "Use payment_method_id.")
        batch.payment_method = None
        batch.new_payment_method = new_pm.model_dump()
    if meta.additional_new_cards is not None:
        names = [c.name.strip() for c in meta.additional_new_cards]
        batch.additional_new_cards = [
            {"name": n} for n in names if not PaymentMethod.objects.filter(name__iexact=n).exists()]
    if meta.invoice_month:
        batch.invoice_year, batch.invoice_month = parse_month(meta.invoice_month)
    if meta.invoice_total:
        batch.invoice_total = parse_amount(meta.invoice_total)
    if meta.invoice_due_date:
        batch.invoice_due_date = meta.invoice_due_date
        if not meta.invoice_month:
            batch.invoice_year, batch.invoice_month = meta.invoice_due_date.year, meta.invoice_due_date.month
    if meta.invoice_closing_date:
        batch.invoice_closing_date = meta.invoice_closing_date
    if meta.account_id is not None:
        batch.balance_account = _check_fk(BankAccount, meta.account_id, "Conta bancária")
    if meta.balance_amount is not None:
        batch.balance_amount = parse_signed_amount(meta.balance_amount)
        if not (meta.balance_date or batch.balance_date):
            raise ToolError("balance_amount precisa de balance_date.")
    if meta.balance_date:
        batch.balance_date = meta.balance_date
    if meta.opening_balance is not None:
        batch.opening_balance = parse_signed_amount(meta.opening_balance)
    if meta.other_balances is not None:
        items = []
        for item in meta.other_balances:
            if bool(item.account_id) == bool(item.account_name):
                raise ToolError("Cada saldo em other_balances precisa de account_id OU account_name.")
            _check_fk(BankAccount, item.account_id, "Conta bancária")
            if item.account_name and not batch.balance_account_id and \
                    not BankAccount.objects.filter(name__iexact=item.account_name.strip()).exists():
                raise ToolError(f"Caixinha '{item.account_name}' não existe; informe batch.account_id "
                                "(a conta em que ela fica) para criá-la.")
            items.append({"account_id": item.account_id, "account_name": (item.account_name or "").strip(),
                          "amount": str(parse_signed_amount(item.amount)), "date": item.date.isoformat()})
        batch.other_balances = items
    if batch.balance_amount is not None and not batch.balance_account_id:
        raise ToolError("Saldo informado precisa de account_id (a conta bancária).")
    if batch.additional_new_cards and not (batch.payment_method_id or batch.new_payment_method):
        raise ToolError("additional_new_cards precisa do cartão principal: payment_method_id ou new_payment_method.")
    if batch.kind == ImportBatch.Kind.INVOICE and not (batch.payment_method_id or batch.new_payment_method):
        raise ToolError("Lote de fatura precisa de payment_method_id (o cartão) ou new_payment_method.")


def _validate_entry(entry, batch):
    k, n = entry.installment_number, entry.installments_total
    if entry.kind == "INSTALLMENT_CHARGE" and not (k and n and 1 <= k <= n):
        raise ToolError("INSTALLMENT_CHARGE precisa de installment_number (k) e installments_total (N), com 1 <= k <= N.")
    if entry.kind == "INSTALLMENT_PURCHASE" and not (n and n >= 2):
        raise ToolError("INSTALLMENT_PURCHASE precisa de installments_total >= 2.")
    if entry.kind == "TRANSFER":
        # Em lote de fatura o destino padrão é o cartão do lote (resolvido na confirmação)
        implied_card = batch.kind == ImportBatch.Kind.INVOICE
        if not (entry.from_account_id or entry.to_account_id or entry.to_card_id
                or entry.from_account_name or entry.to_account_name or implied_card):
            raise ToolError(f"TRANSFER '{entry.description}' precisa de from_account_id, to_account_id ou to_card_id.")
        if entry.from_account_id and entry.from_account_id == entry.to_account_id:
            raise ToolError("TRANSFER com a mesma conta na origem e no destino.")


def _entry_out(e):
    out = {
        "position": e.position, "kind": e.kind, "description": e.description, "amount": e.amount,
        "date": e.date, "match_status": e.match_status, "include": e.include,
    }
    if e.installments_total:
        out["installment"] = f"{e.installment_number}/{e.installments_total}"
    if e.match_note:
        out["match_note"] = e.match_note
    return out


def _convert_anticipated(batch):
    """Parcelas da mesma compra cobradas juntas viram despesas simples.
    Retorna as posições convertidas."""
    converted = []
    for group in dedup.anticipated_installment_groups(batch):
        for e in group:
            tag = f"(parcela {e.installment_number}/{e.installments_total} antecipada)"
            e.kind = StagedEntry.Kind.EXPENSE
            if tag not in e.description:
                e.description = f"{e.description} {tag}"[:200]
            e.installment_number = None
            e.installments_total = None
            e.save()
            converted.append(e)
    return converted


def _reclassify(batch, entries):
    # Solta os vínculos antigos destes itens antes: senão cada item "reserva" o
    # próprio lançamento existente e deixa de reconhecê-lo como duplicado.
    StagedEntry.objects.filter(pk__in=[e.pk for e in entries]).update(
        matched_transaction=None, matched_installment=None, matched_transfer=None)
    claimed_tx, claimed_inst = dedup._claimed_ids(batch)
    for entry in entries:
        entry.refresh_from_db()
        dedup.classify_entry(batch, entry, claimed_tx, claimed_inst)
        entry.save()


def _batch_view(batch, entries):
    """Visão compacta: totais + só os itens que merecem atenção."""
    totals = batch_service.batch_totals(batch)
    by_status = Counter(e.match_status for e in batch.entries.all())
    view = {
        "batch_id": batch.pk, "version": batch.version, "kind": batch.kind, "title": batch.title,
        "payment_method_id": batch.payment_method_id,
        "invoice_month": f"{batch.invoice_year}-{batch.invoice_month:02d}" if batch.invoice_year else None,
        "invoice_total": batch.invoice_total, "totals": totals,
        "entries_by_status": dict(by_status), "warnings": batch.warnings,
        "entries": [_entry_out(e) for e in entries],
    }
    if batch.new_payment_method:
        view["new_payment_method_on_confirm"] = batch.new_payment_method
    if batch.additional_new_cards:
        view["additional_new_cards_on_confirm"] = [c["name"] for c in batch.additional_new_cards]
    new_pots = sorted({n for e in batch.entries.all() for n in (e.from_account_name, e.to_account_name) if n}
                      | {b["account_name"] for b in batch.other_balances or [] if b.get("account_name")})
    if new_pots:
        view["new_pots_on_confirm"] = new_pots
    if batch.other_balances:
        view["other_balances"] = batch.other_balances
    if batch.balance_amount is not None:
        view["balance"] = {"account_id": batch.balance_account_id, "amount": batch.balance_amount,
                           "date": batch.balance_date}
    return view


def _finish(batch, touched):
    """Passos comuns depois de criar/alterar itens. Retorna itens a destacar."""
    converted = _convert_anticipated(batch)
    dedup.assign_external_ids(batch)
    by_pk = {e.pk: e for e in [*touched, *converted]}
    _reclassify(batch, list(by_pk.values()))
    batch.warnings = dedup.batch_warnings(batch)
    batch.version += 1
    batch.save(update_fields=["warnings", "version", "updated_at"])
    converted_pks = {e.pk for e in converted}
    return list(by_pk.values()), converted_pks


def _proposed_card_names(batch):
    names = [c["name"] for c in batch.additional_new_cards or []]
    if batch.new_payment_method:
        names.append(batch.new_payment_method["name"])
    return names


def _resolve_method(batch, method_id, method_name):
    """(PaymentMethod | None, nome pendente) para um item."""
    pm = _check_fk(PaymentMethod, method_id, "Método de pagamento")
    name = (method_name or "").strip()
    if pm or not name:
        return pm, ""
    existing = PaymentMethod.objects.filter(name__iexact=name, active=True).first()
    if existing:
        return existing, ""
    proposed = _proposed_card_names(batch)
    match = next((p for p in proposed if p.lower() == name.lower()), None)
    if match is None:
        raise ToolError(f"payment_method_name '{name}' não é um cartão cadastrado nem proposto neste lote "
                        f"(propostos: {proposed or 'nenhum'}). Inclua-o em batch.additional_new_cards.")
    return None, match[:100]


def _resolve_account(batch, account_id, account_name, label):
    """(BankAccount | None, nome pendente). Nome pendente vira caixinha da conta do lote."""
    account = _check_fk(BankAccount, account_id, label)
    name = (account_name or "").strip()
    if account or not name:
        return account, ""
    qs = BankAccount.objects.filter(name__iexact=name)
    existing = (qs.filter(parent=batch.balance_account).first() if batch.balance_account_id else None) or qs.first()
    if existing:
        return existing, ""
    if not batch.balance_account_id:
        raise ToolError(f"{label} '{name}' não existe; informe batch.account_id (a conta em que a caixinha "
                        "fica) para ela ser criada na confirmação.")
    return None, name[:100]


def _build_entry(batch, item, position):
    paid_year = paid_month = None
    if item.paid_invoice_month:
        paid_year, paid_month = parse_month(item.paid_invoice_month)
    to_card = _check_card(item.to_card_id)
    method, method_name = _resolve_method(batch, item.payment_method_id, item.payment_method_name)
    from_account, from_name = _resolve_account(batch, item.from_account_id, item.from_account_name, "Conta de origem")
    to_account, to_name = _resolve_account(batch, item.to_account_id, item.to_account_name, "Conta de destino")
    entry = StagedEntry(
        batch=batch, position=position, kind=item.kind,
        description=item.description.strip()[:200], amount=parse_amount(item.amount), date=item.date,
        category=_check_fk(Category, item.category_id, "Categoria"),
        category_name=(item.category_name or "").strip()[:100],
        payment_method=method, payment_method_name=method_name,
        from_account_name=from_name, to_account_name=to_name,
        entity=_check_fk(Entity, item.entity_id, "Entidade"),
        entity_name=(item.entity_name or "").strip()[:200],
        installment_number=item.installment_number, installments_total=item.installments_total,
        notes=(item.notes or "").strip()[:200], external_ref=(item.external_ref or "").strip()[:100],
        from_account=from_account, to_account=to_account,
        to_card=to_card, paid_invoice_year=paid_year, paid_invoice_month=paid_month,
    )
    _validate_entry(entry, batch)
    return entry


def stage_entries(args, ctx):
    with transaction.atomic():
        if args.batch_id:
            batch = _get_open_batch(args.batch_id, ctx)
            if args.batch:
                _apply_meta(batch, args.batch)
        else:
            if not args.batch:
                raise ToolError("Para criar um lote, informe `batch` (pelo menos kind).")
            batch = ImportBatch(conversation=ctx.conversation, chat_id=ctx.chat_id)
            _apply_meta(batch, args.batch)
            if batch.kind in (ImportBatch.Kind.INVOICE, ImportBatch.Kind.STATEMENT, ImportBatch.Kind.RECEIPT):
                batch.attachment = Attachment.objects.filter(
                    conversation=ctx.conversation).order_by("-created_at").first()
        if not args.entries and batch.balance_amount is None and not batch.other_balances:
            raise ToolError("Nenhum item informado.")
        batch.save()

        next_pos = (batch.entries.aggregate(m=Max("position"))["m"] or 0) + 1
        new_entries = []
        for item in args.entries:
            entry = _build_entry(batch, item, next_pos)
            entry.save()
            new_entries.append(entry)
            next_pos += 1

        touched, converted = _finish(batch, new_entries)

    flagged = [e for e in touched if e.match_status != StagedEntry.Match.NEW or e.pk in converted]
    view = _batch_view(batch, flagged)
    view["added"] = len(new_entries)
    if new_entries:
        view["added_positions"] = [new_entries[0].position, new_entries[-1].position]
    view["entries_note"] = ("`entries` lista só itens que merecem atenção (já registrados, possíveis "
                            "duplicados, parcelas antecipadas convertidas em despesa). Os demais entraram como novos.")
    view["next_step"] = "Quando terminar de acrescentar itens, chame present_batch para o usuário confirmar."
    return view


def edit_staged_entries(args, ctx):
    with transaction.atomic():
        batch = _get_open_batch(args.batch_id, ctx)
        if args.batch:
            _apply_meta(batch, args.batch)
            batch.save()
        by_pos = {e.position: e for e in batch.entries.all()}
        previous = {e.pk: (e.match_status, e.include) for e in by_pos.values()}
        changed, forced_include = [], {}
        for edit in args.edits:
            entry = by_pos.get(edit.position)
            if entry is None:
                raise ToolError(f"Item {edit.position} não existe no lote #{batch.pk}.")
            if edit.remove:
                entry.delete()
                continue
            for fld in ("kind", "description", "date", "category_name", "entity_name",
                        "installment_number", "installments_total", "notes"):
                value = getattr(edit, fld)
                if value is not None:
                    setattr(entry, fld, value.strip() if isinstance(value, str) else value)
            if edit.amount is not None:
                entry.amount = parse_amount(edit.amount)
            if edit.category_id is not None:
                entry.category = _check_fk(Category, edit.category_id, "Categoria")
                entry.category_name = ""
            if edit.payment_method_id is not None or edit.payment_method_name is not None:
                entry.payment_method, entry.payment_method_name = _resolve_method(
                    batch, edit.payment_method_id, edit.payment_method_name)
            if edit.entity_id is not None:
                entry.entity = _check_fk(Entity, edit.entity_id, "Entidade")
            if edit.from_account_id is not None or edit.from_account_name is not None:
                entry.from_account, entry.from_account_name = _resolve_account(
                    batch, edit.from_account_id, edit.from_account_name, "Conta de origem")
            if edit.to_account_id is not None or edit.to_account_name is not None:
                entry.to_account, entry.to_account_name = _resolve_account(
                    batch, edit.to_account_id, edit.to_account_name, "Conta de destino")
            if edit.to_card_id is not None:
                entry.to_card = _check_card(edit.to_card_id)
            if edit.paid_invoice_month is not None:
                entry.paid_invoice_year, entry.paid_invoice_month = parse_month(edit.paid_invoice_month)
            _validate_entry(entry, batch)
            entry.save()
            changed.append(entry)
            if edit.include is not None:
                forced_include[entry.pk] = edit.include

        # Mudança nos dados do lote (cartão, mês) pode mudar a classificação de tudo
        touched = list(batch.entries.all()) if args.batch else changed
        touched, _converted = _finish(batch, touched)
        for entry in touched:
            desired = forced_include.get(entry.pk)
            if desired is None and previous.get(entry.pk, (None, None))[0] == entry.match_status:
                desired = previous[entry.pk][1]  # mantém escolha anterior de incluir/ignorar
            if desired is not None and desired != entry.include:
                entry.include = desired
                entry.save(update_fields=["include"])

    changed_pks = {e.pk for e in changed}
    view = _batch_view(batch, [e for e in touched if e.pk in changed_pks])
    view["next_step"] = "Chame present_batch para mostrar o resumo atualizado ao usuário."
    return view


def present_batch(args, ctx):
    batch = _get_open_batch(args.batch_id, ctx)
    if not batch.entries.exists() and batch.balance_amount is None and not batch.other_balances:
        raise ToolError("Lote vazio.")
    if args.batch_id not in ctx.batches_to_present:
        ctx.batches_to_present.append(args.batch_id)
    view = _batch_view(batch, [])
    view.pop("entries")
    view["card_updates_on_confirm"] = batch_service.planned_card_updates(batch)
    view["status"] = ("O resumo com botões Confirmar/Descartar será enviado ao usuário logo após sua "
                      "resposta. Nada foi gravado ainda. Mencione diferenças e itens duplicados, se houver.")
    return view


def get_batch(args, ctx):
    batch = ImportBatch.objects.filter(pk=args.batch_id, chat_id=ctx.chat_id).first()
    if batch is None:
        raise ToolError(f"Lote #{args.batch_id} não encontrado.")
    entries = []
    for e in batch.entries.select_related("category").all():
        out = _entry_out(e)
        out["category"] = e.category.name if e.category_id else (e.category_name or None)
        entries.append(out)
    view = _batch_view(batch, [])
    view["entries"] = entries
    view["status"] = batch.status
    return view


TOOLS = [
    Tool(
        name="stage_entries",
        description=(
            "Cria um lote (rascunho) de lançamentos ou acrescenta itens a um lote existente. NÃO grava "
            "nada: o usuário confirma depois. O servidor marca automaticamente itens já registrados "
            "(match_status=duplicate, include=false) e possíveis duplicados (weak_match). Para faturas e "
            "extratos longos, chame várias vezes com o mesmo batch_id (até uns 80 itens por chamada). "
            "Também registra o saldo de uma conta (batch.account_id + balance_amount + balance_date)."
        ),
        input_model=StageEntriesInput,
        handler=stage_entries,
    ),
    Tool(
        name="edit_staged_entries",
        description=(
            "Altera, inclui/ignora ou remove itens de um lote ainda não confirmado (pelo número do item), "
            "e opcionalmente corrige os dados do lote. Use para ajustes pedidos pelo usuário."
        ),
        input_model=EditStagedEntriesInput,
        handler=edit_staged_entries,
    ),
    Tool(
        name="present_batch",
        description=(
            "Envia ao usuário o resumo do lote com os botões Confirmar / Ver itens / Descartar. Chame "
            "quando o lote estiver completo (e de novo após ajustes). Retorna totais e a conferência com "
            "o total da fatura."
        ),
        input_model=BatchIdInput,
        handler=present_batch,
    ),
    Tool(
        name="get_batch",
        description="Mostra um lote e todos os seus itens (qualquer status).",
        input_model=BatchIdInput,
        handler=get_batch,
    ),
]
