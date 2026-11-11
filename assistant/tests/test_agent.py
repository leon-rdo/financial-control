from unittest import mock

from django.test import TestCase, override_settings

from accounts.models import PaymentMethod
from assistant import agent
from assistant.models import ChatMessage, Conversation, ImportBatch
from assistant.providers import Part, ProviderError, StepResult
from assistant.tools.registry import ToolCall
from financial.models import Transaction

CHAT = 111


class FakeProvider:
    """Provedor roteirizado: cada item de `script` é (texto, [ToolCall]), uma exceção,
    ou uma função sem argumentos que devolve um desses (calculado na hora)."""

    name = "fake"
    model = "fake-1"

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def fingerprint(self, system, tools):
        return "fp"

    def user_message(self, parts):
        return {"role": "user", "content": [{"type": "text", "text": p.text} for p in parts if p.text]}

    def note_message(self, text):
        return {"role": "system", "content": text}

    def tool_results(self, results):
        return {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content, "is_error": r.is_error}
            for r in results]}

    def run_step(self, system, history, tools):
        self.requests.append(list(history))
        item = self.script.pop(0)
        if callable(item):
            item = item()
        if isinstance(item, Exception):
            raise item
        text, calls = item
        content = ([{"type": "text", "text": text}] if text else []) + [
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls]
        return StepResult(native_message={"role": "assistant", "content": content}, text=text,
                          tool_calls=calls, stop_reason="tool_use" if calls else "end_turn",
                          usage={"input_tokens": 10}, model=self.model)


@override_settings(ASSISTANT_MAX_STEPS=6)
class AgentLoopTests(TestCase):
    def setUp(self):
        self.pix = PaymentMethod.objects.create(name="Pix", type="PIX")

    def test_tool_loop_stages_but_never_commits(self):
        provider = FakeProvider([
            ("", [ToolCall("a", "get_reference_data", {})]),
            ("", [ToolCall("b", "stage_entries", {"entries": [{"kind": "EXPENSE"}]})]),  # inválido
            ("", [ToolCall("c", "stage_entries", {
                "batch": {"kind": "chat", "payment_method_id": self.pix.pk},
                "entries": [{"kind": "EXPENSE", "description": "Almoço", "amount": "45,00",
                             "date": "2026-11-10"}]})]),
            ("", [ToolCall("d", "present_batch", {"batch_id": 0})]),  # id errado -> erro
            lambda: ("", [ToolCall("e", "present_batch", {"batch_id": ImportBatch.objects.get().pk})]),
            ("Lote pronto para confirmar.", []),
        ])
        result = agent.run_turn(CHAT, [Part("text", text="almoço 45 no pix")], provider=provider)

        self.assertFalse(result.error)
        self.assertEqual(result.text, "Lote pronto para confirmar.")
        self.assertEqual(Transaction.objects.count(), 0)
        batch = ImportBatch.objects.get()
        self.assertEqual(result.batches_to_present, [batch.pk])
        self.assertEqual(batch.entries.get().amount, 45)

        roles = list(ChatMessage.objects.values_list("role", flat=True))
        self.assertEqual(roles[:2], ["user", "note"])  # nota (data/hora) logo após o usuário
        self.assertEqual(roles.count("assistant"), 6)
        tool_msgs = ChatMessage.objects.filter(role="tool")
        self.assertTrue(any(c["is_error"] for m in tool_msgs for c in m.native_content["content"]))

    def test_provider_error_before_reply_rolls_back_turn(self):
        provider = FakeProvider([ProviderError("fora do ar")])
        result = agent.run_turn(CHAT, [Part("text", text="oi")], provider=provider)
        self.assertTrue(result.error)
        self.assertIn("fora do ar", result.text)
        self.assertEqual(ChatMessage.objects.count(), 0)

        provider = FakeProvider([("Olá!", [])])
        result = agent.run_turn(CHAT, [Part("text", text="oi de novo")], provider=provider)
        self.assertEqual(result.text, "Olá!")
        self.assertEqual(list(ChatMessage.objects.values_list("role", flat=True)), ["user", "note", "assistant"])

    def test_history_is_replayed_and_notes_are_delivered(self):
        agent.run_turn(CHAT, [Part("text", text="primeira")], provider=FakeProvider([("ok", [])]))
        agent.add_note(CHAT, "O usuário confirmou o lote #7.")
        provider = FakeProvider([("certo", [])])
        agent.run_turn(CHAT, [Part("text", text="segunda")], provider=provider)
        history = provider.requests[0]
        self.assertEqual([m["role"] for m in history], ["user", "system", "assistant", "user", "system"])
        self.assertIn("lote #7", history[-1]["content"])
        self.assertEqual(Conversation.objects.count(), 1)

    def test_new_conversation_when_fingerprint_changes(self):
        agent.run_turn(CHAT, [Part("text", text="a")], provider=FakeProvider([("ok", [])]))
        provider = FakeProvider([("ok", [])])
        with mock.patch.object(FakeProvider, "fingerprint", return_value="outro"):
            agent.run_turn(CHAT, [Part("text", text="b")], provider=provider)
        self.assertEqual(Conversation.objects.count(), 2)
        self.assertEqual(len(provider.requests[0]), 2)  # histórico novo: user + nota
