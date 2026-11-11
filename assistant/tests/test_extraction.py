import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase, override_settings

from accounts.models import PaymentMethod
from assistant import extraction
from assistant.models import Attachment, Conversation, ExtractionJob, ImportBatch
from financial.models import Transaction

CHAT = 111


def message(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    usage = SimpleNamespace(to_dict=lambda mode="json": {"input_tokens": 100, "output_tokens": 50})
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)], usage=usage)


class FakeClient:
    """Cliente Anthropic simulado: respostas roteirizadas para chamadas diretas e batches."""

    def __init__(self, direct=(), batch_result=None, batch_ended=True):
        self.direct = list(direct)
        self.requests = []
        self.batch_result = batch_result
        self.batch_ended = batch_ended
        self.messages = SimpleNamespace(stream=self._stream, batches=SimpleNamespace(
            create=self._create, retrieve=self._retrieve, results=self._results))

    @contextmanager
    def _stream(self, **params):
        self.requests.append(params)
        yield SimpleNamespace(get_final_message=lambda: self.direct.pop(0))

    def _create(self, requests):
        self.requests.append(requests[0]["params"])
        return SimpleNamespace(id="msgbatch_1")

    def _retrieve(self, batch_id):
        return SimpleNamespace(processing_status="ended" if self.batch_ended else "in_progress")

    def _results(self, batch_id):
        return [SimpleNamespace(custom_id="job-1",
                                result=SimpleNamespace(type="succeeded", message=self.batch_result))]


def invoice(entries, total="150.00"):
    return {
        "batch": {"kind": "invoice", "invoice_month": "2026-11", "invoice_total": total,
                  "invoice_due_date": "2026-11-10", "new_payment_method": {"name": "Final 1111"}},
        "entries": entries,
        "summary": "Fatura do cartão final 1111.",
        "questions": ["De qual conta saiu o pagamento?"],
    }


GOOD = [
    {"kind": "EXPENSE", "description": "Mercado", "amount": "100.00", "date": "2026-10-05",
     "source_text": "05/10 MERCADO BOM SAO PAULO 100,00"},
    {"kind": "INSTALLMENT_CHARGE", "description": "Milhas", "amount": "50.00", "date": "2026-08-24",
     "installment_number": 3, "installments_total": 8, "source_text": "24/08 MILHAS*Comp 03/08 BARUERI 50,00"},
]
INSTALLMENT_AS_EXPENSE = [GOOD[0], {**GOOD[1], "kind": "EXPENSE", "installment_number": None,
                                    "installments_total": None}]


@override_settings(ANTHROPIC_EXTRACTION_MODEL="cheap", ANTHROPIC_EXTRACTION_FALLBACK_MODEL="strong",
                   ASSISTANT_DOCUMENT_MODE="batch", AI_PROVIDER="anthropic")
class ExtractionTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "fatura.pdf"
        path.write_bytes(b"%PDF-1.4 teste")
        self.attachment = Attachment.objects.create(kind="pdf", filename="fatura.pdf", mime="application/pdf",
                                                    sha256="abc", storage_path=str(path))
        PaymentMethod.objects.create(name="Pix", type="PIX")

    def use(self, client):
        patcher = mock.patch.object(extraction, "get_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_direct_extraction_builds_a_batch_without_writing_records(self):
        client = self.use(FakeClient(direct=[message(invoice(GOOD))]))
        result = extraction.run_direct(CHAT, self.attachment, "fatura de novembro")

        self.assertFalse(result.needs_agent)
        batch = ImportBatch.objects.get()
        self.assertEqual(result.batches_to_present, [batch.pk])
        self.assertEqual(batch.entries.count(), 2)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertIn("De qual conta saiu o pagamento?", result.text)
        job = ExtractionJob.objects.get()
        self.assertEqual((job.status, job.mode, job.model, job.import_batch), ("done", "direct", "cheap", batch))
        self.assertEqual(job.usage["output_tokens"], 50)

        request = client.requests[0]
        self.assertEqual(request["model"], "cheap")
        self.assertEqual(request["messages"][0]["content"][0]["type"], "document")
        self.assertIn("fatura de novembro", request["messages"][0]["content"][1]["text"])
        self.assertIn("Pix", request["messages"][0]["content"][1]["text"])  # cadastros vão no pedido
        self.assertIn("source_text", request["system"])
        # o agente fica sabendo do lote para ajustes posteriores
        self.assertIn(f"lote #{batch.pk}", Conversation.objects.get().pending_notes[0])

    def test_installment_typed_as_plain_expense_is_caught_and_retried(self):
        # a soma bate (150,00), então só a conferência linha a linha pega este erro
        self.use(FakeClient(direct=[message(invoice(INSTALLMENT_AS_EXPENSE)), message(invoice(GOOD))]))
        result = extraction.run_direct(CHAT, self.attachment)
        self.assertFalse(result.needs_agent)
        first, second = ExtractionJob.objects.order_by("pk")
        self.assertEqual((first.status, second.status), ("fallback", "done"))
        self.assertIn("parcela 3/8", first.error)
        self.assertEqual(second.model, "cheap")  # 1ª nova tentativa: mesmo modelo
        self.assertEqual(ImportBatch.objects.filter(status="staged").count(), 1)

    def test_ladder_cheap_cheap_strong_then_agent(self):
        wrong_total = invoice(GOOD, total="999.00")
        client = self.use(FakeClient(direct=[message(wrong_total), message("não é json"),
                                             message(invoice(GOOD), stop_reason="max_tokens")]))
        result = extraction.run_direct(CHAT, self.attachment)
        self.assertTrue(result.needs_agent)
        self.assertEqual([r["model"] for r in client.requests], ["cheap", "cheap", "strong"])
        errors = list(ExtractionJob.objects.order_by("pk").values_list("error", flat=True))
        self.assertIn("não bate com o total da fatura", errors[0])
        self.assertIn("JSON", errors[1])
        self.assertIn("max_tokens", errors[2])
        self.assertFalse(ImportBatch.objects.filter(status="staged").exists())  # lote ruim descartado

    def test_batch_mode_submit_then_poll(self):
        client = self.use(FakeClient(batch_result=message(invoice(GOOD)), batch_ended=False))
        job = extraction.submit_batch(CHAT, self.attachment)
        self.assertEqual((job.status, job.provider_batch_id), ("submitted", "msgbatch_1"))
        self.assertNotIn("stream", client.requests[0])
        self.assertEqual(extraction.poll(), [])  # ainda processando

        client.batch_ended = True
        (result,) = extraction.poll()
        self.assertEqual(len(result.batches_to_present), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, "done")
        self.assertEqual(extraction.poll(), [])  # não entrega duas vezes

    def test_batch_result_that_fails_checks_is_retried_directly(self):
        client = self.use(FakeClient(batch_result=message(invoice(INSTALLMENT_AS_EXPENSE)),
                                     direct=[message(invoice(GOOD))]))
        extraction.submit_batch(CHAT, self.attachment)
        (result,) = extraction.poll()
        self.assertFalse(result.needs_agent)
        self.assertEqual(list(ExtractionJob.objects.order_by("pk").values_list("mode", "status")),
                         [("batch", "fallback"), ("direct", "done")])
        self.assertEqual(len(client.requests), 2)


class EvidenceTests(TestCase):
    def check(self, **fields):
        base = {"kind": "EXPENSE", "description": "x", "amount": "10.00", "date": "2026-10-05"}
        return extraction.evidence_problems([extraction.ExtractedEntry(**{**base, **fields})])

    def test_consistent_lines_pass(self):
        self.assertEqual(self.check(source_text="05/10 PADARIA SAO PAULO 10,00"), [])
        self.assertEqual(self.check(kind="REFUND", source_text="28/09 LOJA Suzano 10,00 -"), [])
        self.assertEqual(self.check(kind="INSTALLMENT_CHARGE", installment_number=2, installments_total=7,
                                    source_text="09/09 LOJA *OUTLET02/07 JACI 10,00"), [])
        # extrato: data com hífen, identificador longo, saldo na mesma linha
        self.assertEqual(self.check(source_text="01-10-2026 Pix enviado Fulano 181842759688 R$ -10,00 R$ 445,20"), [])
        self.assertEqual(self.check(), [])  # sem source_text não há o que conferir

    def test_mismatches_are_reported(self):
        self.assertIn("parcela 3/8", self.check(source_text="24/08 MILHAS*Comp 03/08 BARUERI 10,00")[0])
        self.assertIn("sinal de crédito", self.check(source_text="14/10 LOJA Belem 10,00 -")[0])
        self.assertIn("não aparece na linha", self.check(source_text="14/10 LOJA Belem 12,00")[0])
        self.assertIn("não confere", self.check(kind="INSTALLMENT_CHARGE", installment_number=2,
                                                installments_total=3,
                                                source_text="09/09 LOJA 02/07 JACI 10,00")[0])
