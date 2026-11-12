"""Telas do site: lotes (confirmar, descartar, desfazer), regras e gasto com IA."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import PaymentMethod
from assistant.models import Conversation, ImportBatch, StagedEntry, UserRule
from core.models import Category
from financial.models import Transaction

CHAT = 222


class SiteBatchTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("leo", password="x"))
        self.conv = Conversation.objects.create(chat_id=CHAT, provider="fake", model="fake", prompt_hash="x",
                                                last_activity_at=timezone.now())
        self.pix = PaymentMethod.objects.create(name="Pix Itaú", type="PIX")
        self.food = Category.objects.create(name="Mercado", type="EXPENSE")

    def staged(self, description="Padaria", amount="12.50"):
        batch = ImportBatch.objects.create(chat_id=CHAT, kind=ImportBatch.Kind.CHAT, title=description)
        StagedEntry.objects.create(batch=batch, position=1, kind=StagedEntry.Kind.EXPENSE, description=description,
                                   amount=Decimal(amount), date=date.today(), category=self.food,
                                   payment_method=self.pix)
        return batch

    def act(self, batch, action, version=None):
        data = {} if version is None else {"version": version}
        return self.client.post(reverse("assistant:batch_action", args=[batch.pk, action]), data)

    def test_staged_detail_shows_checks_and_actions(self):
        batch = self.staged()
        response = self.client.get(reverse("assistant:batch_detail", args=[batch.pk]))
        self.assertContains(response, "Conferências")
        self.assertContains(response, "Confirmar lote")
        self.assertContains(response, "Descartar")

    def test_confirm_from_site_records_and_tells_the_bot(self):
        batch = self.staged()
        response = self.act(batch, "confirmar", batch.version)
        self.assertRedirects(response, reverse("assistant:batch_detail", args=[batch.pk]))
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.CONFIRMED)
        self.assertTrue(Transaction.objects.filter(description="Padaria", amount=Decimal("12.50")).exists())
        self.conv.refresh_from_db()
        self.assertTrue(any("pelo site" in note for note in self.conv.pending_notes))

    def test_confirm_with_old_version_records_nothing(self):
        batch = self.staged()
        self.act(batch, "confirmar", batch.version + 1)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.STAGED)
        self.assertFalse(Transaction.objects.exists())

    def test_discard_from_site(self):
        batch = self.staged()
        self.act(batch, "descartar", batch.version)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.DISCARDED)
        self.assertFalse(Transaction.objects.exists())

    def test_only_the_last_confirmed_batch_can_be_undone(self):
        first, second = self.staged("Padaria"), self.staged("Feira", "30.00")
        self.act(first, "confirmar", first.version)
        ImportBatch.objects.filter(pk=first.pk).update(committed_at=timezone.now() - timedelta(minutes=5))
        self.act(second, "confirmar", second.version)

        self.act(first, "desfazer")
        first.refresh_from_db()
        self.assertEqual(first.status, ImportBatch.Status.CONFIRMED)
        response = self.client.get(reverse("assistant:batch_detail", args=[first.pk]))
        self.assertNotContains(response, "Desfazer lote")

        self.act(second, "desfazer")
        second.refresh_from_db()
        self.assertEqual(second.status, ImportBatch.Status.UNDONE)
        self.assertFalse(Transaction.objects.filter(description="Feira").exists())
        self.assertTrue(Transaction.objects.filter(description="Padaria").exists())

    def test_unknown_action_is_404(self):
        batch = self.staged()
        self.assertEqual(self.act(batch, "apagar", batch.version).status_code, 404)


class SiteRuleAndCostTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("leo", password="x"))

    def test_rule_toggle_and_pages(self):
        rule = UserRule.objects.create(text="Posto Y é Combustível.")
        response = self.client.post(reverse("assistant:rule_toggle", args=[rule.pk]), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        rule.refresh_from_db()
        self.assertFalse(rule.active)
        for name in ("assistant:rule_list", "assistant:cost", "assistant:batch_list"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
