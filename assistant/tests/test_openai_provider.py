import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from django.test import TestCase, override_settings

from accounts.models import PaymentMethod
from assistant import agent
from assistant.models import Attachment, ChatMessage, ImportBatch
from assistant.providers import Part
from assistant.providers.openai_provider import OpenAIProvider
from assistant.tools import TOOLS

CHAT = 111


def completion(content=None, tool_calls=(), finish_reason=None, refusal=None):
    calls = [SimpleNamespace(id=cid, type="function",
                             function=SimpleNamespace(name=name, arguments=arguments))
             for cid, name, arguments in tool_calls]
    message = SimpleNamespace(content=content, tool_calls=calls or None, refusal=refusal)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason or ("tool_calls" if calls else "stop"))
    usage = SimpleNamespace(model_dump=lambda mode="json": {"prompt_tokens": 5})
    return SimpleNamespace(choices=[choice], usage=usage, model="gpt-test")


class FakeOpenAI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.files = SimpleNamespace(create=lambda file, purpose: SimpleNamespace(id="file-123"))

    def _create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs["messages"])))
        item = self.responses.pop(0)
        return item() if callable(item) else item


@override_settings(OPENAI_MODEL="gpt-test")
class OpenAIProviderTests(TestCase):
    def test_full_turn_with_tool_calls(self):
        pix = PaymentMethod.objects.create(name="Pix", type="PIX")
        stage = json.dumps({"batch": {"kind": "chat", "payment_method_id": pix.pk},
                            "entries": [{"kind": "EXPENSE", "description": "Almoço", "amount": "45",
                                         "date": "2026-11-10"}]})
        client = FakeOpenAI([
            completion(tool_calls=[("c1", "stage_entries", stage), ("c2", "get_reference_data", "{nao é json")]),
            lambda: completion(tool_calls=[("c3", "present_batch",
                                            json.dumps({"batch_id": ImportBatch.objects.get().pk}))]),
            completion(content="Lote pronto."),
        ])
        provider = OpenAIProvider(client=client)
        result = agent.run_turn(CHAT, [Part("text", text="almoço 45 no pix")], provider=provider)

        self.assertEqual(result.text, "Lote pronto.")
        self.assertEqual(len(result.batches_to_present), 1)
        # 2ª requisição: system, user, nota, assistant (2 chamadas) e UMA mensagem tool por chamada
        roles = [m["role"] for m in client.requests[1]]
        self.assertEqual(roles, ["system", "user", "system", "assistant", "tool", "tool"])
        self.assertTrue(client.requests[1][5]["content"].startswith("ERRO:"))  # JSON inválido rejeitado
        self.assertEqual(ChatMessage.objects.filter(role="tool").count(), 2)

    def test_stop_reasons_and_schema(self):
        provider = OpenAIProvider(client=FakeOpenAI([completion(content=None, refusal="não posso"),
                                                     completion(content="x", finish_reason="length")]))
        self.assertEqual(provider.run_step("s", [], TOOLS).stop_reason, "refusal")
        self.assertEqual(provider.run_step("s", [], TOOLS).stop_reason, "max_tokens")
        names = [t["function"]["name"] for t in provider.tool_definitions(TOOLS)]
        self.assertIn("get_cash_flow_forecast", names)

    def test_attachments(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf, img = Path(tmp) / "f.pdf", Path(tmp) / "c.jpg"
            pdf.write_bytes(b"%PDF-1.4")
            img.write_bytes(b"\xff\xd8\xff")
            a_pdf = Attachment.objects.create(kind="pdf", filename="f.pdf", mime="application/pdf",
                                              sha256="a", storage_path=str(pdf))
            a_img = Attachment.objects.create(kind="image", filename="c.jpg", mime="image/jpeg",
                                              sha256="b", storage_path=str(img))
            client = FakeOpenAI([completion(content="ok")])
            provider = OpenAIProvider(client=client)
            message = provider.user_message([Part("attachment", attachment=a_pdf),
                                             Part("attachment", attachment=a_img), Part("text", text="veja")])
            self.assertEqual(message["content"][0], {"type": "file", "file": {"file_id": "file-123"}})
            self.assertNotIn("base64", json.dumps(message))  # histórico guarda só a referência
            provider.run_step("s", [message], TOOLS)
            sent = client.requests[0][1]["content"][1]
            self.assertTrue(sent["image_url"]["url"].startswith("data:image/jpeg;base64,"))
