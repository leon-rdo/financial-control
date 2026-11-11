from datetime import date
from decimal import Decimal

from accounts.models import BankAccount, PaymentMethod
from assistant import batch_service
from assistant.models import ImportBatch
from financial import forecast
from financial.models import Purchase, Transaction, Transfer

from .test_batches import BatchTestCase


class PerCardInvoiceTests(BatchTestCase):
    """Fatura com vários cartões: cada item no seu cartão, uma fatura só."""

    META = {"kind": "invoice", "invoice_month": "2026-11", "invoice_total": "330.00",
            "invoice_due_date": "2026-11-10", "invoice_closing_date": "2026-10-27",
            "new_payment_method": {"name": "Final 1111", "new_bank_account_name": "Banco X"},
            "additional_new_cards": [{"name": "Final 2222"}, {"name": "Final 3333 (Maria)"}]}
    LINES = [
        {"kind": "EXPENSE", "description": "Mercado", "amount": "100.00", "date": "2026-10-05"},
        {"kind": "EXPENSE", "description": "Loja", "amount": "50.00", "date": "2026-10-06",
         "payment_method_name": "Final 2222"},
        {"kind": "REFUND", "description": "Loja", "amount": "20.00", "date": "2026-10-07",
         "payment_method_name": "final 2222"},
        {"kind": "INSTALLMENT_CHARGE", "description": "Clínica", "amount": "200.00", "date": "2026-09-22",
         "installment_number": 2, "installments_total": 4, "payment_method_name": "Final 3333 (Maria)"},
        {"kind": "TRANSFER", "description": "PAGTO FATURA", "amount": "900.00", "date": "2026-10-13",
         "paid_invoice_month": "2026-10"},
    ]

    def test_items_go_to_their_cards_but_invoice_stays_single(self):
        res, data = self.call("stage_entries", batch=self.META, entries=self.LINES)
        self.assertFalse(res.is_error, data)
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        totals = batch_service.batch_totals(batch)
        self.assertEqual(totals["invoice_difference"], Decimal("0.00"))
        self.assertEqual(totals["by_card"], {"Final 1111": Decimal("100.00"), "Final 2222": Decimal("30.00"),
                                             "Final 3333 (Maria)": Decimal("200.00")})
        self.assertFalse(PaymentMethod.objects.filter(name__startswith="Final").exists())

        result = batch_service.commit(batch.pk, batch.version)
        self.assertTrue(result.ok, result.message)
        main, second, third = (PaymentMethod.objects.get(name=n) for n in
                               ("Final 1111", "Final 2222", "Final 3333 (Maria)"))
        self.assertEqual((main.closing_day, main.due_day, main.billing_card), (27, 10, None))
        self.assertEqual((second.billing_card, third.billing_card), (main, main))
        self.assertEqual(Transaction.objects.get(description="Mercado").payment_method, main)
        self.assertEqual(Transaction.objects.get(type="EXPENSE", description="Loja").payment_method, second)
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.payment_method, third)
        # parcela do cartão adicional usa o vencimento da fatura (cartão principal)
        self.assertEqual(purchase.installments.get(installment_number=2).due_date, date(2026, 11, 10))
        self.assertEqual(Transfer.objects.get().to_card, main)

        # previsão: uma fatura só, com subtotal por cartão
        months = forecast.invoice_forecast((2026, 11), (2026, 11), today=date(2026, 11, 1))
        (method,) = months[0]["methods"]
        self.assertEqual((method["payment_method"], method["total"]), ("Final 1111", Decimal("330.00")))
        self.assertEqual({c["card"]: c["total"] for c in method["cards"]},
                         {"Final 1111": Decimal("100.00"), "Final 2222": Decimal("30.00"),
                          "Final 3333 (Maria)": Decimal("200.00")})
        # filtrar pelo cartão principal traz a fatura inteira; por um adicional, só ele
        only_third = forecast.invoice_forecast((2026, 11), (2026, 11), [third.pk], today=date(2026, 11, 1))
        self.assertEqual(only_third[0]["total"], Decimal("200.00"))
        # gastos por cartão em outubro (a 1ª parcela da clínica venceu em 10/10)
        summary = forecast.spending_summary(date(2026, 10, 1), date(2026, 10, 31), "payment_method")
        self.assertEqual({r["label"]: r["total"] for r in summary["rows"]},
                         {"Final 1111": Decimal("100.00"), "Final 2222": Decimal("30.00"),
                          "Final 3333 (Maria)": Decimal("200.00")})

        # reimportar: reconhece tudo, mesmo se um item vier atribuído a outro cartão da fatura
        meta = {k: v for k, v in self.META.items() if k not in ("new_payment_method", "additional_new_cards")}
        meta["payment_method_id"] = main.pk
        lines = [dict(line) for line in self.LINES]
        lines[1]["payment_method_name"] = "Final 3333 (Maria)"
        _, again = self.call("stage_entries", batch=meta, entries=lines)
        self.assertEqual(again["entries_by_status"], {"duplicate": 5})

        self.assertTrue(batch_service.undo(batch.pk).ok)
        self.assertFalse(PaymentMethod.objects.filter(name__startswith="Final").exists())
        self.assertFalse(BankAccount.objects.filter(name="Banco X").exists())

    def test_paying_the_invoice_marks_installments_of_all_its_cards(self):
        _, data = self.call("stage_entries", batch=self.META, entries=self.LINES)
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        batch_service.commit(batch.pk, batch.version)
        main = PaymentMethod.objects.get(name="Final 1111")
        Transfer.objects.create(date=date(2026, 11, 10), amount=Decimal("330"), to_card=main,
                                invoice_year=2026, invoice_month=11).mark_invoice_paid()
        self.assertTrue(Purchase.objects.get().installments.get(installment_number=2).paid)
        self.assertEqual(forecast.invoice_forecast((2026, 11), (2026, 11), today=date(2026, 11, 1)), [])

    def test_unknown_card_name_is_rejected(self):
        lines = [{"kind": "EXPENSE", "description": "X", "amount": "1", "date": "2026-10-05",
                  "payment_method_name": "Final 9999"}]
        res, data = self.call("stage_entries", batch=self.META, entries=lines)
        self.assertTrue(res.is_error)
        self.assertIn("additional_new_cards", data)


