"""Provedor OpenAI (Chat Completions com function calling).

Usado quando AI_PROVIDER=openai. O histórico fica no formato nativo da OpenAI;
uma conversa nunca mistura provedores (ver agent.get_conversation).
"""

import base64
import hashlib
import json
import logging
from pathlib import Path

import openai
from django.conf import settings

from ..tools.registry import ToolCall
from .base import Part, ProviderError, StepResult

logger = logging.getLogger(__name__)

# Imagens ficam no histórico como referência e só viram base64 na hora do envio
# (para não gravar megabytes em cada mensagem).
IMAGE_PLACEHOLDER = "x_attachment_image"

FINISH_REASONS = {"stop": "end_turn", "tool_calls": "tool_use", "function_call": "tool_use",
                  "length": "max_tokens", "content_filter": "refusal"}


class OpenAIProvider:
    name = "openai"

    def __init__(self, client=None):
        self.model = settings.OPENAI_MODEL
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = openai.OpenAI(api_key=settings.OPENAI_API_KEY or None, max_retries=3, timeout=600.0)
        return self._client

    # -- definição -----------------------------------------------------------

    def tool_definitions(self, tools):
        # Sem strict: o modo strict da OpenAI exige todos os campos como obrigatórios.
        # A entrada é validada com pydantic antes de executar (tools.registry.execute).
        return [
            {"type": "function",
             "function": {"name": t.name, "description": t.description,
                          "parameters": t.input_model.model_json_schema()}}
            for t in tools
        ]

    def fingerprint(self, system, tools):
        payload = json.dumps(
            {"provider": self.name, "model": self.model, "system": system,
             "tools": self.tool_definitions(tools)},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    # -- mensagens -----------------------------------------------------------

    def _upload(self, attachment):
        if attachment.provider == self.name and attachment.provider_file_id:
            return attachment.provider_file_id
        data = Path(attachment.storage_path).read_bytes()
        try:
            uploaded = self.client.files.create(
                file=(attachment.filename, data, attachment.mime), purpose="user_data")
        except openai.APIError as exc:
            raise ProviderError(f"Falha ao enviar arquivo para a OpenAI: {exc}") from exc
        attachment.provider = self.name
        attachment.provider_file_id = uploaded.id
        attachment.save(update_fields=["provider", "provider_file_id"])
        return uploaded.id

    def user_message(self, parts: list[Part]):
        files, texts = [], []
        for part in parts:
            if part.kind == "attachment":
                att = part.attachment
                if att.kind == "pdf":
                    files.append({"type": "file", "file": {"file_id": self._upload(att)}})
                elif att.kind == "image":
                    files.append({"type": IMAGE_PLACEHOLDER, "attachment_id": att.pk})
                else:
                    content = Path(att.storage_path).read_text(encoding="utf-8")
                    texts.append({"type": "text", "text": f"[Arquivo {att.filename}]\n{content}"})
            elif part.text:
                texts.append({"type": "text", "text": part.text})
        content = files + texts
        if not content:
            content = [{"type": "text", "text": "(mensagem vazia)"}]
        return {"role": "user", "content": content}

    def note_message(self, text):
        return {"role": "system", "content": text}

    def tool_results(self, results):
        # Uma mensagem `tool` por chamada (o agente achata listas no histórico)
        return [
            {"role": "tool", "tool_call_id": r.call_id,
             "content": ("ERRO: " if r.is_error else "") + r.content}
            for r in results
        ]

    def _expand(self, message):
        """Troca referências de imagem pelo conteúdo em base64."""
        content = message.get("content")
        if not isinstance(content, list) or not any(p.get("type") == IMAGE_PLACEHOLDER for p in content):
            return message
        from ..models import Attachment

        parts = []
        for part in content:
            if part.get("type") != IMAGE_PLACEHOLDER:
                parts.append(part)
                continue
            att = Attachment.objects.filter(pk=part["attachment_id"]).first()
            try:
                data = base64.standard_b64encode(Path(att.storage_path).read_bytes()).decode()
            except (AttributeError, OSError):
                parts.append({"type": "text", "text": "[imagem não está mais disponível]"})
                continue
            parts.append({"type": "image_url", "image_url": {"url": f"data:{att.mime};base64,{data}"}})
        return {**message, "content": parts}

    # -- chamada -------------------------------------------------------------

    def run_step(self, system, history, tools):
        messages = [{"role": "system", "content": system}, *(self._expand(m) for m in history)]
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=self.tool_definitions(tools))
        except openai.RateLimitError as exc:
            raise ProviderError("Limite de uso da API da OpenAI atingido. Tente mais tarde.") from exc
        except openai.APIStatusError as exc:
            raise ProviderError(f"Erro da API da OpenAI ({exc.status_code}): {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderError("Sem conexão com a API da OpenAI.") from exc

        choice = response.choices[0]
        msg = choice.message
        native = {"role": "assistant", "content": msg.content}
        tool_calls = []
        function_calls = [tc for tc in (msg.tool_calls or []) if tc.type == "function"]
        if function_calls:
            native["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in function_calls
            ]
            for tc in function_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    if not isinstance(args, dict):
                        raise ValueError("argumentos não são um objeto")
                except ValueError:
                    # Campo desconhecido: a validação rejeita e o erro volta para o modelo
                    args = {"json_invalido": (tc.function.arguments or "")[:500]}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))

        stop_reason = FINISH_REASONS.get(choice.finish_reason, choice.finish_reason or "")
        if msg.refusal:
            stop_reason = "refusal"
            native["refusal"] = msg.refusal
        return StepResult(
            native_message=native,
            text=(msg.content or "").strip(),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=response.usage.model_dump(mode="json") if response.usage else {},
            model=response.model,
        )
