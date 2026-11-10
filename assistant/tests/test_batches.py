from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import PaymentMethod
from assistant import batch_service
from assistant.models import Conversation, ImportBatch
from assistant.tools import ToolCall, ToolContext, execute
from core.models import Category
from accounts.models import BalanceSnapshot, BankAccount
from financial import forecast
from financial.models import Purchase, Transaction, Transfer

CHAT = 111


class BatchTestCase(TestCase):
    def setUp(self):
        self.conv = Conversation.objects.create(chat_id=CHAT, provider="fake", model="fake", prompt_hash="x",
                                                last_activity_at=timezone.now())
        self.ctx = ToolContext(conversation=self.conv, chat_id=CHAT)
        self.card = PaymentMethod.objects.create(name="Nubank", type="CREDIT", due_day=10)
        self.pix = PaymentMethod.objects.create(name="Pix Itaú", type="PIX")
        self.food = Category.objects.create(name="Mercado", type="EXPENSE")

    def call(self, name, **args):
        result = execute(ToolCall(id="t1", name=name, input=args), self.ctx)
        import json

        data = json.loads(result.content) if not result.is_error else result.content
        return result, data

    def entries(self, batch_id):
        """Todos os itens do lote (stage_entries devolve só os que merecem atenção)."""
        _, data = self.call("get_batch", batch_id=batch_id)
        return data["entries"]

    def stage_invoice(self, entries, **batch):
        meta = {"kind": "invoice", "payment_method_id": self.card.pk, "invoice_month": "2026-12",
                "invoice_total": "250.00", "invoice_due_date": "2026-12-10", "invoice_closing_date": "2026-12-03"}
        meta.update(batch)
        return self.call("stage_entries", batch=meta, entries=entries)


class StagingTests(BatchTestCase):
    def test_stage_never_writes_financial_records(self):
        res, data = self.stage_invoice([
            {"kind": "EXPENSE", "description": "Mercado X", "amount": "100.00", "date": "2026-11-20",
             "category_id": self.food.pk},
        ])
        self.assertFalse(res.is_error, data)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(data["entries"], [])  # nada a destacar
        self.assertEqual(self.entries(data["batch_id"])[0]["match_status"], "new")

    def test_invalid_input_returns_error(self):
        res, data = self.call("stage_entries", entries=[{"kind": "EXPENSE"}])
        self.assertTrue(res.is_error)
        self.assertIn("Entrada inválida", data)

    def test_unknown_payment_method_is_rejected(self):
        res, data = self.call("stage_entries", batch={"kind": "chat"}, entries=[
            {"kind": "EXPENSE", "description": "X", "amount": "1.00", "date": "2026-11-01", "payment_method_id": 999}
        ])
        self.assertTrue(res.is_error)
        self.assertIn("não existe", data)

    def test_strong_duplicate_is_excluded_and_weak_is_flagged(self):
        Transaction.objects.create(type="EXPENSE", description="Mercado X", amount=Decimal("100.00"),
                                   date=date(2026, 11, 19), category=self.food, payment_method=self.card,
                                   confirmed=True)
        Transaction.objects.create(type="EXPENSE", description="Padaria", amount=Decimal("20.00"),
                                   date=date(2026, 11, 10), category=self.food, payment_method=self.card,
                                   confirmed=True)
        _, data = self.stage_invoice([
            {"kind": "EXPENSE", "description": "MERCADO X", "amount": "100.00", "date": "2026-11-20"},
            {"kind": "EXPENSE", "description": "Mercado X", "amount": "100.00", "date": "2026-11-20"},
            {"kind": "EXPENSE", "description": "PADARIA", "amount": "20.00", "date": "2026-11-15"},
        ])
        statuses = [(e["match_status"], e["include"]) for e in self.entries(data["batch_id"])]
        # 1ª linha casa com o existente; a 2ª (idêntica) é legítima: um-para-um
        self.assertEqual(statuses[0], ("duplicate", False))
        self.assertEqual(statuses[1], ("new", True))
        self.assertEqual(statuses[2], ("weak_match", True))

    def test_installment_charge_matches_existing_installment(self):
        Purchase.objects.create(description="Geladeira", total_amount=Decimal("1000.00"),
                                purchase_date=date(2026, 9, 10), number_of_installments=10,
                                category=self.food, payment_method=self.card)
        # parcela 4/10 tem vencimento em dez/2026 (fallback: mês da compra + 3)
        _, data = self.stage_invoice([
            {"kind": "INSTALLMENT_CHARGE", "description": "GELADEIRA 04/10", "amount": "100.00",
             "date": "2026-09-10", "installment_number": 4, "installments_total": 10},
        ])
        self.assertEqual(data["entries"][0]["match_status"], "duplicate")
        self.assertEqual(data["entries_by_status"], {"duplicate": 1})

    def test_installment_charge_requires_k_and_n(self):
        res, data = self.stage_invoice([
            {"kind": "INSTALLMENT_CHARGE", "description": "X", "amount": "10", "date": "2026-11-01"}])
        self.assertTrue(res.is_error)


