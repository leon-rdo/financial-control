"""Cartão emprestado: compras de pessoas de fora da família e a devolução delas."""

from datetime import date
from decimal import Decimal

from accounts.models import BankAccount
from assistant import batch_service
from assistant.models import ImportBatch, UserRule
from core.models import Entity, FamilyMember
from financial import forecast
from financial.models import Purchase, Transaction

from .test_batches import BatchTestCase

NOV = (date(2026, 11, 1), date(2026, 11, 30))


class ThirdPartyTests(BatchTestCase):
    def commit(self, batch_id):
        batch = ImportBatch.objects.get(pk=batch_id)
        result = batch_service.commit(batch.pk, batch.version)
        self.assertTrue(result.ok, result.message)
        return batch

    def test_purchase_stays_on_invoice_but_out_of_family_spending(self):
        _, data = self.stage_invoice([
            {"kind": "EXPENSE", "description": "Mercado", "amount": "150.00", "date": "2026-11-10",
             "category_id": self.food.pk},
            {"kind": "EXPENSE", "description": "Loja de tênis", "amount": "100.00", "date": "2026-11-12",
             "on_behalf_of_name": "João"},
        ])
        totals = data["totals"]
        self.assertEqual(Decimal(str(totals["invoice_difference"])), Decimal("0"))  # a fatura continua batendo
        self.assertEqual(Decimal(str(totals["third_party"]["João"])), Decimal("100.00"))
        self.assertFalse(Entity.objects.filter(name="João").exists())      # nada gravado antes de confirmar
        self.commit(data["batch_id"])

        joao = Entity.objects.get(name="João")
        self.assertEqual(joao.type, "PERSON")
        self.assertEqual(Transaction.objects.get(description="Loja de tênis").on_behalf_of, joao)

        summary = forecast.spending_summary(*NOV)
        self.assertEqual((summary["total"], summary["third_party_total"]), (Decimal("150.00"), Decimal("100.00")))
        self.assertEqual(forecast.spending_summary(*NOV, third_party="only")["total"], Decimal("100.00"))
        self.assertEqual(forecast.spending_summary(*NOV, third_party="include")["total"], Decimal("250.00"))

        invoice = forecast.invoice_forecast((2026, 12), (2026, 12), today=date(2026, 11, 20))[0]["methods"][0]
        self.assertEqual(invoice["total"], Decimal("250.00"))              # o banco cobra tudo
        self.assertEqual(invoice["third_party"], [{"person": "João", "total": Decimal("100.00")}])

        owed = forecast.third_party_balances(today=date(2026, 11, 20))["people"][0]
        self.assertEqual((owed["due"], owed["upcoming"]), (Decimal("0"), Decimal("100.00")))  # fatura de dezembro
        owed = forecast.third_party_balances(today=date(2026, 12, 5))["people"][0]
        self.assertEqual((owed["due"], owed["balance"]), (Decimal("100.00"), Decimal("100.00")))

    def test_installments_follow_the_person_on_later_invoices(self):
        _, data = self.stage_invoice([
            {"kind": "INSTALLMENT_CHARGE", "description": "Celular", "amount": "250.00", "date": "2026-11-05",
             "installment_number": 1, "installments_total": 4, "on_behalf_of_name": "João"}])
        self.commit(data["batch_id"])
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.on_behalf_of.name, "João")

        # fatura seguinte: a parcela 2/4 já existe e vem como dele, sem ninguém marcar de novo
        _, data = self.stage_invoice(
            [{"kind": "INSTALLMENT_CHARGE", "description": "Celular", "amount": "250.00", "date": "2026-11-05",
              "installment_number": 2, "installments_total": 4}],
            invoice_month="2027-01", invoice_due_date="2027-01-10", invoice_closing_date="2027-01-03")
        self.assertEqual(self.entries(data["batch_id"])[0]["match_status"], "duplicate")
        self.assertEqual(Decimal(str(data["totals"]["third_party"]["João"])), Decimal("250.00"))

        owed = forecast.third_party_balances(today=date(2026, 12, 15))["people"][0]
        self.assertEqual((owed["charged_total"], owed["due"], owed["upcoming"]),
                         (Decimal("1000.00"), Decimal("250.00"), Decimal("750.00")))
        self.assertEqual([m["month"] for m in owed["by_month"]], ["2026-12", "2027-01", "2027-02", "2027-03"])
        self.assertEqual(forecast.spending_summary(date(2026, 12, 1), date(2026, 12, 31))["total"], Decimal("0"))

    def test_marking_an_item_already_registered_tags_the_existing_record(self):
        tx = Transaction.objects.create(type="EXPENSE", description="Farmácia", amount=Decimal("80"),
                                        date=date(2026, 11, 8), category=self.food, payment_method=self.card,
                                        confirmed=True)
        _, data = self.stage_invoice([{"kind": "EXPENSE", "description": "FARMACIA SA", "amount": "80.00",
                                       "date": "2026-11-08"}], invoice_total="80.00")
        self.assertEqual(self.entries(data["batch_id"])[0]["match_status"], "duplicate")
        _, data = self.call("edit_staged_entries", batch_id=data["batch_id"],
                            edits=[{"position": 1, "on_behalf_of_name": "Ana Paula"}])
        self.assertEqual(data["entries"][0]["on_behalf_of"], "Ana Paula")
        self.assertFalse(data["entries"][0]["include"])                    # continua sem duplicar
        batch = self.commit(data["batch_id"])
        tx.refresh_from_db()
        self.assertEqual(tx.on_behalf_of.name, "Ana Paula")
        self.assertEqual(Transaction.objects.count(), 1)

        self.assertTrue(batch_service.undo(batch.pk).ok)
        tx.refresh_from_db()
        self.assertIsNone(tx.on_behalf_of)

    def test_repayment_is_not_family_income(self):
        joao = Entity.objects.create(name="João", type="PERSON")
        Transaction.objects.create(type="EXPENSE", description="Tênis", amount=Decimal("300"), date=date(2026, 11, 3),
                                   category=self.food, payment_method=self.pix, confirmed=True, on_behalf_of=joao)
        _, data = self.call("stage_entries", batch={"kind": "chat", "payment_method_id": self.pix.pk}, entries=[
            {"kind": "INCOME", "description": "Pix do João", "amount": "200.00", "date": "2026-11-15",
             "on_behalf_of_name": "joão"}])
        self.assertEqual(Decimal(str(data["totals"]["third_party_repayments"]["João"])), Decimal("200.00"))
        self.commit(data["batch_id"])
        repayment = Transaction.objects.get(type="INCOME")
        self.assertEqual((repayment.on_behalf_of, repayment.category.name), (joao, "Devoluções de terceiros"))

        owed = forecast.third_party_balances(today=date(2026, 11, 20))
        person = owed["people"][0]
        self.assertEqual((person["due"], person["repaid"], person["balance"]),
                         (Decimal("300"), Decimal("200.00"), Decimal("100.00")))
        self.assertEqual(owed["total_due"], Decimal("100.00"))

        _, data = self.call("query_transactions", start_date="2026-11-01", end_date="2026-11-30")
        totals = {k: Decimal(str(v)) for k, v in data["totals"].items()}
        self.assertEqual((totals["income"], totals["expense"]), (Decimal("0"), Decimal("0")))
        self.assertEqual((totals["third_party_expense"], totals["third_party_repaid"]),
                         (Decimal("300"), Decimal("200")))
        _, data = self.call("get_third_party_balances", person="João", include_items=True)
        self.assertEqual(len(data["people"][0]["items"]), 1)
        self.assertEqual(len(data["people"][0]["repayments"]), 1)

    def test_family_members_cannot_be_third_parties(self):
        FamilyMember.objects.create(name="Bia", aliases="BEATRIZ LIMA")
        result, text = self.stage_invoice([{"kind": "EXPENSE", "description": "x", "amount": "10", "date": "2026-11-10",
                                            "on_behalf_of_name": "Beatriz Lima"}])
        self.assertTrue(result.is_error)
        self.assertIn("é da família", text)
        result, text = self.call("mark_third_party", person_name="Bia", payment_method_ids=[self.card.pk])
        self.assertTrue(result.is_error)

    def test_lent_card_marks_purchases_by_default_and_existing_records_on_request(self):
        old = Transaction.objects.create(type="EXPENSE", description="Antiga", amount=Decimal("50"),
                                         date=date(2026, 10, 3), category=self.food, payment_method=self.card,
                                         confirmed=True)
        _, data = self.call("mark_third_party", person_name="Ana Paula", payment_method_ids=[self.card.pk])
        self.card.refresh_from_db()
        self.assertEqual(self.card.lent_to.name, "Ana Paula")
        old.refresh_from_db()
        self.assertIsNone(old.on_behalf_of)                                # só daqui para a frente

        _, ref = self.call("get_reference_data")
        self.assertEqual({m["name"]: m["lent_to"] for m in ref["payment_methods"]}["Nubank"], "Ana Paula")
        self.assertEqual(ref["third_parties"][0]["uses_cards"], ["Nubank"])

        _, data = self.stage_invoice([{"kind": "EXPENSE", "description": "Posto", "amount": "250.00",
                                       "date": "2026-11-10"}])
        self.assertEqual(self.entries(data["batch_id"])[0]["on_behalf_of"], "Ana Paula")
        # o usuário pode dizer que uma compra daquele cartão foi da família
        _, data = self.call("edit_staged_entries", batch_id=data["batch_id"],
                            edits=[{"position": 1, "on_behalf_of_name": ""}])
        self.assertNotIn("on_behalf_of", data["entries"][0])

        _, data = self.call("mark_third_party", person_name="Ana Paula", transaction_ids=[old.pk])
        old.refresh_from_db()
        self.assertEqual(old.on_behalf_of.name, "Ana Paula")
        _, data = self.call("mark_third_party", clear=True, transaction_ids=[old.pk])
        old.refresh_from_db()
        self.assertIsNone(old.on_behalf_of)

    def test_transfer_cannot_be_third_party(self):
        account = BankAccount.objects.create(name="Conta", bank="Banco")
        result, text = self.call("stage_entries", batch={"kind": "chat"}, entries=[
            {"kind": "TRANSFER", "description": "x", "amount": "10", "date": "2026-11-10",
             "from_account_id": account.pk, "on_behalf_of_name": "João"}])
        self.assertTrue(result.is_error)


