import json
from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import PaymentMethod
from assistant.models import Conversation, ImportBatch, StagedEntry
from financial.models import Transaction
from telegram_bot import bot
from telegram_bot.client import is_allowed, split_text
from telegram_bot.models import TelegramUpdate

CHAT = 111


@override_settings(TELEGRAM_WEBHOOK_SECRET="segredo", TELEGRAM_ALLOWED_CHAT_IDS="111")
class WebhookTests(TestCase):
    url = "/telegram/webhook/segredo/"

    def post(self, payload, token="segredo"):
        headers = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": token} if token else {}
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json", **headers)

    def test_requires_secret_header(self):
        self.assertEqual(self.post({"update_id": 1}, token=None).status_code, 403)
        self.assertEqual(self.post({"update_id": 1}, token="errado").status_code, 403)
        self.assertEqual(self.client.post("/telegram/webhook/outro/", data="{}",
                                          content_type="application/json").status_code, 403)

    def test_queues_message_once(self):
        update = {"update_id": 10, "message": {"message_id": 1, "chat": {"id": CHAT}, "text": "oi"}}
        self.assertEqual(self.post(update).status_code, 200)
        self.assertEqual(self.post(update).status_code, 200)  # reenvio do Telegram
        record = TelegramUpdate.objects.get()
        self.assertEqual((record.status, record.chat_id), ("pending", CHAT))


@override_settings(TELEGRAM_ALLOWED_CHAT_IDS="111")
class CallbackTests(TestCase):
    def setUp(self):
        pm = PaymentMethod.objects.create(name="Pix", type="PIX")
        self.batch = ImportBatch.objects.create(chat_id=CHAT, kind="chat", payment_method=pm, version=3)
        StagedEntry.objects.create(batch=self.batch, position=1, kind="EXPENSE", description="Almoço",
                                   amount="45.00", date=timezone.now().date(), category_name="Alimentação")
        Conversation.objects.create(chat_id=CHAT, provider="anthropic", model="m", prompt_hash="h",
                                    last_activity_at=timezone.now())

    def callback(self, data, update_id=20):
        return {"update_id": update_id, "callback_query": {
            "id": "cb", "data": data, "message": {"message_id": 5, "chat": {"id": CHAT}}}}

    @mock.patch("telegram_bot.client.call", return_value={"ok": True})
    def test_confirm_button_commits_batch(self, call):
        bot.ingest_update(self.callback(f"b:c:{self.batch.pk}:3"))
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, "confirmed")
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(TelegramUpdate.objects.get().status, "done")
        self.assertIn("confirmou o lote", Conversation.objects.get().pending_notes[0])

    @mock.patch("telegram_bot.client.call", return_value={"ok": True})
    def test_stale_button_does_not_commit(self, call):
        bot.ingest_update(self.callback(f"b:c:{self.batch.pk}:2"))
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, "staged")
        self.assertEqual(Transaction.objects.count(), 0)

    @mock.patch("telegram_bot.client.call", return_value={"ok": True})
    @override_settings(TELEGRAM_ALLOWED_CHAT_IDS="999")
    def test_other_chats_are_ignored(self, call):
        bot.ingest_update(self.callback(f"b:c:{self.batch.pk}:3"))
        self.assertEqual(Transaction.objects.count(), 0)


class ClientTests(TestCase):
    @override_settings(TELEGRAM_ALLOWED_CHAT_IDS="")
    def test_empty_allowlist_denies_everyone(self):
        self.assertFalse(is_allowed(123))

    def test_split_text(self):
        chunks = split_text("linha\n" * 2000, limit=4096)
        self.assertTrue(all(len(c) <= 4096 for c in chunks))
        self.assertEqual("".join(c + "\n" for c in chunks).count("linha"), 2000)