class PotsTests(BatchTestCase):
    """Caixinhas/cofrinhos: dinheiro guardado dentro de uma conta."""

    def setUp(self):
        super().setUp()
        self.account = BankAccount.objects.create(name="Carteira Digital", bank="Carteira Digital")
        self.pix.bank_account = self.account
        self.pix.save()

    def stage(self, **batch):
        meta = {"kind": "statement", "account_id": self.account.pk, "opening_balance": "495.00",
                "balance_amount": "0.00", "balance_date": "2026-10-31"}
        meta.update(batch)
        return self.call("stage_entries", batch=meta, entries=[
            {"kind": "INCOME", "description": "Rendimentos", "amount": "0.20", "date": "2026-10-01",
             "payment_method_id": self.pix.pk, "external_ref": "A1", "category_name": "Rendimentos"},
            {"kind": "EXPENSE", "description": "Pix enviado", "amount": "50.00", "date": "2026-10-01",
             "payment_method_id": self.pix.pk, "external_ref": "A2"},
            {"kind": "TRANSFER", "description": "Dinheiro retirado Emergências", "amount": "350.00",
             "date": "2026-10-02", "from_account_name": "Emergências", "to_account_id": self.account.pk,
             "external_ref": "A3"},
            {"kind": "TRANSFER", "description": "Pagamento de fatura", "amount": "773.05", "date": "2026-10-02",
             "from_account_id": self.account.pk, "external_ref": "A4"},
            {"kind": "TRANSFER", "description": "Dinheiro reservado Emergências", "amount": "22.15",
             "date": "2026-10-03", "from_account_id": self.account.pk, "to_account_name": "emergências",
             "external_ref": "A5"},
        ])

    def test_statement_with_pots(self):
        res, data = self.stage(other_balances=[{"account_name": "Emergências", "amount": "8000", "date": "2026-10-31"}])
        self.assertFalse(res.is_error, data)
        self.assertEqual(data["new_pots_on_confirm"], ["Emergências", "emergências"])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        # 495 + 0,20 - 50 + 350 - 773,05 - 22,15 = 0
        self.assertEqual(batch_service.batch_totals(batch)["statement_difference"], Decimal("0.00"))
        self.assertFalse(BankAccount.objects.filter(name__iexact="Emergências").exists())

        result = batch_service.commit(batch.pk, batch.version)
        self.assertTrue(result.ok, result.message)
        pot = BankAccount.objects.get(name__iexact="Emergências")  # uma só, apesar da caixa diferente
        self.assertEqual((pot.parent, pot.type, pot.is_reserve), (self.account, "INVESTMENT", True))
        self.assertEqual(Transfer.objects.count(), 3)
        self.assertEqual(Transaction.objects.filter(type="EXPENSE").count(), 1)  # reservar não é gasto

        balances = forecast.account_balances(date(2026, 10, 31))
        by_name = {a["account"]: a for a in balances["accounts"]}
        self.assertEqual(by_name["Carteira Digital"]["balance"], Decimal("0.00"))
        self.assertEqual(by_name["Emergências"]["balance"], Decimal("8000.00"))
        self.assertEqual((balances["available"], balances["reserved"]), (Decimal("0.00"), Decimal("8000.00")))

        # reimportar o extrato: tudo reconhecido pelo ID da operação
        _, again = self.stage()
        self.assertEqual(again["entries_by_status"], {"duplicate": 5})

        self.assertTrue(batch_service.undo(batch.pk).ok)
        self.assertFalse(BankAccount.objects.filter(name__iexact="Emergências").exists())
        self.assertEqual(Transfer.objects.count(), 0)

    def test_movements_after_informed_balance_change_pot_and_available(self):
        pot = BankAccount.objects.create(name="Reserva", bank="Carteira Digital", type="INVESTMENT",
                                         parent=self.account)
        res, data = self.call("stage_entries", batch={
            "kind": "chat", "account_id": self.account.pk, "balance_amount": "100", "balance_date": "2026-10-31",
            "other_balances": [{"account_id": pot.pk, "amount": "8000", "date": "2026-10-31"}]})
        self.assertFalse(res.is_error, data)
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        Transfer.objects.create(date=date(2026, 11, 2), amount=Decimal("500"), from_account=pot,
                                to_account=self.account)
        later = forecast.account_balances(date(2026, 11, 30))
        self.assertEqual((later["available"], later["reserved"], later["total"]),
                         (Decimal("600.00"), Decimal("7500.00"), Decimal("8100.00")))
        flow = forecast.monthly_cash_flow(0, today=date(2026, 11, 30))
        self.assertEqual((flow["start_balance"], flow["reserved"]), (Decimal("600.00"), Decimal("7500.00")))

    def test_pot_without_informed_balance_stays_out_of_totals(self):
        pot = BankAccount.objects.create(name="Reserva", bank="Carteira Digital", type="INVESTMENT",
                                         parent=self.account)
        Transfer.objects.create(date=date(2026, 10, 2), amount=Decimal("350"), from_account=pot,
                                to_account=self.account)
        balances = forecast.account_balances(date(2026, 10, 31))
        by_name = {a["account"]: a for a in balances["accounts"]}
        self.assertIsNone(by_name["Reserva"]["balance"])  # não inventa saldo negativo
        self.assertEqual(by_name["Reserva"]["net_movements_since_anchor"], Decimal("-350.00"))
        self.assertEqual((balances["reserved"], balances["reserved_unknown"]), (Decimal("0"), ["Reserva"]))

    def test_same_operation_id_for_payment_and_refund_does_not_collide(self):
        _, data = self.call("stage_entries", batch={"kind": "statement", "account_id": self.account.pk}, entries=[
            {"kind": "EXPENSE", "description": "Pix enviado", "amount": "99.90", "date": "2026-10-14",
             "payment_method_id": self.pix.pk, "external_ref": "X1"},
            {"kind": "REFUND", "description": "Reembolso de Pix", "amount": "99.90", "date": "2026-10-14",
             "payment_method_id": self.pix.pk, "external_ref": "X1"},
        ])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        self.assertEqual(Transaction.objects.exclude(external_id__isnull=True).count(), 2)

    def test_pot_name_without_statement_account_is_rejected(self):
        res, data = self.call("stage_entries", batch={"kind": "chat"}, entries=[
            {"kind": "TRANSFER", "description": "Guardar", "amount": "10", "date": "2026-10-14",
             "from_account_id": self.account.pk, "to_account_name": "Viagem"}])
        self.assertTrue(res.is_error)
        self.assertIn("account_id", data)
