"""Protocolo neutro de provedor de IA. Cada provedor guarda o histórico no seu
formato nativo (ChatMessage.native_content); o agente só usa esta interface."""

from dataclasses import dataclass, field
from typing import Protocol

from ..tools.registry import ToolCall, ToolResult


class ProviderError(Exception):
    """Falha ao falar com o provedor (rede, limite, resposta inválida)."""


@dataclass
class Part:
    """Parte de uma mensagem do usuário: texto ou anexo."""

    kind: str  # "text" | "attachment"
    text: str = ""
    attachment: object = None  # assistant.models.Attachment


@dataclass
class StepResult:
    native_message: dict
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    usage: dict = field(default_factory=dict)
    model: str = ""


class LLMProvider(Protocol):
    name: str
    model: str

    def fingerprint(self, system: str, tools: list) -> str: ...

    def user_message(self, parts: list[Part]) -> dict: ...

    def note_message(self, text: str) -> dict: ...

    def tool_results(self, results: list[ToolResult]) -> dict | list[dict]: ...

    def run_step(self, system: str, history: list[dict], tools: list) -> StepResult: ...
