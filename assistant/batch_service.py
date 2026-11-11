"""Gravação, descarte e desfazer de lotes. Só é chamado por ação do usuário
(botão Confirmar / Descartar, comando /desfazer), nunca pela IA."""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from accounts.models import BalanceSnapshot, BankAccount, PaymentMethod
from core.models import Category, Entity
from financial.forecast import REFUND_CATEGORY_NAME, invoice_card
from financial.models import Installment, Purchase, Transaction, Transfer

from .dedup import assign_external_ids, first_invoice_month_for, installment_purchase_external_id
from .models import ImportBatch, StagedEntry

logger = logging.getLogger(__name__)

FALLBACK_CATEGORY_NAME = "Outros"


class CommitError(Exception):
    pass


@dataclass
class CommitResult:
    ok: bool
    message: str
    created: int = 0
    confirmed_existing: int = 0
    skipped: int = 0
    card_updates: list = field(default_factory=list)
    balance_recorded: bool = False


def _category_for(entry):
    if entry.kind == StagedEntry.Kind.REFUND:
        cat, _ = Category.objects.get_or_create(
            name=REFUND_CATEGORY_NAME, defaults={"type": Category.TypeChoices.BOTH, "active": True}
        )
        return cat
    if entry.category_id:
        return entry.category
    if entry.category_name:
        existing = Category.objects.filter(name__iexact=entry.category_name.strip(), active=True).first()
        if existing:
            return existing
        cat_type = Category.TypeChoices.INCOME if entry.kind == StagedEntry.Kind.INCOME else Category.TypeChoices.EXPENSE
        return Category.objects.create(name=entry.category_name.strip()[:100], type=cat_type, active=True)
    cat, _ = Category.objects.get_or_create(
        name=FALLBACK_CATEGORY_NAME, defaults={"type": Category.TypeChoices.BOTH, "active": True}
    )
    return cat


def _entity_for(entry):
    if entry.entity_id:
        return entry.entity
    name = (entry.entity_name or "").strip()
    if not name:
        return None
    existing = Entity.objects.filter(name__iexact=name).first()
    if existing:
        return existing
    return Entity.objects.create(name=name[:200], type=Entity.TypeChoices.SUPPLIER, active=True)


def planned_card_updates(batch):
    """Fechamento/vencimento que a fatura revela e o cartão ainda não tem.
    Mostrado no resumo do lote e aplicado no commit (o toque em Confirmar aprova)."""
    pm = invoice_card(batch.payment_method) if batch.payment_method_id else None
    if not pm or pm.type != "CREDIT":
        return {}
    updates = {}
    if not pm.closing_day and batch.invoice_closing_date:
        updates["closing_day"] = batch.invoice_closing_date.day
    if not pm.due_day and batch.invoice_due_date:
        updates["due_day"] = batch.invoice_due_date.day
    return updates


def _create_payment_method(batch, undo_data):
    """Cria o cartão/método proposto no lote (aprovado pelo toque em Confirmar)."""
    spec = batch.new_payment_method
    account = None
    if spec.get("bank_account_id"):
        account = BankAccount.objects.filter(pk=spec["bank_account_id"]).first()
    elif spec.get("new_bank_account_name"):
        name = spec["new_bank_account_name"].strip()[:100]
        account = BankAccount.objects.filter(name__iexact=name).first()
        if account is None:
            account = BankAccount.objects.create(name=name, bank=name, type=BankAccount.TypeChoices.CHECKING)
            undo_data.setdefault("created_bank_accounts", []).append(account.pk)
    closing_day, due_day = spec.get("closing_day"), spec.get("due_day")
    if spec.get("type") == "CREDIT":
        closing_day = closing_day or (batch.invoice_closing_date.day if batch.invoice_closing_date else None)
        due_day = due_day or (batch.invoice_due_date.day if batch.invoice_due_date else None)
    pm = PaymentMethod.objects.create(
        name=spec["name"].strip()[:100], type=spec.get("type") or "CREDIT", bank_account=account,
        closing_day=closing_day, due_day=due_day,
    )
    undo_data.setdefault("created_payment_methods", []).append(pm.pk)
    batch.payment_method = pm
    batch.save(update_fields=["payment_method", "updated_at"])
    return pm