class UserRuleTests(BatchTestCase):
    def test_rules_are_saved_listed_and_replaced(self):
        _, data = self.call("save_user_rule", text="Pix para a  ACME LTDA é despesa")
        rule_id = data["saved"]["id"]
        self.assertEqual(data["saved"]["text"], "Pix para a ACME LTDA é despesa")
        _, ref = self.call("get_reference_data")
        self.assertEqual(ref["user_rules"], [{"id": rule_id, "text": "Pix para a ACME LTDA é despesa"}])

        _, data = self.call("save_user_rule", text="Pix para a ACME LTDA é transferência", remove_rule_id=rule_id)
        self.assertEqual([r["text"] for r in data["user_rules"]], ["Pix para a ACME LTDA é transferência"])
        self.assertEqual(UserRule.objects.filter(active=True).count(), 1)

        result, _ = self.call("save_user_rule")
        self.assertTrue(result.is_error)
        result, _ = self.call("save_user_rule", remove_rule_id=9999)
        self.assertTrue(result.is_error)

    def test_extraction_request_carries_rules_and_third_parties(self):
        import json
        from types import SimpleNamespace

        from assistant.tools.reference import GetReferenceDataInput, get_reference_data

        UserRule.objects.create(text="Pagamento de fatura no extrato do Banco X é do cartão Nubank")
        data = json.loads(json.dumps(get_reference_data(GetReferenceDataInput(), SimpleNamespace(chat_id=None)),
                                     default=str))
        self.assertEqual(len(data["user_rules"]), 1)
        self.assertEqual(data["third_parties"], [])