class CommitTests(BatchTestCase):
    def test_commit_creates_records_and_card_settings(self):
        _, data = self.stage_invoice([
            {"kind": "EXPENSE", "description": "Mercado X", "amount": "100.00", "date": "2026-11-20",
             "category_id": self.food.pk},
            {"kind": "INSTALLMENT_CHARGE", "description": "Celular", "amount": "150.00", "date": "2026-09-01",
             "installment_number": 3, "installments_total": 10, "category_name": "Eletrônicos"},
        ])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        result = batch_service.commit(batch.pk, batch.version)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.created, 2)

        tx = Transaction.objects.get()
        self.assertTrue(tx.confirmed)
        self.assertTrue(tx.external_id.startswith("card:"))
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.total_amount, Decimal("1500.00"))
        self.assertEqual(purchase.first_invoice_month, date(2026, 10, 1))
        self.assertEqual(set(purchase.installments.filter(paid=True).values_list("installment_number", flat=True)),
                         {1, 2})
        inst3 = purchase.installments.get(installment_number=3)
        self.assertEqual((inst3.reference_year, inst3.reference_month), (2026, 12))
        self.card.refresh_from_db()
        self.assertEqual(self.card.closing_day, 3)  # aprendido da fatura
        self.assertEqual(Category.objects.filter(name="Eletrônicos").count(), 1)

    def test_reimporting_same_invoice_flags_everything_as_duplicate(self):
        entries = [
            {"kind": "EXPENSE", "description": "Mercado X", "amount": "100.00", "date": "2026-11-20"},
            {"kind": "INSTALLMENT_CHARGE", "description": "Celular", "amount": "150.00", "date": "2026-09-01",
             "installment_number": 3, "installments_total": 10},
        ]
        _, data = self.stage_invoice(entries)
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)

        _, data2 = self.stage_invoice(entries)
        self.assertEqual([e["match_status"] for e in self.entries(data2["batch_id"])], ["duplicate", "duplicate"])
        self.assertTrue(data2["warnings"])  # mesma fatura já importada

        # Fatura do mês seguinte: parcela 4/10 da mesma compra também é reconhecida
        _, data3 = self.stage_invoice([
            {"kind": "INSTALLMENT_CHARGE", "description": "Celular", "amount": "150.00", "date": "2026-09-01",
             "installment_number": 4, "installments_total": 10}], invoice_month="2027-01",
            invoice_due_date="2027-01-10")
        self.assertEqual(data3["entries"][0]["match_status"], "duplicate")

    def test_stale_version_and_double_commit_are_rejected(self):
        _, data = self.stage_invoice([
            {"kind": "EXPENSE", "description": "A", "amount": "10", "date": "2026-11-20"}])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        old_version = batch.version
        self.call("edit_staged_entries", batch_id=batch.pk, edits=[{"position": 1, "amount": "12.00"}])
        self.assertFalse(batch_service.commit(batch.pk, old_version).ok)
        batch.refresh_from_db()
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        self.assertFalse(batch_service.commit(batch.pk, batch.version).ok)
        self.assertEqual(Transaction.objects.get().amount, Decimal("12.00"))

    def test_missing_payment_method_blocks_commit(self):
        _, data = self.call("stage_entries", batch={"kind": "chat"}, entries=[
            {"kind": "EXPENSE", "description": "Almoço", "amount": "45", "date": "2026-11-09"}])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        result = batch_service.commit(batch.pk, batch.version)
        self.assertFalse(result.ok)
        self.assertIn("sem método de pagamento", result.message)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.STAGED)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_undo_removes_created_records(self):
        _, data = self.call("stage_entries", batch={"kind": "receipt", "payment_method_id": self.pix.pk}, entries=[
            {"kind": "EXPENSE", "description": "Almoço", "amount": "45", "date": "2026-11-09"},
            {"kind": "INSTALLMENT_PURCHASE", "description": "TV", "amount": "2400", "date": "2026-11-09",
             "installments_total": 12, "payment_method_id": self.card.pk},
        ])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        self.assertEqual(Purchase.objects.get().installments.count(), 12)
        result = batch_service.undo(batch.pk)
        self.assertTrue(result.ok)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(Purchase.objects.count(), 0)

    def test_present_batch_reports_invoice_difference(self):
        _, data = self.stage_invoice([
            {"kind": "EXPENSE", "description": "A", "amount": "200.00", "date": "2026-11-20"},
            {"kind": "REFUND", "description": "Estorno", "amount": "10.00", "date": "2026-11-21"},
        ])
        res, view = self.call("present_batch", batch_id=data["batch_id"])
        self.assertFalse(res.is_error, view)
        self.assertEqual(Decimal(view["totals"]["invoice_difference"]), Decimal("60.00"))
        self.assertEqual(self.ctx.batches_to_present, [data["batch_id"]])


