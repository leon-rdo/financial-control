"""Quanto o assistente gastou com IA no mês, o teto e os avisos.

Cada chamada ao modelo já grava o uso de tokens (`ChatMessage.usage` no agente,
`ExtractionJob.usage` na leitura de documentos). Aqui isso vira dólares.

- `AI_MONTHLY_BUDGET_USD`: orçamento do mês. Avisa por e-mail aos 80% e aos 100%.
- `AI_MONTHLY_LIMIT_USD`: teto. Ao chegar nele o bot para de chamar a IA até o
  mês virar (comandos, botões e avisos automáticos continuam). 0 = sem teto.

Preços em US$ por milhão de tokens (tabela pública da Anthropic, nov/2026).
Escrita de cache custa 1,25x a entrada (5 min) ou 2x (1 h); a API de batches dá
50% em tudo. Modelos fora da tabela (por exemplo os da OpenAI) entram como
"sem preço": informe-os em AI_PRICES_JSON, no mesmo formato.
"""

import json
import logging
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings

from core.alerts import send_alert

from .models import ChatMessage, ExtractionJob, SpendAlert

logger = logging.getLogger(__name__)

MTOK = Decimal(1_000_000)

DEFAULT_PRICES = {
    "claude-opus-5-5": {"input": "4", "output": "20", "cache_read": "0.20"},
    "claude-sonnet-5-5": {"input": "2", "output": "10", "cache_read": "0.10"},
    # Haiku 5.5: preço maior quando o prompt passa de 100 mil tokens
    "claude-haiku-5-5": {"input": "0.10", "output": "0.50", "cache_read": "0.01",
                         "above": {"tokens": 100_000, "input": "0.50", "output": "2.50", "cache_read": "0.05"}},
    # Modelos que podem responder no lugar do principal (fallback de recusa)
    "claude-opus-5": {"input": "5", "output": "25", "cache_read": "0.50"},
    "claude-opus-4-8": {"input": "5", "output": "25", "cache_read": "0.50"},
    "claude-sonnet-5": {"input": "2", "output": "10", "cache_read": "0.20"},
}

LEVELS = (("80", Decimal("0.8")), ("100", Decimal("1")))


def prices():
    table = dict(DEFAULT_PRICES)
    extra = getattr(settings, "AI_PRICES_JSON", "")
    if extra:
        try:
            table.update(json.loads(extra))
        except ValueError:
            logger.error("AI_PRICES_JSON inválido; usando só a tabela padrão.")
    return table


def _price_for(model):
    table = prices()
    if model in table:
        return table[model]
    # ids com sufixo de data/versão: usa o prefixo mais longo que casar
    matches = [name for name in table if model.startswith(name)]
    return table[max(matches, key=len)] if matches else None


def call_cost(model, usage, batch=False):
    """Custo em US$ de uma chamada, ou None se o modelo não tem preço na tabela."""
    price = _price_for(model or "")
    if price is None or not usage:
        return None if price is None else Decimal("0")
    if "prompt_tokens" in usage:  # formato da OpenAI: o total de entrada inclui o que veio do cache
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        fresh, output = (usage.get("prompt_tokens") or 0) - cached, usage.get("completion_tokens") or 0
        write_5m = write_1h = 0
    else:
        fresh, output = usage.get("input_tokens") or 0, usage.get("output_tokens") or 0
        cached = usage.get("cache_read_input_tokens") or 0
        detail = usage.get("cache_creation") or {}
        write_1h = detail.get("ephemeral_1h_input_tokens") or 0
        write_5m = detail.get("ephemeral_5m_input_tokens")
        if write_5m is None:
            write_5m = (usage.get("cache_creation_input_tokens") or 0) - write_1h
    above = price.get("above")
    if above and fresh + cached + write_5m + write_1h > above["tokens"]:
        price = {**price, **above}
    p_in, p_out = Decimal(str(price["input"])), Decimal(str(price["output"]))
    p_read = Decimal(str(price.get("cache_read", price["input"])))
    cost = (fresh * p_in + write_5m * p_in * Decimal("1.25") + write_1h * p_in * 2
            + cached * p_read + output * p_out) / MTOK
    return cost / 2 if batch else cost