def _create_additional_cards(batch, undo_data):
    """Outros cartões da mesma fatura: cobrados na fatura do cartão principal do lote."""
    main = invoice_card(batch.payment_method)
    for spec in batch.additional_new_cards or []:
        name = spec["name"].strip()[:100]
        if PaymentMethod.objects.filter(name__iexact=name).exists():
            continue
        pm = PaymentMethod.objects.create(
            name=name, type=PaymentMethod.TypeChoices.CREDIT, bank_account=main.bank_account, billing_card=main,
        )
        undo_data.setdefault("created_payment_methods", []).append(pm.pk)


def _resolve_account_name(batch, name, undo_data):
    """Conta pelo nome; se não existir, cria como caixinha da conta do lote."""
    name = name.strip()[:100]
    parent = batch.balance_account
    qs = BankAccount.objects.filter(name__iexact=name)
    account = (qs.filter(parent=parent).first() if parent else None) or qs.first()
    if account:
        return account
    if parent is None:
        raise CommitError(f"Não sei em qual conta criar a caixinha '{name}': o lote não tem conta.")
    account = BankAccount.objects.create(
        name=name, bank=parent.bank, type=BankAccount.TypeChoices.INVESTMENT, parent=parent)
    undo_data.setdefault("created_bank_accounts", []).append(account.pk)
    return account


def _resolve_entry_refs(batch, entry, undo_data):
    """Troca nomes (cartão proposto, caixinha nova) pelos registros, já criados."""
    fields = []
    if entry.payment_method_name and not entry.payment_method_id:
        pm = PaymentMethod.objects.filter(name__iexact=entry.payment_method_name.strip()).first()
        if pm is None:
            raise CommitError(f"Item {entry.position}: cartão '{entry.payment_method_name}' não foi cadastrado.")
        entry.payment_method = pm
        fields.append("payment_method")
    for side in ("from_account", "to_account"):
        name = getattr(entry, f"{side}_name")
        if name and not getattr(entry, f"{side}_id"):
            setattr(entry, side, _resolve_account_name(batch, name, undo_data))
            fields.append(side)
    if fields:
        entry.save(update_fields=fields)


def _record_balance(batch, account, when, amount, undo_data):
    existing = BalanceSnapshot.objects.filter(account=account, date=when).first()
    undo_data.setdefault("snapshots", []).append({
        "account_id": account.pk, "date": when.isoformat(),
        "previous_balance": str(existing.balance) if existing else None,
        "previous_source": existing.source if existing else None,
    })
    source = (BalanceSnapshot.SourceChoices.STATEMENT if batch.kind == ImportBatch.Kind.STATEMENT
              else BalanceSnapshot.SourceChoices.ASSISTANT)
    BalanceSnapshot.objects.update_or_create(
        account=account, date=when,
        defaults={"balance": amount, "source": source, "notes": f"Lote #{batch.pk} do assistente"},
    )


def _free_external_id(model, external_id):
    if external_id and not model.objects.filter(external_id=external_id).exists():
        return external_id
    return None


def _notes(batch, entry, extra=""):
    parts = [f"Importado pelo assistente (lote #{batch.pk})"]
    if extra:
        parts.append(extra)
    if entry.notes:
        parts.append(entry.notes)
    return ". ".join(parts)