class InvoiceShapeTests(BatchTestCase):
    """Casos tirados de uma fatura real (vários cartões, antecipação, pagamento)."""

    def test_anticipated_installments_become_plain_expenses(self):
        lines = [{"kind": "INSTALLMENT_CHARGE", "description": f"MERCADOLIVRE*MERCADO{k:02d}/04",
                  "amount": "112.50" if k == 1 else "112.47", "date": "2026-10-10",
                  "installment_number": k, "installments_total": 4} for k in (1, 4, 2, 3)]
        lines.append({"kind": "REFUND", "description": "MERCADOLIVRE", "amount": "449.91", "date": "2026-10-20"})
        lines.append({"kind": "INSTALLMENT_CHARGE", "description": "LOJA DE MOTOS", "amount": "113.75",
                      "date": "2026-08-13", "installment_number": 3, "installments_total": 4})
        _, data = self.stage_invoice(lines, invoice_total="113.75")
        kinds = [e["kind"] for e in self.entries(data["batch_id"])]
        self.assertEqual(kinds, ["EXPENSE"] * 4 + ["REFUND", "INSTALLMENT_CHARGE"])
        self.assertEqual(len(data["entries"]), 4)  # as convertidas são destacadas para a IA

        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertEqual(batch_service.batch_totals(batch)["invoice_difference"], Decimal("0.00"))
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        self.assertEqual(Purchase.objects.count(), 1)  # só a loja de motos tem parcelas futuras
        self.assertEqual(Transaction.objects.filter(type="EXPENSE").count(), 4)

    def test_notes_are_saved(self):
        _, data = self.stage_invoice([
            {"kind": "EXPENSE", "description": "Uber", "amount": "10", "date": "2026-11-20",
             "notes": "Cartão final 1234 (adicional)"}])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        batch_service.commit(batch.pk, batch.version)
        self.assertIn("final 1234", Transaction.objects.get().notes)

    def test_invoice_payment_marks_installments_paid_and_undo_restores(self):
        account = BankAccount.objects.create(name="Banco X CC", bank="Banco X")
        purchase = Purchase.objects.create(description="Sofá", total_amount=Decimal("300"),
                                           purchase_date=date(2026, 9, 5), number_of_installments=3,
                                           category=self.food, payment_method=self.card)
        # parcelas com referência 09, 10 e 11/2026
        _, data = self.stage_invoice([
            {"kind": "TRANSFER", "description": "PAGTO. POR DEB EM C/C", "amount": "1500.00",
             "date": "2026-10-13", "paid_invoice_month": "2026-10", "from_account_id": account.pk},
            {"kind": "EXPENSE", "description": "Mercado", "amount": "250.00", "date": "2026-11-20"},
        ])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        totals = batch_service.batch_totals(batch)
        self.assertEqual(totals["invoice_difference"], Decimal("0.00"))  # pagamento fora da soma
        self.assertEqual(totals["included_transfers"], Decimal("1500.00"))

        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        transfer = Transfer.objects.get()
        self.assertEqual((transfer.to_card, transfer.from_account), (self.card, account))
        self.assertTrue(purchase.installments.get(installment_number=2).paid)
        self.assertFalse(purchase.installments.get(installment_number=3).paid)
        self.assertEqual(forecast.account_balances(date(2026, 11, 30))["total"], Decimal("-1500.00"))

        self.assertTrue(batch_service.undo(batch.pk).ok)
        self.assertEqual(Transfer.objects.count(), 0)
        self.assertFalse(purchase.installments.get(installment_number=2).paid)
        self.card.refresh_from_db()
        self.assertIsNone(self.card.closing_day)  # aprendido da fatura e desfeito

    def test_same_payment_from_statement_completes_existing_transfer(self):
        account = BankAccount.objects.create(name="Banco X CC", bank="Banco X")
        Transfer.objects.create(date=date(2026, 10, 13), amount=Decimal("1500.00"), to_card=self.card,
                                invoice_year=2026, invoice_month=10)
        _, data = self.call("stage_entries", batch={"kind": "statement", "account_id": account.pk}, entries=[
            {"kind": "TRANSFER", "description": "Pagamento cartão", "amount": "1500.00", "date": "2026-10-13",
             "from_account_id": account.pk, "to_card_id": self.card.pk}])
        self.assertEqual(data["entries"][0]["match_status"], "confirm_existing")
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        self.assertEqual(Transfer.objects.get().from_account, account)