@override_settings(TELEGRAM_ALLOWED_CHAT_IDS="111")
class WorkerFlowTests(TestCase):
    """Fila -> worker -> agente (provedor simulado) -> resumo com botões."""

    def test_message_becomes_batch_summary(self):
        from django.core.management import call_command

        from assistant.tests.test_agent import FakeProvider
        from assistant.tools.registry import ToolCall

        pm = PaymentMethod.objects.create(name="Pix", type="PIX")
        provider = FakeProvider([
            ("", [ToolCall("a", "stage_entries", {
                "batch": {"kind": "chat", "payment_method_id": pm.pk},
                "entries": [{"kind": "EXPENSE", "description": "Almoço", "amount": "45",
                             "date": "2026-11-10", "category_name": "Alimentação"}]})]),
            lambda: ("", [ToolCall("b", "present_batch", {"batch_id": ImportBatch.objects.get().pk})]),
            ("Montei o lote, é só confirmar.", []),
        ])
        bot.ingest_update({"update_id": 30, "message": {"message_id": 9, "chat": {"id": CHAT},
                                                        "text": "almoço 45 no pix"}})
        sent = []

        def fake_call(method, payload=None, timeout=15):
            sent.append((method, payload))
            return {"ok": True, "result": {"message_id": 77}}

        with mock.patch("telegram_bot.bot.get_provider", return_value=provider), \
                mock.patch("telegram_bot.client.call", side_effect=fake_call):
            call_command("run_telegram_worker", "--once", "--quiet-seconds", "0")

        self.assertEqual(TelegramUpdate.objects.get().status, "done")
        texts = [p.get("text", "") for m, p in sent if m == "sendMessage"]
        self.assertIn("Montei o lote, é só confirmar.", texts)
        summary = next(p for m, p in sent if m == "sendMessage" and "reply_markup" in p)
        self.assertIn("Confirmar", summary["reply_markup"])
        self.assertEqual(ImportBatch.objects.get().telegram_message_id, 77)
        self.assertEqual(Transaction.objects.count(), 0)


@override_settings(TELEGRAM_ALLOWED_CHAT_IDS="111")
class DigestTests(TestCase):
    def setUp(self):
        from datetime import date
        from decimal import Decimal

        from accounts.models import BalanceSnapshot, BankAccount
        from core.models import Category
        from financial.models import Recurrence

        self.date, self.Decimal = date, Decimal
        cat = Category.objects.create(name="Mercado", type="EXPENSE")
        acct = BankAccount.objects.create(name="Inter", bank="Inter")
        pix = PaymentMethod.objects.create(name="Pix", type="PIX", bank_account=acct)
        card = PaymentMethod.objects.create(name="Visa", type="CREDIT", closing_day=27, due_day=10)
        BalanceSnapshot.objects.create(account=acct, date=date(2026, 11, 30), balance=Decimal("500"))
        Transaction.objects.create(type="EXPENSE", description="Compras", amount=Decimal("900"),
                                   date=date(2026, 11, 20), category=cat, payment_method=card, confirmed=True)
        Transaction.objects.create(type="EXPENSE", description="Feira", amount=Decimal("100"),
                                   date=date(2026, 10, 20), category=cat, payment_method=pix, confirmed=True)
        Recurrence.objects.create(description="Aluguel", amount=Decimal("2000"), type="EXPENSE", category=cat,
                                  payment_method=pix, frequency="MONTHLY", reference_day=15,
                                  start_date=date(2026, 1, 1))

    def test_digests_for_the_day(self):
        from telegram_bot.digests import build_digests

        keys = {d.key: d.text for d in build_digests(self.date(2026, 12, 7))}
        self.assertEqual(len(keys), 2)
        invoice = next(t for k, t in keys.items() if k.endswith(":2026-12:soon"))
        self.assertIn("vence em 3 dias (10/12): R$ 900,00", invoice)
        negative = next(t for k, t in keys.items() if k.startswith("negative:2026-12"))
        self.assertIn("-R$ 2.400,00", negative)

        day1 = {d.key: d.text for d in build_digests(self.date(2026, 12, 1))}
        self.assertIn("monthly:2026-11", day1)
        self.assertIn("Gastos: R$ 900,00 (R$ 800,00 a mais que em outubro, 800%)", day1["monthly:2026-11"])
        self.assertIn("Faturas que vencem em dezembro: R$ 900,00", day1["monthly:2026-11"])
        self.assertEqual(build_digests(self.date(2026, 12, 20))[0].key.split(":")[0], "negative")

    def test_command_sends_each_digest_once(self):
        from django.core.management import call_command

        from telegram_bot.models import DigestLog

        with mock.patch("telegram_bot.client.call", return_value={"ok": True}) as call:
            call_command("send_digests", "--date", "2026-12-07")
            first = call.call_count
            call_command("send_digests", "--date", "2026-12-07")
        self.assertEqual(first, 2)
        self.assertEqual(call.call_count, 2)  # segunda rodada não reenvia
        self.assertEqual(DigestLog.objects.count(), 2)