def _commit_transfer(batch, entry, result):
    if entry.match_status == StagedEntry.Match.CONFIRM_EXISTING and entry.matched_transfer_id:
        tr = entry.matched_transfer
        entry.previous_state = {
            "transfer": {
                "from_account_id": tr.from_account_id, "to_account_id": tr.to_account_id,
                "to_card_id": tr.to_card_id, "invoice_year": tr.invoice_year,
                "invoice_month": tr.invoice_month,
            }
        }
        tr.from_account_id = tr.from_account_id or entry.from_account_id
        tr.to_account_id = tr.to_account_id or entry.to_account_id
        tr.to_card_id = tr.to_card_id or entry.to_card_id
        if not tr.invoice_month and entry.paid_invoice_month:
            tr.invoice_year, tr.invoice_month = entry.paid_invoice_year, entry.paid_invoice_month
        tr.save()
        entry.previous_state["paid_installments"] = tr.mark_invoice_paid()
        entry.save(update_fields=["previous_state"])
        result.confirmed_existing += 1
        return

    to_card = entry.to_card
    if to_card is None and not entry.to_account_id and batch.kind == ImportBatch.Kind.INVOICE:
        to_card = batch.payment_method  # pagamento listado na fatura: é deste cartão
    if to_card is not None:
        to_card = invoice_card(to_card)  # a fatura é do cartão principal
    if not (entry.from_account_id or entry.to_account_id or to_card):
        raise CommitError(f"Item {entry.position} ({entry.description}): transferência sem conta nem cartão.")
    tr = Transfer.objects.create(
        date=entry.date,
        amount=entry.amount,
        description=entry.description[:200],
        from_account=entry.from_account,
        to_account=entry.to_account,
        to_card=to_card,
        invoice_year=entry.paid_invoice_year,
        invoice_month=entry.paid_invoice_month,
        external_id=_free_external_id(Transfer, entry.external_id),
        notes=_notes(batch, entry),
    )
    entry.committed_transfer = tr
    entry.previous_state = {"paid_installments": tr.mark_invoice_paid()}
    entry.save(update_fields=["committed_transfer", "previous_state"])
    result.created += 1


def _batch_invoice_month(batch):
    if batch.kind == ImportBatch.Kind.INVOICE and batch.invoice_year and batch.invoice_month:
        return date(batch.invoice_year, batch.invoice_month, 1)
    return None


def _stamp_existing(batch, entry):
    """Item ignorado por já estar registrado: se veio de uma fatura, anota no
    lançamento existente em qual fatura ele foi cobrado (a previsão fica exata)."""
    invoice_month = _batch_invoice_month(batch)
    tx = entry.matched_transaction
    if not (invoice_month and tx and entry.match_status == StagedEntry.Match.DUPLICATE):
        return
    if tx.payment_method.type != "CREDIT" or tx.invoice_month == invoice_month:
        return
    entry.previous_state = {"invoice_month": tx.invoice_month.isoformat() if tx.invoice_month else None}
    entry.save(update_fields=["previous_state"])
    tx.invoice_month = invoice_month
    tx.save(update_fields=["invoice_month", "updated_at"])