def month_spend(today=None):
    """Gasto do mês de `today`: total, conversa x documentos e por modelo."""
    today = today or date.today()
    start = datetime(today.year, today.month, 1)
    end = datetime(today.year + (today.month == 12), today.month % 12 + 1, 1)
    spend = {"month": start.date(), "total": Decimal("0"), "chat": Decimal("0"), "documents": Decimal("0"),
             "calls": 0, "unpriced_calls": 0, "by_model": {},
             "budget": settings.AI_MONTHLY_BUDGET_USD, "limit": settings.AI_MONTHLY_LIMIT_USD}

    def add(kind, model, usage, batch=False):
        if not usage:
            return
        spend["calls"] += 1
        cost = call_cost(model, usage, batch)
        if cost is None:
            spend["unpriced_calls"] += 1
            return
        spend[kind] += cost
        spend["total"] += cost
        spend["by_model"][model] = spend["by_model"].get(model, Decimal("0")) + cost

    messages = ChatMessage.objects.filter(role=ChatMessage.Role.ASSISTANT, created_at__gte=start, created_at__lt=end)
    for model, usage in messages.values_list("model", "usage"):
        add("chat", model, usage)
    jobs = ExtractionJob.objects.filter(created_at__gte=start, created_at__lt=end)
    for model, usage, mode in jobs.values_list("model", "usage", "mode"):
        add("documents", model, usage, batch=mode == ExtractionJob.Mode.BATCH)
    return spend


def over_limit(today=None):
    """O teto do mês foi atingido? (o bot deixa de chamar a IA)"""
    limit = settings.AI_MONTHLY_LIMIT_USD
    return bool(limit) and month_spend(today)["total"] >= limit


def usd(value):
    return f"US$ {value:.2f}"


def describe(spend):
    lines = [f"Gasto com IA em {spend['month']:%m/%Y}: {usd(spend['total'])} em {spend['calls']} chamada(s)",
             f"• Conversa: {usd(spend['chat'])}", f"• Leitura de documentos: {usd(spend['documents'])}"]
    for model, cost in sorted(spend["by_model"].items(), key=lambda kv: -kv[1]):
        lines.append(f"• {model}: {usd(cost)}")
    if spend["unpriced_calls"]:
        lines.append(f"• {spend['unpriced_calls']} chamada(s) de modelo sem preço cadastrado (fora do total)")
    if spend["budget"]:
        lines.append(f"Orçamento do mês: {usd(spend['budget'])} ({spend['total'] / spend['budget'] * 100:.0f}% usado)")
    if spend["limit"]:
        lines.append(f"Teto (o bot para de usar IA): {usd(spend['limit'])}")
    return "\n".join(lines)


def send_alerts(today=None):
    """Avisa por e-mail quando o gasto do mês cruza 80% e 100% do orçamento e
    quando bate no teto. Cada nível é avisado uma vez por mês. Devolve os níveis
    avisados agora."""
    spend = month_spend(today)
    reached = [(level, f"{int(share * 100)}% do orçamento de {usd(spend['budget'])}")
               for level, share in LEVELS if spend["budget"] and spend["total"] >= spend["budget"] * share]
    if spend["limit"] and spend["total"] >= spend["limit"]:
        reached.append(("limit", f"o teto de {usd(spend['limit'])}: o bot parou de usar IA até o mês virar"))
    new = []
    for level, label in reached:
        _alert, created = SpendAlert.objects.get_or_create(
            month=spend["month"], level=level, defaults={"amount": spend["total"]})
        if created:  # senão, já avisado neste mês
            new.append((level, label))
    if new:
        level, label = new[-1]  # só o nível mais alto cruzado agora
        body = (f"O gasto com IA do Confin chegou a {label}.\n\n{describe(spend)}\n\n"
                "Para mudar os valores: AI_MONTHLY_BUDGET_USD e AI_MONTHLY_LIMIT_USD no .env do servidor "
                "(e reinicie confin-worker). No Telegram, /custo mostra o gasto do mês.")
        send_alert(f"Gasto com IA: {label.split(':')[0]}", body)
    return [level for level, _ in new]
