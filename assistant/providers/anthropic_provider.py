"""Provedor Claude (API da Anthropic)."""

import hashlib
import json
import logging
from pathlib import Path

import anthropic
from django.conf import settings

from ..tools.registry import ToolCall
from .base import Part, ProviderError, StepResult

logger = logging.getLogger(__name__)

# Se um filtro de segurança recusar um pedido legítimo, a API refaz o pedido
# em outro modelo (escolhido pela Anthropic conforme a categoria da recusa).
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 64000
FILE_TTL_SECONDS = 7 * 24 * 3600  # arquivos expiram sozinhos na Files API


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client=None):
        self.model = settings.ANTHROPIC_MODEL
        self.effort = settings.ANTHROPIC_EFFORT
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=settings.ANTHROPIC_API_KEY or None, max_retries=3, timeout=600.0
            )
        return self._client

    # -- definição -----------------------------------------------------------

    def tool_definitions(self, tools):
        # Sem `strict`: o schema de stage_entries (muitos campos opcionais) estoura o
        # limite de gramática da API ("compiled grammar is too large"). Sem
        # `eager_input_streaming`: a API entrega o JSON da ferramenta inteiro e
        # válido, o que importa mais aqui do que receber aos poucos. A entrada é
        # sempre validada com pydantic antes de executar (tools.registry.execute).
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": anthropic.transform_schema(t.input_model),
            }
            for t in tools
        ]

    def fingerprint(self, system, tools):
        payload = json.dumps(
            {"provider": self.name, "model": self.model, "effort": self.effort,
             "system": system, "tools": self.tool_definitions(tools)},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    # -- mensagens -----------------------------------------------------------

    def _upload(self, attachment):
        if attachment.provider == self.name and attachment.provider_file_id:
            return attachment.provider_file_id
        data = Path(attachment.storage_path).read_bytes()
        try:
            meta = self.client.files.upload(
                file=(attachment.filename, data, attachment.mime),
                expires_in_seconds=FILE_TTL_SECONDS,
            )
        except anthropic.APIError as exc:
            raise ProviderError(f"Falha ao enviar arquivo para a Anthropic: {exc}") from exc
        attachment.provider = self.name
        attachment.provider_file_id = meta.id
        attachment.save(update_fields=["provider", "provider_file_id"])
        return meta.id

    def user_message(self, parts: list[Part]):
        files, texts = [], []
        for part in parts:
            if part.kind == "attachment":
                att = part.attachment
                if att.kind == "pdf":
                    files.append({"type": "document", "title": att.filename[:200],
                                  "source": {"type": "file", "file_id": self._upload(att)}})
                elif att.kind == "image":
                    files.append({"type": "image", "source": {"type": "file", "file_id": self._upload(att)}})
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
        # Mensagem de sistema no meio da conversa: não invalida o cache do prefixo.
        return {"role": "system", "content": text}

    def tool_results(self, results):
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content, "is_error": r.is_error}
                for r in results
            ],
        }

    # -- chamada -------------------------------------------------------------

    @staticmethod
    def _sanitize_fallback(blocks):
        """Após um fallback no meio da resposta, blocos internos anteriores ao
        último `fallback` não podem ser reenviados (o `fallback` fica no lugar)."""
        last = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=None)
        if last is None:
            return blocks
        # Sem ferramentas de servidor neste app: antes do limite, só texto e
        # os próprios blocos `fallback` são reenviados.
        return [b for i, b in enumerate(blocks) if i >= last or b.get("type") in ("text", "fallback")]

    def run_step(self, system, history, tools):
        params = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": self.tool_definitions(tools),
            "messages": history,
            "output_config": {"effort": self.effort},
            "cache_control": {"type": "ephemeral"},
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }
        message = None
        for attempt in range(2):
            try:
                with self.client.beta.messages.stream(**params) as stream:
                    message = stream.get_final_message()
                break
            except ValueError as exc:
                # JSON de entrada de ferramenta que o SDK não conseguiu interpretar
                logger.warning("Entrada de ferramenta inválida no stream (tentativa %s): %s", attempt + 1, exc)
                if attempt == 1:
                    raise ProviderError("Resposta do modelo veio malformada.") from exc
            except anthropic.RateLimitError as exc:
                raise ProviderError("Limite de uso da API da Anthropic atingido. Tente mais tarde.") from exc
            except anthropic.APIStatusError as exc:
                raise ProviderError(f"Erro da API da Anthropic ({exc.status_code}): {exc.message}") from exc
            except anthropic.APIConnectionError as exc:
                raise ProviderError("Sem conexão com a API da Anthropic.") from exc

        blocks = self._sanitize_fallback([b.to_dict(mode="json") for b in message.content])
        tool_calls = [ToolCall(id=b["id"], name=b["name"], input=b.get("input") or {})
                      for b in blocks if b.get("type") == "tool_use"]
        text = "\n".join(b["text"] for b in blocks if b.get("type") == "text" and b.get("text")).strip()
        usage = message.usage.to_dict(mode="json") if message.usage else {}
        return StepResult(
            native_message={"role": "assistant", "content": blocks},
            text=text,
            tool_calls=tool_calls,
            stop_reason=message.stop_reason or "",
            usage=usage,
            model=message.model,
        )
