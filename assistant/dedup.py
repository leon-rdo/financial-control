"""Detecção de lançamentos já registrados (deduplicação) para itens de lote.

Regras (todas no servidor, a IA só lê o resultado):
- Despesa/receita avulsa: mesmo método, valor ±0,01 e data ±3 dias = duplicado
  certo (excluído). Valor ±2% ou data ±7 dias = possível duplicado (incluído, com
  aviso). Atribuição um-para-um: dois cafés iguais no mesmo dia são legítimos.
  Se o lançamento existente é de recorrência e não confirmado, o item apenas o
  confirma (confirm_existing).
- Parcela k/N em fatura: procura Installment do mesmo cartão com mesmo k e N,
  valor ±max(0,05; 1%) e mês de referência ±1.
- Compra parcelada nova: Purchase do mesmo método, mesmo N, total ±0,01, data ±3.
- Extrato de conta: o lançamento existente pode ter sido registrado por outro
  método da mesma conta (Pix x débito), então a comparação é pela conta.
- Transferência / pagamento de fatura: mesmo valor e data ±3; se a existente não
  tem conta de origem ou cartão e o item tem, o item completa a existente.
"""

import hashlib
import re
import unicodedata
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from financial.forecast import REFUND_CATEGORY_NAME, add_months, card_family_ids, invoice_card
from financial.models import Installment, Purchase, Transaction, Transfer

from .models import ImportBatch, StagedEntry

STRONG_DAYS = 3
WEAK_DAYS = 7
CENT = Decimal("0.01")