def _commit_entry(batch, entry, result):
    if entry.kind == StagedEntry.Kind.TRANSFER:
        _commit_transfer(batch, entry, result)
        return

    pm = entry.payment_method or batch.payment_method
    if pm is None:
        raise CommitError(f"Item {entry.position} ({entry.description}) está sem método de pagamento.")

    if entry.match_status == StagedEntry.Match.CONFIRM_EXISTING and entry.matched_transaction_id:
        tx = entry.matched_transaction
        entry.previous_state = {
            "confirmed": tx.confirmed, "amount": str(tx.amount),
            "date": tx.date.isoformat(), "description": tx.description,
        }
        tx.confirmed = True
        tx.amount = entry.amount
        tx.date = entry.date
        tx.save(update_fields=["confirmed", "amount", "date", "updated_at"])
        entry.save(update_fields=["previous_state"])
        result.confirmed_existing += 1
        return

    category = _category_for(entry)
    entity = _entity_for(entry)

    if entry.kind in (StagedEntry.Kind.EXPENSE, StagedEntry.Kind.INCOME, StagedEntry.Kind.REFUND):
        tx = Transaction.objects.create(
            type="EXPENSE" if entry.kind == StagedEntry.Kind.EXPENSE else "INCOME",
            description=entry.description[:200],
            amount=entry.amount,
            date=entry.date,
            category=category,
            payment_method=pm,
            entity=entity,
            confirmed=True,
            invoice_month=_batch_invoice_month(batch) if pm.type == "CREDIT" else None,
            external_id=_free_external_id(Transaction, entry.external_id),
            notes=_notes(batch, entry),
        )
        entry.committed_transaction = tx
        entry.save(update_fields=["committed_transaction"])
        result.created += 1
        return

    if entry.kind == StagedEntry.Kind.INSTALLMENT_PURCHASE:
        n = entry.installments_total or 1
        purchase = Purchase.objects.create(
            description=entry.description[:200],
            total_amount=entry.amount,
            purchase_date=entry.date,
            number_of_installments=n,
            category=category,
            payment_method=pm,
            entity=entity,
            notes=_notes(batch, entry),
        )
        entry.committed_purchase = purchase
        entry.save(update_fields=["committed_purchase"])
        result.created += 1
        return

    if entry.kind == StagedEntry.Kind.INSTALLMENT_CHARGE:
        k = entry.installment_number or 1
        n = entry.installments_total or k
        fim = first_invoice_month_for(batch, entry)
        ext = (installment_purchase_external_id(invoice_card(pm).pk, entry.description, n, entry.amount, fim)
               if fim else None)
        purchase = Purchase.objects.create(
            description=entry.description[:200],
            total_amount=(Decimal(entry.amount) * n).quantize(Decimal("0.01")),
            purchase_date=entry.date,
            number_of_installments=n,
            category=category,
            payment_method=pm,
            entity=entity,
            first_invoice_month=fim,
            external_id=_free_external_id(Purchase, ext),
            notes=_notes(batch, entry, f"Fatura: parcela {k}/{n}"),
        )
        if k > 1:
            purchase.installments.filter(installment_number__lt=k).update(paid=True)
        entry.committed_purchase = purchase
        entry.save(update_fields=["committed_purchase"])
        result.created += 1
        return

    raise CommitError(f"Tipo de item desconhecido: {entry.kind}")


def commit(batch_id, version):
    """Grava o lote. Seguro contra toque duplo e contra lote alterado depois do resumo."""
    locked = ImportBatch.objects.filter(
        pk=batch_id, status=ImportBatch.Status.STAGED, version=version
    ).update(status=ImportBatch.Status.COMMITTING)
    if not locked:
        batch = ImportBatch.objects.filter(pk=batch_id).first()
        if batch is None:
            return CommitResult(False, "Lote não encontrado.")
        if batch.status != ImportBatch.Status.STAGED:
            return CommitResult(False, f"Este lote já está {batch.get_status_display().lower()}.")
        return CommitResult(False, "O lote foi alterado depois deste resumo. Use o resumo mais recente.")

    batch = ImportBatch.objects.select_related("payment_method__billing_card", "balance_account").get(pk=batch_id)
    result = CommitResult(True, "")
    try:
        with transaction.atomic():
            undo_data = {}
            if batch.new_payment_method and not batch.payment_method_id:
                _create_payment_method(batch, undo_data)
            if batch.additional_new_cards and batch.payment_method_id:
                _create_additional_cards(batch, undo_data)
            if undo_data.get("created_payment_methods"):
                assign_external_ids(batch)  # as chaves das linhas dependem do id do cartão
            entries = batch.entries.select_related(
                "payment_method", "category", "entity", "matched_transaction__payment_method", "matched_transfer",
                "from_account", "to_account", "to_card",
            ).order_by("position")
            for entry in entries:
                if not entry.include:
                    result.skipped += 1
                    _stamp_existing(batch, entry)
                    continue
                _resolve_entry_refs(batch, entry, undo_data)
                _commit_entry(batch, entry, result)

            updates = planned_card_updates(batch)
            if updates:
                undo_data["card_fields"] = list(updates.keys())
                for attr, value in updates.items():
                    setattr(batch.payment_method, attr, value)
                batch.payment_method.save(update_fields=[*updates.keys(), "updated_at"])
                result.card_updates = [f"{k}={v}" for k, v in updates.items()]

            if batch.balance_account_id and batch.balance_amount is not None and batch.balance_date:
                _record_balance(batch, batch.balance_account, batch.balance_date, batch.balance_amount, undo_data)
                result.balance_recorded = True
            for item in batch.other_balances or []:
                account = (BankAccount.objects.filter(pk=item["account_id"]).first() if item.get("account_id")
                           else _resolve_account_name(batch, item["account_name"], undo_data))
                if account is None:
                    raise CommitError("Conta de um dos saldos informados não existe mais.")
                _record_balance(batch, account, date.fromisoformat(item["date"]), Decimal(item["amount"]), undo_data)
                result.balance_recorded = True

            batch.undo_data = undo_data
            batch.status = ImportBatch.Status.CONFIRMED
            batch.committed_at = timezone.now()
            batch.save(update_fields=["undo_data", "status", "committed_at", "updated_at"])
    except Exception as exc:
        ImportBatch.objects.filter(pk=batch_id).update(status=ImportBatch.Status.STAGED)
        if isinstance(exc, CommitError):
            return CommitResult(False, str(exc))
        logger.exception("Erro ao gravar lote %s", batch_id)
        return CommitResult(False, "Erro inesperado ao gravar o lote. Nada foi gravado.")

    parts = [f"{result.created} lançamento(s) gravado(s)"]
    if result.confirmed_existing:
        parts.append(f"{result.confirmed_existing} previsto(s) confirmado(s)")
    if result.skipped:
        parts.append(f"{result.skipped} ignorado(s)")
    if result.balance_recorded:
        parts.append("saldo registrado")
    result.message = ", ".join(parts) + "."
    return result


