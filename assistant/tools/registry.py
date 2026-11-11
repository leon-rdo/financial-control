"""Registro neutro de ferramentas (independe do provedor de IA)."""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)


class ToolInput(BaseModel):
    """Base das entradas de ferramenta: campos desconhecidos são erro, não ignorados."""

    model_config = ConfigDict(extra="forbid")


class ToolError(Exception):
    """Erro de uso da ferramenta: a mensagem volta para a IA corrigir a chamada."""


@dataclass
class ToolContext:
    conversation: object
    chat_id: int
    batches_to_present: list = field(default_factory=list)


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], dict]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Tipo não serializável: {type(value)}")


def to_json(data):
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def parse_amount(value):
    """Aceita '1234.56', '1.234,56', 'R$ 45,90'. Sempre positivo, 2 casas."""
    text = str(value).replace("R$", "").replace(" ", "").strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ToolError(f"Valor inválido: {value!r}. Use ponto decimal, ex.: 123.45")
    if amount <= 0:
        raise ToolError(f"Valor deve ser positivo: {value!r}")
    return amount


def parse_signed_amount(value):
    """Como parse_amount, mas aceita zero e negativo (saldos)."""
    text = str(value).replace("R$", "").replace(" ", "").strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ToolError(f"Valor inválido: {value!r}. Use ponto decimal, ex.: -123.45")


def parse_month(value):
    """'2026-12' -> (2026, 12)."""
    try:
        year, month = (int(x) for x in str(value).split("-")[:2])
        date(year, month, 1)
    except (ValueError, TypeError):
        raise ToolError(f"Mês inválido: {value!r}. Use AAAA-MM.")
    return year, month


def execute(tools_by_name, call, ctx):
    """Valida a entrada com pydantic e executa. Nunca lança exceção."""
    tool = tools_by_name.get(call.name)
    if tool is None:
        return ToolResult(call.id, f"Ferramenta desconhecida: {call.name}", is_error=True)
    try:
        args = tool.input_model.model_validate(call.input or {})
    except ValidationError as exc:
        return ToolResult(call.id, f"Entrada inválida para {call.name}: {exc}", is_error=True)
    try:
        output = tool.handler(args, ctx)
    except ToolError as exc:
        return ToolResult(call.id, str(exc), is_error=True)
    except Exception:
        logger.exception("Erro na ferramenta %s", call.name)
        return ToolResult(call.id, f"Erro interno ao executar {call.name}.", is_error=True)
    return ToolResult(call.id, to_json(output))
