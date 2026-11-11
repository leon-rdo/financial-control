"""Conjunto FIXO de ferramentas do assistente. Não variar por conversa: o Claude
valida o histórico (e o cache) contra o mesmo conjunto de ferramentas."""

from . import queries, reference, staging
from .registry import Tool, ToolCall, ToolContext, ToolResult, execute as _execute

TOOLS: list[Tool] = [*reference.TOOLS, *queries.TOOLS, *staging.TOOLS]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def execute(call: ToolCall, ctx: ToolContext) -> ToolResult:
    return _execute(TOOLS_BY_NAME, call, ctx)


__all__ = ["TOOLS", "TOOLS_BY_NAME", "Tool", "ToolCall", "ToolContext", "ToolResult", "execute"]