def discard(batch_id, version=None):
    qs = ImportBatch.objects.filter(pk=batch_id, status=ImportBatch.Status.STAGED)
    if version is not None:
        qs = qs.filter(version=version)
    return bool(qs.update(status=ImportBatch.Status.DISCARDED))


def undo(batch_id):
    """Desfaz um lote confirmado: apaga o que foi criado e restaura o que foi alterado."""
    batch = ImportBatch.objects.select_related("payment_method__billing_card").filter(
        pk=batch_id, status=ImportBatch.Status.CONFIRMED).first()
    if batch is None:
        return CommitResult(False, "Não há lote confirmado para desfazer.")
    removed = 0
    with transaction.atomic():
        for entry in batch.entries.select_related(
            "committed_transaction", "committed_purchase", "committed_transfer",
            "matched_transaction", "matched_transfer",
        ):
            state = entry.previous_state or {}
            if state.get("paid_installments"):
                Installment.objects.filter(pk__in=state["paid_installments"]).update(paid=False)
            if entry.committed_transaction_id:
                entry.committed_transaction.delete()
                removed += 1
            if entry.committed_purchase_id:
                entry.committed_purchase.delete()
                removed += 1
            if entry.committed_transfer_id:
                entry.committed_transfer.delete()
                removed += 1
            if "confirmed" in state and entry.matched_transaction_id:
                tx = entry.matched_transaction
                tx.confirmed = state.get("confirmed", False)
                tx.amount = Decimal(state["amount"])
                tx.date = date.fromisoformat(state["date"])
                tx.save(update_fields=["confirmed", "amount", "date", "updated_at"])
            if "invoice_month" in state and entry.matched_transaction_id:
                tx = entry.matched_transaction
                tx.invoice_month = date.fromisoformat(state["invoice_month"]) if state["invoice_month"] else None
                tx.save(update_fields=["invoice_month", "updated_at"])
            if "transfer" in state and entry.matched_transfer_id:
                tr = entry.matched_transfer
                for attr, value in state["transfer"].items():
                    setattr(tr, attr, value)
                tr.save()
            if state:
                # update direto: o objeto em memória ainda aponta para registros apagados
                StagedEntry.objects.filter(pk=entry.pk).update(previous_state={})

        undo_data = batch.undo_data or {}
        for previous in undo_data.get("snapshots", []):
            snap = BalanceSnapshot.objects.filter(account_id=previous["account_id"], date=previous["date"]).first()
            if snap and previous["previous_balance"] is None:
                snap.delete()
            elif snap:
                snap.balance = Decimal(previous["previous_balance"])
                snap.source = previous["previous_source"]
                snap.save(update_fields=["balance", "source", "updated_at"])
        if undo_data.get("card_fields") and batch.payment_method_id:
            card = invoice_card(batch.payment_method)
            for attr in undo_data["card_fields"]:
                setattr(card, attr, None)
            card.save(update_fields=[*undo_data["card_fields"], "updated_at"])
        # Cartões/contas criados pelo lote: remove (do mais novo para o mais antigo)
        # se nada mais passou a usá-los
        for model, key in ((PaymentMethod, "created_payment_methods"), (BankAccount, "created_bank_accounts")):
            for pk in reversed(undo_data.get(key, [])):
                try:
                    with transaction.atomic():
                        model.objects.filter(pk=pk).delete()
                except ProtectedError:
                    pass

        batch.status = ImportBatch.Status.UNDONE
        batch.undo_data = {}
        batch.save(update_fields=["status", "undo_data", "updated_at"])
    return CommitResult(True, f"Lote #{batch.pk} desfeito: {removed} registro(s) removido(s).")


