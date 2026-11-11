from datetime import date
from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from assistant import costs
from assistant.models import Attachment, ChatMessage, Conversation, ExtractionJob, SpendAlert

OPUS_USAGE = {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 10000,
              "cache_creation_input_tokens": 2000,
              "cache_creation": {"ephemeral_5m_input_tokens": 2000, "ephemeral_1h_input_tokens": 0}}
# 1000*4 + 2000*5 + 10000*0,20 + 500*20 = 26.000 / 1.000.000
OPUS_COST = Decimal("0.026")


class CostTests(TestCase):
    def setUp(self):
        self.conv = Conversation.objects.create(chat_id=1, provider="anthropic", model="claude-opus-5-5",
                                                prompt_hash="x", last_activity_at=timezone.now())

    def message(self, usage=OPUS_USAGE, model="claude-opus-5-5"):
        return ChatMessage.objects.create(conversation=self.conv, role=ChatMessage.Role.ASSISTANT,
                                          native_content={}, model=model, usage=usage)

    def test_call_cost(self):
        self.assertEqual(costs.call_cost("claude-opus-5-5", OPUS_USAGE), OPUS_COST)
        self.assertEqual(costs.call_cost("claude-opus-5-5", OPUS_USAGE, batch=True), OPUS_COST / 2)
        # escrita de cache de 1 hora custa 2x a entrada
        one_hour = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 1000,
                    "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 1000}}
        self.assertEqual(costs.call_cost("claude-sonnet-5-5", one_hour), Decimal("0.004"))
        # Haiku: preço maior acima de 100 mil tokens de prompt
        small = {"input_tokens": 50_000, "output_tokens": 1000}
        large = {"input_tokens": 200_000, "output_tokens": 1000}
        self.assertEqual(costs.call_cost("claude-haiku-5-5", small), Decimal("0.0055"))
        self.assertEqual(costs.call_cost("claude-haiku-5-5", large), Decimal("0.1025"))
        self.assertIsNone(costs.call_cost("modelo-desconhecido", small))

    @override_settings(AI_PRICES_JSON='{"gpt-x": {"input": "1", "output": "2", "cache_read": "0.5"}}')
    def test_openai_usage_and_custom_prices(self):
        usage = {"prompt_tokens": 1000, "completion_tokens": 100, "prompt_tokens_details": {"cached_tokens": 400}}
        # 600*1 + 400*0,5 + 100*2 = 1000 / 1.000.000
        self.assertEqual(costs.call_cost("gpt-x-2026-01-01", usage), Decimal("0.001"))

    def test_month_spend_splits_chat_and_documents(self):
        self.message()
        self.message(model="modelo-desconhecido")
        old = self.message()
        ChatMessage.objects.filter(pk=old.pk).update(created_at=timezone.now().replace(year=2020))
        attachment = Attachment.objects.create(conversation=self.conv, kind="pdf", filename="f.pdf", mime="application/pdf",
                                               sha256="a" * 64, storage_path="/tmp/f.pdf")
        ExtractionJob.objects.create(chat_id=1, attachment=attachment, mode="batch", model="claude-opus-5-5",
                                     usage=OPUS_USAGE)
        spend = costs.month_spend()
        self.assertEqual((spend["chat"], spend["documents"]), (OPUS_COST, OPUS_COST / 2))
        self.assertEqual((spend["calls"], spend["unpriced_calls"]), (3, 1))
        self.assertIn("US$ 0.04", costs.describe(spend))

    @override_settings(AI_MONTHLY_BUDGET_USD=Decimal("0.03"), AI_MONTHLY_LIMIT_USD=Decimal("0.05"),
                       ALERT_EMAIL="alerta@example.com", DEFAULT_FROM_EMAIL="no-reply@example.com")
    def test_alerts_once_per_level_and_limit(self):
        self.message()                                   # 0,026 = 87% do orçamento
        self.assertEqual(costs.send_alerts(), ["80"])
        self.assertEqual(costs.send_alerts(), [])        # não repete
        self.assertFalse(costs.over_limit())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alerta@example.com"])
        self.assertIn("80% do orçamento", mail.outbox[0].subject)

        self.message()                                   # 0,052: passa do orçamento e do teto de uma vez
        self.assertEqual(costs.send_alerts(), ["100", "limit"])
        self.assertTrue(costs.over_limit())
        self.assertEqual(len(mail.outbox), 2)            # um e-mail só, do nível mais alto
        self.assertIn("teto", mail.outbox[1].subject)
        self.assertEqual(SpendAlert.objects.count(), 3)
        # mês seguinte começa zerado
        today = date.today()
        self.assertFalse(costs.over_limit(date(today.year + 1, today.month, 1)))

    @override_settings(AI_MONTHLY_BUDGET_USD=Decimal("0"), AI_MONTHLY_LIMIT_USD=Decimal("0"))
    def test_zero_disables_budget_and_limit(self):
        self.message()
        self.assertEqual(costs.send_alerts(), [])
        self.assertFalse(costs.over_limit())
