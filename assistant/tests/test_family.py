import json
from datetime import date
from decimal import Decimal

from django.utils import timezone

from accounts.models import BalanceSnapshot, BankAccount, PaymentMethod
from assistant import agent, batch_service
from assistant.models import ImportBatch
from assistant.providers import Part
from assistant.tests.test_agent import FakeProvider
from core.models import FamilyMember
from financial import forecast
from financial.models import Transaction, Transfer

from .test_batches import CHAT, BatchTestCase


class FamilyTests(BatchTestCase):
    def setUp(self):
        super().setUp()
        self.ana = FamilyMember.objects.create(name="Ana", aliases="ANA SOUZA LIMA", telegram_chat_id=CHAT)
        self.bia = FamilyMember.objects.create(name="Bia", aliases="BEATRIZ LIMA")
        self.acc_ana = BankAccount.objects.create(name="Conta Ana", bank="Banco A", holder=self.ana)
        self.acc_bia = BankAccount.objects.create(name="Conta Bia", bank="Banco B", holder=self.bia)
        self.pot = BankAccount.objects.create(name="Reserva", bank="Banco B", type="INVESTMENT", parent=self.acc_bia)
        self.pix.bank_account = self.acc_ana
        self.pix.save()
        self.pix_bia = PaymentMethod.objects.create(name="Pix Bia", type="PIX", bank_account=self.acc_bia)
        self.card.bank_account = self.acc_ana
        self.card.save()
        self.card_bia = PaymentMethod.objects.create(name="Adicional", type="CREDIT", billing_card=self.card,
                                                     holder=self.bia)

    def test_effective_holder_inheritance(self):
        self.assertEqual(self.pot.effective_holder, self.bia)            # caixinha herda da conta
        self.assertEqual(self.pix.effective_holder, self.ana)            # método herda da conta
        self.assertEqual(self.card_bia.effective_holder, self.bia)       # adicional com portador próprio
        plain = PaymentMethod.objects.create(name="Virtual", type="CREDIT", billing_card=self.card)
        self.assertEqual(plain.effective_holder, self.ana)               # sem portador: o do cartão principal

    def test_reference_data_shows_family_and_speaker(self):
        _, data = self.call("get_reference_data")
        members = {m["name"]: m for m in data["family_members"]}
        self.assertTrue(members["Ana"]["is_speaker"])
        self.assertFalse(members["Bia"]["is_speaker"])
        self.assertEqual(members["Bia"]["names_on_documents"], ["BEATRIZ LIMA"])
        holders = {m["name"]: m["holder"] for m in data["payment_methods"]}
        self.assertEqual((holders["Pix Itaú"], holders["Adicional"]), ("Ana", "Bia"))
        self.assertEqual({a["name"]: a["holder"] for a in data["bank_accounts"]}["Reserva"], "Bia")

    def test_spending_and_balances_by_person_keep_family_total(self):
        for pm, amount in ((self.pix, "100"), (self.card, "40"), (self.card_bia, "60"), (self.pix_bia, "30")):
            Transaction.objects.create(type="EXPENSE", description="x", amount=Decimal(amount),
                                       date=date(2026, 11, 5), category=self.food, payment_method=pm, confirmed=True)
        summary = forecast.spending_summary(date(2026, 11, 1), date(2026, 11, 30), "holder")
        self.assertEqual({r["label"]: r["total"] for r in summary["rows"]},
                         {"Ana": Decimal("140"), "Bia": Decimal("90")})
        self.assertEqual(summary["total"], Decimal("230"))

        for account, amount in ((self.acc_ana, "1000"), (self.acc_bia, "500"), (self.pot, "8000")):
            BalanceSnapshot.objects.create(account=account, date=date(2026, 11, 30), balance=Decimal(amount))
        balances = forecast.account_balances(date(2026, 11, 30))
        self.assertEqual(balances["by_holder"], {"Ana": {"available": Decimal("1000.00"), "reserved": Decimal("0")},
                                                 "Bia": {"available": Decimal("500.00"), "reserved": Decimal("8000.00")}})
        self.assertEqual((balances["available"], balances["reserved"]), (Decimal("1500.00"), Decimal("8000.00")))

    def test_transfer_between_spouses_is_not_spending_and_both_statements_merge(self):
        # extrato da Ana: Pix para a Bia (conta da Bia desconhecida no documento)
        _, data = self.call("stage_entries", batch={"kind": "statement", "account_id": self.acc_ana.pk}, entries=[
            {"kind": "TRANSFER", "description": "Pix enviado BEATRIZ LIMA", "amount": "300.00",
             "date": "2026-11-03", "from_account_id": self.acc_ana.pk, "external_ref": "P1"}])
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        # extrato da Bia: o mesmo Pix, do outro lado
        _, data = self.call("stage_entries", batch={"kind": "statement", "account_id": self.acc_bia.pk}, entries=[
            {"kind": "TRANSFER", "description": "Pix recebido ANA SOUZA LIMA", "amount": "300.00",
             "date": "2026-11-03", "to_account_id": self.acc_bia.pk, "external_ref": "Q9"}])
        self.assertEqual(data["entries"][0]["match_status"], "confirm_existing")
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)

        transfer = Transfer.objects.get()  # um registro só, com os dois lados
        self.assertEqual((transfer.from_account, transfer.to_account), (self.acc_ana, self.acc_bia))
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(forecast.spending_summary(date(2026, 11, 1), date(2026, 11, 30))["total"], Decimal("0"))
        balances = forecast.account_balances(date(2026, 11, 30))
        self.assertEqual(balances["available"], Decimal("0.00"))  # o dinheiro só mudou de mãos
        self.assertEqual({k: v["available"] for k, v in balances["by_holder"].items()},
                         {"Ana": Decimal("-300.00"), "Bia": Decimal("300.00")})

    def test_new_cards_get_holders_on_confirm(self):
        res, data = self.call("stage_entries", batch={
            "kind": "invoice", "invoice_month": "2026-11", "invoice_total": "10.00",
            "new_payment_method": {"name": "Final 1111", "new_bank_account_name": "Banco X", "holder_id": self.ana.pk},
            "additional_new_cards": [{"name": "Final 2222", "holder_id": self.bia.pk}]}, entries=[
            {"kind": "EXPENSE", "description": "Loja", "amount": "10.00", "date": "2026-10-06",
             "payment_method_name": "Final 2222"}])
        self.assertFalse(res.is_error, data)
        batch = ImportBatch.objects.get(pk=data["batch_id"])
        self.assertTrue(batch_service.commit(batch.pk, batch.version).ok)
        self.assertEqual(PaymentMethod.objects.get(name="Final 1111").holder, self.ana)
        self.assertEqual(PaymentMethod.objects.get(name="Final 2222").holder, self.bia)
        self.assertEqual(BankAccount.objects.get(name="Banco X").holder, self.ana)

    def test_family_tools(self):
        _, data = self.call("save_family_member", name="Caio", names_on_documents=["CAIO LIMA"], is_speaker=True)
        caio = FamilyMember.objects.get(name="Caio")
        self.assertEqual((caio.telegram_chat_id, caio.alias_list), (CHAT, ["CAIO LIMA"]))
        self.ana.refresh_from_db()
        self.assertIsNone(self.ana.telegram_chat_id)  # o chat passa a ser do Caio
        self.call("save_family_member", name="caio", names_on_documents=["CAIO LIMA", "C LIMA"])
        self.assertEqual(FamilyMember.objects.filter(name__iexact="caio").count(), 1)
        self.assertEqual(FamilyMember.objects.get(name="Caio").alias_list, ["CAIO LIMA", "C LIMA"])

        res, data = self.call("assign_holder", family_member_id=caio.pk, bank_account_ids=[self.acc_ana.pk],
                              payment_method_ids=[self.card_bia.pk])
        self.assertFalse(res.is_error, data)
        self.acc_ana.refresh_from_db()
        self.card_bia.refresh_from_db()
        self.assertEqual((self.acc_ana.holder, self.card_bia.holder), (caio, caio))
        res, _ = self.call("assign_holder", family_member_id=caio.pk, bank_account_ids=[9999])
        self.assertTrue(res.is_error)

    def test_agent_note_says_who_is_speaking(self):
        provider = FakeProvider([("ok", [])])
        agent.run_turn(CHAT, [Part("text", text="oi")], provider=provider)
        self.assertIn("Quem está falando: Ana.", provider.requests[0][1]["content"])
        provider = FakeProvider([("ok", [])])
        agent.run_turn(999, [Part("text", text="oi")], provider=provider)
        self.assertIn("ainda não identificada", provider.requests[0][1]["content"])