@override_settings(TELEGRAM_ALLOWED_CHAT_IDS="111", AI_PROVIDER="anthropic",
                   ANTHROPIC_EXTRACTION_MODEL="cheap", ANTHROPIC_EXTRACTION_FALLBACK_MODEL="")
class DocumentRoutingTests(TestCase):
    """PDF enviado ao bot: vai para a extração (batch por padrão, na hora com "agora")."""

    def setUp(self):
        import tempfile

        from assistant.tests.test_documents import make_pdf
        from assistant.tests.test_extraction import GOOD, FakeClient, invoice, message

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        override = override_settings(ASSISTANT_STORAGE_DIR=tmp.name)
        override.enable()
        self.addCleanup(override.disable)

        self.fake = FakeClient(direct=[message(invoice(GOOD))], batch_result=message(invoice(GOOD)))
        self.sent = []

        def fake_call(method, payload=None, timeout=15):
            self.sent.append((method, payload))
            return {"ok": True, "result": {"message_id": 5}}

        for target, kwargs in (
            ("telegram_bot.client.call", {"side_effect": fake_call}),
            ("telegram_bot.client.download_file", {"return_value": (make_pdf(), "documents/fatura.pdf")}),
            ("assistant.extraction.get_client", {"return_value": self.fake}),
        ):
            patcher = mock.patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def document(self, caption=None):
        msg = {"message_id": 3, "chat": {"id": CHAT},
               "document": {"file_id": "f1", "file_name": "fatura.pdf", "mime_type": "application/pdf"}}
        if caption:
            msg["caption"] = caption
        return [{"update_id": 40, "message": msg}]

    def texts(self):
        return [p.get("text", "") for m, p in self.sent if m == "sendMessage"]

    @override_settings(ASSISTANT_DOCUMENT_MODE="batch")
    def test_document_goes_to_batch_and_is_delivered_by_the_worker(self):
        from assistant.models import ExtractionJob

        bot.process_chat_updates(CHAT, self.document())
        self.assertEqual(ExtractionJob.objects.get().mode, "batch")
        self.assertIn("segundo plano", self.texts()[0])
        self.assertEqual(ImportBatch.objects.count(), 0)

        bot.deliver_finished_extractions()
        self.assertTrue(any("Li fatura.pdf" in t for t in self.texts()))
        summary = next(p for m, p in self.sent if m == "sendMessage" and "reply_markup" in p)
        self.assertIn("Confirmar", summary["reply_markup"])
        self.assertEqual(ImportBatch.objects.get().telegram_message_id, 5)
        self.assertEqual(Transaction.objects.count(), 0)

    @override_settings(ASSISTANT_DOCUMENT_MODE="batch")
    def test_caption_agora_reads_immediately(self):
        from assistant.models import ExtractionJob

        bot.process_chat_updates(CHAT, self.document(caption="agora, fatura de novembro"))
        job = ExtractionJob.objects.get()
        self.assertEqual((job.mode, job.caption), ("direct", "fatura de novembro"))
        self.assertEqual(ImportBatch.objects.count(), 1)

    @override_settings(ASSISTANT_DOCUMENT_MODE="agent")
    def test_agent_mode_keeps_the_interactive_flow(self):
        from assistant.models import ExtractionJob
        from assistant.tests.test_agent import FakeProvider

        provider = FakeProvider([("Li o arquivo.", [])])
        with mock.patch("telegram_bot.bot.get_provider", return_value=provider):
            bot.process_chat_updates(CHAT, self.document())
        self.assertEqual(ExtractionJob.objects.count(), 0)
        self.assertIn("Li o arquivo.", self.texts())