class StatementTests(BatchTestCase):
    def setUp(self):
        super().setUp()
        self.account = BankAccount.objects.create(name="Inter", bank="Inter")
        self.pix.bank_account = self.account
        self.pix.save()
        self.debit = PaymentMethod.objects.create(name="Débito Inter", type="DEBIT", bank_account=self.account)

    def test_statement_line_matches_existing_from_other_method_of_same_account(self):
        Transaction.objects.create(type="EXPENSE", description="Farmácia", amount=Decimal("30.00"),
                                   date=date(2026, 11, 3), category=self.food, payment_method=self.pix,
                                   confirmed=True)
        _, data = self.call("stage_entries", batch={"kind": "statement", "account_id": self.account.pk}, entries=[
            {"kind": "EXPENSE", "description": "DROGARIA X", "amount": "30.00", "date": "2026-11-03",
             "payment_method_id": self.debit.pk},
            {"kind": "INCOME", "description": "Salário", "amount": "5000", "date": "2026-11-05",
             "payment_method_id": self.pix.pk, "external_ref": "FIT123"},
        ])
        statuses = [e["match_status"] for e in self.entries(data["batch_id"])]
        self.assertEqual(statuses, ["duplicate", "new"])

    def test_balance_snapshot_commit_anchor_and_undo(self):
        _, data = self.call("stage_entries", batch={
            "kind": "statement", "account_id": self.account.pk, "balance_amount": "1.500,00",
            "balance_date": "2026-11-05"}, entries=[
            {"kind": "INCOME", "description": "Salário", "amount": "5000", "date": "2026-11-05",
             "payment_method_id": self.pix.pk, "external_ref": "FIT123"},
            {"kind": "EXPENSE", "description": "Aluguel", "amount": "2000", "date": "2026-11-08",
             "payment_method_id": self.pix.pk, "external_ref": "FIT124"},
        ])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        self.assertEqual(Transaction.objects.get(description="Salário").external_id,
                         f"stmt:{self.account.pk}:FIT123:INCOME:5000.00")

        balances = forecast.account_balances(date(2026, 11, 30))
        acct = balances["accounts"][0]
        # saldo de 05/11 já inclui o salário; só o aluguel (08/11) vem depois
        self.assertEqual((acct["anchor"], acct["balance"]), ("snapshot", Decimal("-500.00")))
        self.assertTrue(balances["all_anchored"])

        # reimportar o mesmo extrato não duplica
        _, again = self.call("stage_entries", batch={"kind": "statement", "account_id": self.account.pk}, entries=[
            {"kind": "EXPENSE", "description": "Aluguel", "amount": "2000", "date": "2026-11-08",
             "payment_method_id": self.pix.pk, "external_ref": "FIT124"}])
        self.assertEqual(again["entries"][0]["match_status"], "duplicate")

        self.assertTrue(batch_service.undo(batch.pk).ok)
        self.assertEqual(BalanceSnapshot.objects.count(), 0)

    def test_balance_only_batch(self):
        res, data = self.call("stage_entries", batch={
            "kind": "chat", "account_id": self.account.pk, "balance_amount": "-120.50",
            "balance_date": "2026-11-10"})
        self.assertFalse(res.is_error, data)
        res, _ = self.call("present_batch", batch_id=data["batch_id"])
        self.assertFalse(res.is_error)
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        self.assertEqual(BalanceSnapshot.objects.get().balance, Decimal("-120.50"))

    def test_edit_keeps_user_include_choice(self):
        Transaction.objects.create(type="EXPENSE", description="Farmácia", amount=Decimal("30.00"),
                                   date=date(2026, 11, 3), category=self.food, payment_method=self.pix,
                                   confirmed=True)
        _, data = self.call("stage_entries", batch={"kind": "chat", "payment_method_id": self.pix.pk}, entries=[
            {"kind": "EXPENSE", "description": "Farmácia", "amount": "30.00", "date": "2026-11-03"}])
        bid = data["batch_id"]
        self.call("edit_staged_entries", batch_id=bid, edits=[{"position": 1, "include": True}])
        self.call("edit_staged_entries", batch_id=bid, edits=[{"position": 1, "category_id": self.food.pk}])
        entry = self.entries(bid)[0]
        self.assertEqual((entry["match_status"], entry["include"]), ("duplicate", True))