def batch_totals(batch):
    """Números do resumo: novos, duplicados, estornos e as conferências (soma da
    fatura, subtotal por cartão, saldo do extrato)."""
    entries = list(batch.entries.select_related("payment_method"))
    K = StagedEntry.Kind
    included = [e for e in entries if e.include]
    excluded = [e for e in entries if not e.include]

    def total(items, kinds=None, exclude_kinds=()):
        return sum((Decimal(e.amount) for e in items
                    if (kinds is None or e.kind in kinds) and e.kind not in exclude_kinds), Decimal("0"))

    charges_all = total(entries, kinds=(K.EXPENSE, K.INSTALLMENT_CHARGE))
    refunds_all = total(entries, kinds=(K.REFUND,))
    has_default_method = bool(batch.payment_method_id or batch.new_payment_method)

    totals = {
        "items": len(entries),
        "included": len(included),
        "included_amount": total(included, exclude_kinds=(K.REFUND, K.TRANSFER, K.INCOME)),
        "included_income": total(included, kinds=(K.INCOME,)),
        "included_transfers": total(included, kinds=(K.TRANSFER,)),
        "excluded": len(excluded),
        "excluded_amount": total(excluded),
        "weak": sum(1 for e in entries if e.match_status == StagedEntry.Match.WEAK),
        "confirm_existing": sum(1 for e in entries if e.match_status == StagedEntry.Match.CONFIRM_EXISTING),
        "refunds": refunds_all,
        "missing_payment_method": [
            e.position for e in included
            if e.kind != K.TRANSFER
            and not (e.payment_method_id or e.payment_method_name or has_default_method)],
    }

    if batch.kind == ImportBatch.Kind.INVOICE:
        if batch.invoice_total is not None:
            statement_sum = charges_all - refunds_all
            totals["invoice_items_sum"] = statement_sum
            totals["invoice_difference"] = Decimal(batch.invoice_total) - statement_sum
        # Subtotal por cartão (confere com o "Total para ..." de cada cartão na fatura)
        default_name = (batch.payment_method.name if batch.payment_method_id
                        else (batch.new_payment_method or {}).get("name", "(sem cartão)"))
        by_card = {}
        for e in entries:
            if e.kind not in (K.EXPENSE, K.INSTALLMENT_CHARGE, K.REFUND):
                continue
            name = e.payment_method.name if e.payment_method_id else (e.payment_method_name or default_name)
            sign = -1 if e.kind == K.REFUND else 1
            by_card[name] = by_card.get(name, Decimal("0")) + sign * Decimal(e.amount)
        if len(by_card) > 1:
            totals["by_card"] = by_card

    acct = batch.balance_account_id
    if acct and batch.opening_balance is not None and batch.balance_amount is not None:
        # Extrato: saldo inicial + entradas - saídas deve dar o saldo final
        net = Decimal("0")
        for e in entries:
            amount = Decimal(e.amount)
            if e.kind in (K.INCOME, K.REFUND):
                net += amount
            elif e.kind == K.TRANSFER:
                if e.to_account_id == acct:
                    net += amount
                else:
                    net -= amount
            else:
                net -= amount
        totals["statement_net"] = net
        totals["statement_difference"] = Decimal(batch.balance_amount) - (Decimal(batch.opening_balance) + net)
    return totals