def normalize(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _hash(*parts):
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


def line_external_id(batch, entry, occurrence):
    """Chave estável de uma linha importada: reimportar o mesmo arquivo não duplica.

    - Extrato com identificador do banco (ID da operação, FITID do OFX):
      `stmt:<conta>:<id>:<tipo>:<valor>` (um Pix e o seu estorno compartilham o id).
    - Linha de fatura de cartão: hash do cartão principal da fatura, mês, data,
      valor e descrição (não depende de qual cartão da fatura fez a compra).
    """
    if entry.external_ref and batch.balance_account_id:
        return f"stmt:{batch.balance_account_id}:{entry.external_ref}:{entry.kind}:{entry.amount}"[:120]
    if not (batch.kind == ImportBatch.Kind.INVOICE and batch.payment_method_id and batch.invoice_year):
        return ""
    return "card:{}:{}".format(invoice_card(batch.payment_method).pk, _hash(
        batch.invoice_year, batch.invoice_month, entry.date.isoformat(),
        entry.amount, normalize(entry.description), entry.kind, occurrence,
    ))


def assign_external_ids(batch):
    """Recalcula external_id das linhas (índice de ocorrência para linhas iguais)."""
    seen = Counter()
    for e in batch.entries.order_by("position"):
        key = (e.date, e.amount, normalize(e.description), e.kind)
        seen[key] += 1
        ext = line_external_id(batch, e, seen[key])
        if ext != e.external_id:
            e.external_id = ext
            e.save(update_fields=["external_id"])


def installment_purchase_external_id(root_card_id, description, total_installments, amount, first_invoice_month):
    """Chave da compra parcelada criada a partir de uma linha "PARCELA k/N".

    É a mesma em todas as faturas seguintes (k muda, mas descrição, N, valor da
    parcela e mês da 1ª fatura não)."""
    return "cardinst:{}:{}".format(root_card_id, _hash(
        normalize(description), total_installments, amount, first_invoice_month.isoformat(),
    ))


def first_invoice_month_for(batch, entry):
    """Mês da 1ª parcela, a partir do mês da fatura e do número k da parcela."""
    from datetime import date

    if not (batch.invoice_year and batch.invoice_month and entry.installment_number):
        return None
    y, m = add_months(batch.invoice_year, batch.invoice_month, -(entry.installment_number - 1))
    return date(y, m, 1)


def _within(a, b, tol):
    return abs(Decimal(a) - Decimal(b)) <= tol


def _claimed_ids(batch, exclude_entry_id=None):
    qs = batch.entries.exclude(pk=exclude_entry_id) if exclude_entry_id else batch.entries.all()
    tx_ids = set(qs.exclude(matched_transaction__isnull=True).values_list("matched_transaction_id", flat=True))
    inst_ids = set(qs.exclude(matched_installment__isnull=True).values_list("matched_installment_id", flat=True))
    return tx_ids, inst_ids


def _claimed_transfers(batch, exclude_entry_id=None):
    qs = batch.entries.exclude(pk=exclude_entry_id) if exclude_entry_id else batch.entries.all()
    return set(qs.exclude(matched_transfer__isnull=True).values_list("matched_transfer_id", flat=True))


def classify_entry(batch, entry, claimed_tx=None, claimed_inst=None):
    """Define match_status/match_note/matched_*/include de um item (não salva)."""
    if claimed_tx is None or claimed_inst is None:
        claimed_tx, claimed_inst = _claimed_ids(batch, exclude_entry_id=entry.pk)

    entry.match_status = StagedEntry.Match.NEW
    entry.match_note = ""
    entry.matched_transaction = None
    entry.matched_installment = None
    entry.matched_transfer = None
    entry.include = True

    pm = entry.payment_method or batch.payment_method
    kind = entry.kind

    if kind in (StagedEntry.Kind.EXPENSE, StagedEntry.Kind.INCOME, StagedEntry.Kind.REFUND):
        _classify_single(entry, pm, claimed_tx)
    elif kind == StagedEntry.Kind.INSTALLMENT_CHARGE:
        _classify_installment_charge(batch, entry, pm, claimed_inst)
    elif kind == StagedEntry.Kind.INSTALLMENT_PURCHASE:
        _classify_installment_purchase(entry, pm)
    elif kind == StagedEntry.Kind.TRANSFER:
        _classify_transfer(batch, entry)

    if entry.matched_transaction_id:
        claimed_tx.add(entry.matched_transaction_id)
    if entry.matched_installment_id:
        claimed_inst.add(entry.matched_installment_id)
    return entry


def _method_filter(qs, pm, prefix="payment_method"):
    """Restringe a lançamentos do "mesmo dinheiro": cartões da mesma fatura, ou
    qualquer método (Pix, débito...) da mesma conta."""
    if pm.type == "CREDIT":
        return qs.filter(**{f"{prefix}_id__in": card_family_ids(pm)})
    if pm.bank_account_id:
        return qs.filter(**{f"{prefix}__bank_account_id": pm.bank_account_id}).exclude(
            **{f"{prefix}__type": "CREDIT"})
    return qs.filter(**{f"{prefix}_id": pm.pk})


def _classify_single(entry, pm, claimed_tx):
    tx_type = "EXPENSE" if entry.kind == StagedEntry.Kind.EXPENSE else "INCOME"

    if entry.external_id:
        existing = Transaction.objects.filter(external_id=entry.external_id).first()
        if existing:
            entry.match_status = StagedEntry.Match.DUPLICATE
            entry.match_note = "mesma linha já importada"
            entry.matched_transaction = existing
            entry.include = False
            return

    qs = Transaction.objects.filter(
        type=tx_type,
        date__gte=entry.date - timedelta(days=WEAK_DAYS),
        date__lte=entry.date + timedelta(days=WEAK_DAYS),
    ).exclude(pk__in=claimed_tx)
    if entry.kind == StagedEntry.Kind.REFUND:
        qs = qs.filter(category__name=REFUND_CATEGORY_NAME)
    if pm:
        qs = _method_filter(qs, pm)

    strong, weak = None, None
    for tx in qs.order_by("date"):
        days = abs((tx.date - entry.date).days)
        if _within(tx.amount, entry.amount, CENT) and days <= STRONG_DAYS and pm:
            if strong is None or days < abs((strong.date - entry.date).days):
                strong = tx
        elif weak is None and (
            (_within(tx.amount, entry.amount, Decimal(entry.amount) * Decimal("0.02")) and days <= STRONG_DAYS)
            or (_within(tx.amount, entry.amount, CENT) and days <= WEAK_DAYS)
        ):
            weak = tx

    if strong:
        entry.matched_transaction = strong
        if strong.recurrence_id and not strong.confirmed:
            entry.match_status = StagedEntry.Match.CONFIRM_EXISTING
            entry.match_note = f"confirma lançamento previsto de {strong.date:%d/%m}"
            entry.include = True
        else:
            entry.match_status = StagedEntry.Match.DUPLICATE
            entry.match_note = f"já registrado em {strong.date:%d/%m} (#{strong.pk})"
            entry.include = False
    elif weak:
        entry.match_status = StagedEntry.Match.WEAK
        entry.match_note = f"parecido com '{weak.description}' R$ {weak.amount} em {weak.date:%d/%m}"
        entry.include = True


def _classify_installment_charge(batch, entry, pm, claimed_inst):
    k, n = entry.installment_number, entry.installments_total
    if not (k and n and pm):
        return

    fim = first_invoice_month_for(batch, entry)
    if fim:
        ext = installment_purchase_external_id(invoice_card(pm).pk, entry.description, n, entry.amount, fim)
        purchase = Purchase.objects.filter(external_id=ext).first()
        if purchase:
            inst = purchase.installments.filter(installment_number=k).first()
            if inst and inst.pk not in claimed_inst:
                entry.match_status = StagedEntry.Match.DUPLICATE
                entry.match_note = f"parcela {k}/{n} já registrada"
                entry.matched_installment = inst
                entry.include = False
                return

    tol = max(Decimal("0.05"), Decimal(entry.amount) * Decimal("0.01"))
    qs = Installment.objects.filter(
        purchase__payment_method_id__in=card_family_ids(pm),
        installment_number=k,
        purchase__number_of_installments=n,
    ).exclude(pk__in=claimed_inst).select_related("purchase")

    best, best_dist = None, None
    for inst in qs:
        if not _within(inst.amount, entry.amount, tol):
            continue
        if batch.invoice_year and batch.invoice_month:
            dist = abs((inst.reference_year * 12 + inst.reference_month)
                       - (batch.invoice_year * 12 + batch.invoice_month))
        else:
            dist = abs((inst.due_date - entry.date).days) // 30
        if best is None or dist < best_dist:
            best, best_dist = inst, dist

    if best is None:
        return
    entry.matched_installment = best
    if best_dist <= 1:
        entry.match_status = StagedEntry.Match.DUPLICATE
        entry.match_note = f"parcela {k}/{n} já registrada ({best.purchase.description})"
        entry.include = False
    else:
        entry.match_status = StagedEntry.Match.WEAK
        entry.match_note = (f"parcela {k}/{n} parecida já registrada, mas em outro mês "
                            f"({best.reference_month:02d}/{best.reference_year})")
        entry.include = False


def _classify_installment_purchase(entry, pm):
    if not (pm and entry.installments_total):
        return
    existing = _method_filter(Purchase.objects.all(), pm).filter(
        number_of_installments=entry.installments_total,
        purchase_date__gte=entry.date - timedelta(days=STRONG_DAYS),
        purchase_date__lte=entry.date + timedelta(days=STRONG_DAYS),
    )
    for p in existing:
        if _within(p.total_amount, entry.amount, CENT):
            entry.match_status = StagedEntry.Match.DUPLICATE
            entry.match_note = f"compra parcelada já registrada (#{p.pk})"
            entry.include = False
            return


def _classify_transfer(batch, entry):
    if entry.external_id:
        existing = Transfer.objects.filter(external_id=entry.external_id).first()
        if existing:
            entry.match_status = StagedEntry.Match.DUPLICATE
            entry.match_note = "mesma linha já importada"
            entry.matched_transfer = existing
            entry.include = False
            return

    claimed = _claimed_transfers(batch, exclude_entry_id=entry.pk)
    qs = Transfer.objects.filter(
        date__gte=entry.date - timedelta(days=STRONG_DAYS),
        date__lte=entry.date + timedelta(days=STRONG_DAYS),
    ).exclude(pk__in=claimed)
    for tr in qs.order_by("date"):
        if not _within(tr.amount, entry.amount, CENT):
            continue
        # Campos preenchidos nos dois lados precisam coincidir
        pairs = [(tr.from_account_id, entry.from_account_id), (tr.to_account_id, entry.to_account_id),
                 (tr.to_card_id, entry.to_card_id)]
        if any(a and b and a != b for a, b in pairs):
            continue
        entry.matched_transfer = tr
        adds_info = any(b and not a for a, b in pairs) or (
            entry.paid_invoice_month and not tr.invoice_month)
        if adds_info:
            entry.match_status = StagedEntry.Match.CONFIRM_EXISTING
            entry.match_note = f"completa a transferência de {tr.date:%d/%m} já registrada"
            entry.include = True
        else:
            entry.match_status = StagedEntry.Match.DUPLICATE
            entry.match_note = f"transferência já registrada em {tr.date:%d/%m}"
            entry.include = False
        return


def anticipated_installment_groups(batch):
    """Parcelas da MESMA compra cobradas juntas na mesma fatura (antecipação ou
    cancelamento): ex. 01/04, 02/04, 03/04 e 04/04 no mesmo mês. Não sobra
    parcela futura, então devem virar despesas simples.

    Retorna listas de itens (cada lista com 2+ parcelas distintas)."""
    groups = {}
    for e in batch.entries.filter(kind=StagedEntry.Kind.INSTALLMENT_CHARGE):
        base = re.sub(r"\d{1,2}\s*/\s*\d{1,2}", " ", e.description)
        key = (normalize(base), e.installments_total, e.date, e.payment_method_id)
        groups.setdefault(key, []).append(e)
    return [g for g in groups.values() if len({e.installment_number for e in g}) > 1]


def batch_warnings(batch):
    """Avisos de lote inteiro: mesmo arquivo ou mesma fatura já confirmados."""
    warnings = []
    confirmed = ImportBatch.objects.filter(status=ImportBatch.Status.CONFIRMED).exclude(pk=batch.pk)
    if batch.attachment_id:
        dup = confirmed.filter(attachment__sha256=batch.attachment.sha256).first()
        if dup:
            warnings.append(f"Este mesmo arquivo já foi importado no lote #{dup.pk}.")
    if batch.kind == ImportBatch.Kind.INVOICE and batch.payment_method_id and batch.invoice_year:
        dup = confirmed.filter(
            kind=ImportBatch.Kind.INVOICE,
            payment_method_id=batch.payment_method_id,
            invoice_year=batch.invoice_year,
            invoice_month=batch.invoice_month,
        ).first()
        if dup:
            warnings.append(
                f"A fatura {batch.invoice_month:02d}/{batch.invoice_year} deste cartão já foi importada no lote #{dup.pk}."
            )
    return warnings