class NewPaymentMethodTests(BatchTestCase):
    META = {"kind": "invoice", "invoice_month": "2026-11", "invoice_total": "113.75",
            "invoice_due_date": "2026-11-10", "invoice_closing_date": "2026-10-27",
            "new_payment_method": {"name": "Banco X Visa", "new_bank_account_name": "Banco X"}}
    LINES = [
        {"kind": "TRANSFER", "description": "PAGTO. POR DEB EM C/C", "amount": "1500.00", "date": "2026-10-13",
         "paid_invoice_month": "2026-10"},
        {"kind": "INSTALLMENT_CHARGE", "description": "LOJA DE MOTOS", "amount": "113.75", "date": "2026-08-13",
         "installment_number": 3, "installments_total": 4},
    ]

    def test_card_is_created_only_on_confirm_and_removed_on_undo(self):
        res, data = self.call("stage_entries", batch=self.META, entries=self.LINES)
        self.assertFalse(res.is_error, data)
        self.assertFalse(PaymentMethod.objects.filter(name__icontains="Banco X").exists())
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertEqual(batch_service.batch_totals(batch)["missing_payment_method"], [])

        result = batch_service.commit(batch.pk, batch.version)
        self.assertTrue(result.ok, result.message)
        card = PaymentMethod.objects.get(name="Banco X Visa")
        self.assertEqual((card.type, card.closing_day, card.due_day, card.bank_account.name),
                         ("CREDIT", 27, 10, "Banco X"))
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.payment_method, card)
        inst = purchase.installments.get(installment_number=3)
        self.assertEqual(inst.due_date, date(2026, 11, 10))
        self.assertEqual(Transfer.objects.get().to_card, card)

        # reimportar agora encontra o cartão e reconhece tudo
        meta = {**self.META, "payment_method_id": card.pk}
        meta.pop("new_payment_method")
        _, again = self.call("stage_entries", batch=meta, entries=self.LINES)
        self.assertEqual(again["entries_by_status"], {"duplicate": 2})

        self.assertTrue(batch_service.undo(batch.pk).ok)
        self.assertFalse(PaymentMethod.objects.filter(name="Banco X Visa").exists())
        self.assertFalse(BankAccount.objects.filter(name="Banco X").exists())

    def test_existing_name_is_rejected(self):
        meta = {**self.META, "new_payment_method": {"name": "nubank"}}
        res, data = self.call("stage_entries", batch=meta, entries=self.LINES)
        self.assertTrue(res.is_error)
        self.assertIn("Já existe", data)


class InvoiceMonthTests(BatchTestCase):
    """O dia de fechamento varia de mês para mês: o que veio numa fatura fica
    preso a ela, não ao cálculo pelo dia fixo."""

    def setUp(self):
        super().setUp()
        self.card.closing_day = 27
        self.card.save()

    def test_imported_lines_keep_their_invoice(self):
        # 25/09 pelo dia fixo cairia na fatura de outubro; veio na de novembro
        _, data = self.stage_invoice([
            {"kind": "EXPENSE", "description": "Uber", "amount": "18.92", "date": "2026-09-25"},
            {"kind": "REFUND", "description": "Shein", "amount": "8.92", "date": "2026-09-18"},
        ], invoice_month="2026-11", invoice_total="10.00", invoice_due_date="2026-11-10")
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        months = forecast.invoice_forecast((2026, 10), (2026, 11), today=date(2026, 10, 28))
        self.assertEqual([(m["month"], m["total"]) for m in months], [(11, Decimal("10.00"))])

    def test_existing_transaction_is_stamped_and_undo_restores(self):
        tx = Transaction.objects.create(type="EXPENSE", description="Uber", amount=Decimal("18.92"),
                                        date=date(2026, 9, 25), category=self.food, payment_method=self.card,
                                        confirmed=True)
        _, data = self.stage_invoice([
            {"kind": "EXPENSE", "description": "DL *UberRides", "amount": "18.92", "date": "2026-09-25"},
        ], invoice_month="2026-11", invoice_total="18.92", invoice_due_date="2026-11-10")
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertEqual(data["entries"][0]["match_status"], "duplicate")
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        tx.refresh_from_db()
        self.assertEqual(tx.invoice_month, date(2026, 11, 1))
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertTrue(batch_service.undo(batch.pk).ok)
        tx.refresh_from_db()
        self.assertIsNone(tx.invoice_month)