@override_settings(TELEGRAM_ALLOWED_CHAT_IDS="111")
class CommandTests(TestCase):
    """Comandos sem IA e o teto de gasto."""

    def setUp(self):
        self.sent = []

        def fake_call(method, payload=None, timeout=15):
            self.sent.append((method, payload))
            return {"ok": True, "result": {"message_id": 1}}

        patcher = mock.patch("telegram_bot.client.call", side_effect=fake_call)
        patcher.start()
        self.addCleanup(patcher.stop)

    def texts(self):
        return [p.get("text", "") for m, p in self.sent if m == "sendMessage"]

    def message(self, text):
        return [{"update_id": 1, "message": {"message_id": 1, "chat": {"id": CHAT}, "text": text}}]

    def test_terceiros_lists_who_owes(self):
        from core.models import Category, Entity

        bot.process_chat_updates(CHAT, self.message("/terceiros"))
        self.assertIn("Nenhuma compra de terceiros", self.texts()[-1])

        joao = Entity.objects.create(name="João", type="PERSON")
        pix = PaymentMethod.objects.create(name="Pix", type="PIX")
        cat = Category.objects.create(name="Outros", type="BOTH")
        for kind, amount in (("EXPENSE", "300"), ("INCOME", "120")):
            Transaction.objects.create(type=kind, description="x", amount=Decimal(amount), date=date(2026, 1, 5),
                                       category=cat, payment_method=pix, confirmed=True, on_behalf_of=joao)
        bot.process_chat_updates(CHAT, self.message("/terceiros"))
        self.assertIn("João: deve R$ 180,00", self.texts()[-1])
        self.assertIn("devolveu R$ 120,00", self.texts()[-1])

    def test_custo_reports_month_spend(self):
        bot.process_chat_updates(CHAT, self.message("/custo"))
        self.assertIn("Gasto com IA", self.texts()[-1])
        self.assertIn("US$ 0.00", self.texts()[-1])

    @override_settings(AI_MONTHLY_LIMIT_USD=Decimal("0.01"), AI_MONTHLY_BUDGET_USD=Decimal("0"))
    def test_over_limit_stops_ai_calls_but_not_commands(self):
        from django.utils import timezone

        from assistant.models import ChatMessage, Conversation

        conv = Conversation.objects.create(chat_id=CHAT, provider="anthropic", model="claude-opus-5-5",
                                           prompt_hash="x", last_activity_at=timezone.now(), closed_at=timezone.now())
        ChatMessage.objects.create(conversation=conv, role="assistant", native_content={}, model="claude-opus-5-5",
                                   usage={"input_tokens": 10_000, "output_tokens": 1000})
        provider = mock.Mock()
        with mock.patch("telegram_bot.bot.get_provider", return_value=provider), \
                mock.patch("assistant.agent.run_turn") as run_turn:
            bot.process_chat_updates(CHAT, self.message("quanto gastei este mês?"))
            run_turn.assert_not_called()
            self.assertIn("teto de gasto com IA", self.texts()[-1])
            bot.process_chat_updates(CHAT, self.message("/custo"))
            self.assertIn("Gasto com IA", self.texts()[-1])

    def test_old_bot_button_is_answered(self):
        bot.handle_callback({"id": "cb", "data": "confirm:12", "message": {"message_id": 5, "chat": {"id": CHAT}}})
        method, payload = self.sent[-1]
        self.assertEqual(method, "answerCallbackQuery")
        self.assertIn("versão antiga", payload["text"])


class ThirdPartyDigestTests(TestCase):
    def test_invoice_reminder_says_how_much_belongs_to_others(self):
        from core.models import Category, Entity
        from telegram_bot import digests

        card = PaymentMethod.objects.create(name="Nubank", type="CREDIT", closing_day=6, due_day=13)
        cat = Category.objects.create(name="Outros", type="BOTH")
        joao = Entity.objects.create(name="João", type="PERSON")
        for amount, person in (("400", None), ("100", joao)):
            Transaction.objects.create(type="EXPENSE", description="x", amount=Decimal(amount), date=date(2026, 11, 1),
                                       category=cat, payment_method=card, confirmed=True, on_behalf_of=person,
                                       invoice_month=date(2026, 11, 1))
        texts = [d.text for d in digests.invoice_due_digests(date(2026, 11, 11))]
        self.assertEqual(len(texts), 1)
        self.assertIn("R$ 500,00", texts[0])
        self.assertIn("é de terceiros: João R$ 100,00", texts[0])
