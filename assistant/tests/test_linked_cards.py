from datetime import date

from accounts.models import PaymentMethod
from assistant import batch_service
from assistant.models import ImportBatch
from financial.models import InvoiceClosing

from .test_batches import BatchTestCase


class LinkExistingCardsTests(BatchTestCase):
    def setUp(self):
        super().setUp()
        self.extra = PaymentMethod.objects.create(name="Final 9999", type="CREDIT")

    def commit(self, batch_id):
        batch = ImportBatch.objects.get(pk=batch_id)
        result = batch_service.commit(batch.pk, batch.version)
        self.assertTrue(result.ok, result.message)
        return batch

    def stage(self, **batch):
        return self.stage_invoice([
            {"kind": "EXPENSE", "description": "Mercado", "amount": "150.00", "date": "2026-11-10"},
            {"kind": "EXPENSE", "description": "Farmácia", "amount": "100.00", "date": "2026-11-12",
             "payment_method_id": self.extra.pk},
        ], **batch)

    def test_link_happens_only_on_confirm_and_is_undone(self):
        _, data = self.stage(link_existing_card_ids=[self.extra.pk])
        self.assertEqual(data["cards_to_link_on_confirm"], ["Final 9999"])
        self.extra.refresh_from_db()
        self.assertIsNone(self.extra.billing_card_id)                      # nada mudou antes de confirmar
        batch = self.commit(data["batch_id"])
        self.extra.refresh_from_db()
        self.assertEqual(self.extra.billing_card_id, self.card.pk)

        self.assertTrue(batch_service.undo(batch.pk).ok)
        self.extra.refresh_from_db()
        self.assertIsNone(self.extra.billing_card_id)

    def test_summary_mentions_the_link(self):
        from telegram_bot import render

        _, data = self.stage(link_existing_card_ids=[self.extra.pk])
        summary, _ = render.batch_summary(ImportBatch.objects.get(pk=data["batch_id"]))
        self.assertIn("ligo à fatura de Nubank: Final 9999", summary)

    def test_invalid_links_are_rejected(self):
        result, text = self.stage(link_existing_card_ids=[self.card.pk])
        self.assertTrue(result.is_error)
        self.assertIn("cartão principal", text)

        PaymentMethod.objects.create(name="Já ligado", type="CREDIT", billing_card=self.extra)
        result, text = self.stage(link_existing_card_ids=[self.extra.pk])   # já tem cartões na fatura dele
        self.assertTrue(result.is_error)

        pix = PaymentMethod.objects.get(name="Pix Itaú")
        result, text = self.stage(link_existing_card_ids=[pix.pk])
        self.assertTrue(result.is_error)

    def test_already_linked_card_is_a_no_op(self):
        self.extra.billing_card = self.card
        self.extra.save()
        _, data = self.stage(link_existing_card_ids=[self.extra.pk])
        self.commit(data["batch_id"])
        self.extra.refresh_from_db()
        self.assertEqual(self.extra.billing_card_id, self.card.pk)

    def test_invoice_import_records_the_real_closing_and_undo_restores(self):
        _, data = self.stage()                                             # fechamento 03/12, vencimento 10/12
        batch = self.commit(data["batch_id"])
        closing = InvoiceClosing.objects.get()
        self.assertEqual((closing.card, closing.year, closing.month, closing.closing_date, closing.due_date),
                         (self.card, 2026, 12, date(2026, 12, 3), date(2026, 12, 10)))
        self.assertTrue(batch_service.undo(batch.pk).ok)
        self.assertFalse(InvoiceClosing.objects.exists())

    def test_reimport_updates_closing_and_undo_puts_the_previous_back(self):
        _, data = self.stage()
        self.commit(data["batch_id"])
        _, data = self.stage(invoice_closing_date="2026-12-01")
        batch = self.commit(data["batch_id"])
        self.assertEqual(InvoiceClosing.objects.get().closing_date, date(2026, 12, 1))
        batch_service.undo(batch.pk)
        self.assertEqual(InvoiceClosing.objects.get().closing_date, date(2026, 12, 3))
