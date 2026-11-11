"""Extração de documentos em chamada única, sem ferramentas.

Faturas e extratos não precisam do agente interativo: um modelo mais barato lê o
documento junto com os cadastros e devolve o lote inteiro em JSON. O servidor
valida, monta o lote com as mesmas regras do agente (duplicados, conferência
com o total da fatura / saldo do extrato) e só então apresenta ao usuário.

Dois modos (settings.ASSISTANT_DOCUMENT_MODE):
- "batch": pela API de batches da Anthropic (metade do preço, resposta em
  minutos; o worker consulta e avisa quando termina).
- "direct": a mesma chamada, na hora.

Se a extração falhar ou as conferências não fecharem (soma da fatura, saldo do
extrato, conferência linha a linha), o servidor tenta de novo na hora com o
mesmo modelo, depois com o modelo de reserva, e por fim devolve o documento ao
agente interativo (`needs_agent=True`), que relê com o modelo principal.
"""

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace

import anthropic
from django.conf import settings
from django.utils import timezone
from pydantic import Field, ValidationError

from . import agent, batch_service
from .models import ExtractionJob, ImportBatch
from .prompts import EXTRACTION_PROMPT
from .providers import get_provider
from .tools import ToolContext
from .tools.reference import GetReferenceDataInput, get_reference_data
from .tools.registry import ToolError, ToolInput, to_json
from .tools.staging import BatchMeta, EntryIn, StageEntriesInput, present_batch, stage_entries
from .tools.staging import BatchIdInput

logger = logging.getLogger(__name__)

MAX_TOKENS = 64000
BATCH_EXPIRY = timedelta(hours=25)


class ExtractedEntry(EntryIn):
    source_text: str | None = Field(
        default=None,
        description=("A linha do documento que originou este item, copiada literalmente (data, texto, "
                     "parcela, valor e sinal), para conferência automática."),
    )


class ExtractionOutput(ToolInput):
    batch: BatchMeta
    entries: list[ExtractedEntry] = Field(default_factory=list)
    summary: str = ""
    questions: list[str] = Field(default_factory=list)


@dataclass
class ExtractionResult:
    job: ExtractionJob
    text: str = ""
    batches_to_present: list = field(default_factory=list)
    needs_agent: bool = False  # extração não serviu: reler com o agente interativo
    reason: str = ""


class ExtractionFailed(Exception):
    pass


_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None, max_retries=3, timeout=600.0)
    return _client


def available():
    """Extração em chamada única só existe para o provedor Anthropic."""
    return (settings.AI_PROVIDER or "anthropic").lower() == "anthropic" and \
        settings.ASSISTANT_DOCUMENT_MODE in ("batch", "direct")


def handles(attachment):
    return attachment.kind in ("pdf", "text")


def system_prompt():
    schema = json.dumps(ExtractionOutput.model_json_schema(), ensure_ascii=False, sort_keys=True)
    return EXTRACTION_PROMPT + schema + "\n"


def build_params(attachment, caption, model=None, effort=None, chat_id=None):
    """Parâmetros da chamada (iguais nos modos direct e batch)."""
    reference = get_reference_data(GetReferenceDataInput(), SimpleNamespace(chat_id=chat_id))
    reference.pop("entities", None)  # nomes de estabelecimentos vão em entity_name
    now = timezone.localtime() if settings.USE_TZ else timezone.now()

    path = Path(attachment.storage_path)
    if attachment.kind == "pdf":
        document = {"type": "document", "title": attachment.filename[:200],
                    "source": {"type": "base64", "media_type": "application/pdf",
                               "data": base64.standard_b64encode(path.read_bytes()).decode()}}
    else:
        document = {"type": "text", "text": f"[Arquivo {attachment.filename}]\n{path.read_text(encoding='utf-8')}"}

    text = f"Data de hoje: {now:%Y-%m-%d}.\n\nCadastros do usuário:\n{to_json(reference)}"
    if caption:
        text += f"\n\nObservação do usuário sobre o documento: {caption}"
    params = {
        "model": model or settings.ANTHROPIC_EXTRACTION_MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt(),
        "messages": [{"role": "user", "content": [document, {"type": "text", "text": text}]}],
    }
    effort = effort or settings.ANTHROPIC_EXTRACTION_EFFORT
    if effort:
        params["output_config"] = {"effort": effort}
    return params


def parse_output(message):
    """Mensagem do modelo -> ExtractionOutput validado."""
    if message.stop_reason in ("refusal", "max_tokens"):
        raise ExtractionFailed(f"o modelo parou antes de terminar ({_diagnose(message)})")
    text = "".join(b.text for b in message.content if b.type == "text").strip()
    raw = text
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ExtractionFailed(f"a resposta não trouxe um objeto JSON ({_diagnose(message, raw)})")
    try:
        return ExtractionOutput.model_validate(json.loads(text[start:end + 1]))
    except (ValueError, ValidationError) as exc:
        raise ExtractionFailed(f"JSON fora do formato: {str(exc)[:300]} ({_diagnose(message, raw)})") from exc


def _diagnose(message, text=""):
    """O que dá para saber de uma resposta que não serviu. Fica em ExtractionJob.error,
    para a causa não se perder (uma resposta vazia e uma cortada pedem correções diferentes)."""
    usage = message.usage
    parts = [f"stop_reason={message.stop_reason}",
             f"blocos={[b.type for b in message.content]}",
             f"tokens_saida={getattr(usage, 'output_tokens', '?')}"]
    details = getattr(message, "stop_details", None)
    if details is not None:
        parts.append(f"detalhe={getattr(details, 'category', None) or getattr(details, 'type', '')}")
    if text:
        parts.append(f"inicio={text[:120]!r}")
        if len(text) > 240:
            parts.append(f"fim={text[-120:]!r}")
    return "; ".join(parts)


_LEADING_DATE = re.compile(r"^\s*\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?\s*")
_FULL_DATE = re.compile(r"(?<!\d)\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(?!\d)")  # data em qualquer ponto: não é parcela
_INSTALLMENT = re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)")
_MONEY = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")


def evidence_problems(entries, limit=5):
    """Confere cada item com a linha do documento que o modelo copiou em
    `source_text`. Pega os erros que a soma não acusa (parcela lançada como compra
    à vista) e os que ela acusa sem dizer onde (sinal ou valor trocado)."""
    problems = []
    for position, entry in enumerate(entries, 1):
        src = (entry.source_text or "").strip()
        if not src:
            continue
        body = _FULL_DATE.sub(" ", _LEADING_DATE.sub("", src))
        installments = [(int(k), int(n)) for k, n in _INSTALLMENT.findall(body)
                        if 1 <= int(k) <= int(n) and int(n) >= 2]
        if installments and entry.kind == "EXPENSE":
            problems.append(f"item {position}: a linha traz parcela {installments[0][0]}/{installments[0][1]} "
                            "mas foi lançada como compra à vista")
        elif installments and entry.kind == "INSTALLMENT_CHARGE" and \
                (entry.installment_number, entry.installments_total) not in installments:
            problems.append(f"item {position}: parcela {entry.installment_number}/{entry.installments_total} "
                            f"não confere com a linha ({installments[0][0]}/{installments[0][1]})")
        if src.endswith("-") and entry.kind in ("EXPENSE", "INSTALLMENT_CHARGE"):
            problems.append(f"item {position}: a linha tem sinal de crédito mas foi lançada como compra")
        values = set()
        for text in _MONEY.findall(src):
            try:
                values.add(Decimal(text.replace(".", "").replace(",", ".")))
            except InvalidOperation:
                pass
        try:
            amount = Decimal(str(entry.amount).replace(",", "."))
        except InvalidOperation:
            amount = None
        if values and amount is not None and amount not in values:
            problems.append(f"item {position}: valor {entry.amount} não aparece na linha")
        if len(problems) >= limit:
            break
    return problems


def _reconciliation_problem(batch):
    totals = batch_service.batch_totals(batch)
    for key, label in (("invoice_difference", "a soma dos itens não bate com o total da fatura"),
                       ("statement_difference", "as linhas não fecham com o saldo do extrato")):
        if key in totals and abs(totals[key]) >= batch_service.Decimal("0.01"):
            return f"{label} (diferença de R$ {totals[key]})"
    return ""


def apply_output(job, output):
    """Monta o lote a partir da extração. Devolve ExtractionResult."""
    provider = get_provider()
    conversation = agent.get_conversation(job.chat_id, provider)
    attachment = job.attachment
    if attachment.conversation_id != conversation.pk:
        attachment.conversation = conversation
        attachment.save(update_fields=["conversation"])
    ctx = ToolContext(conversation=conversation, chat_id=job.chat_id)

    if not output.entries and output.batch.balance_amount is None and not output.batch.other_balances:
        return ExtractionResult(job, text=output.summary or "Não encontrei lançamentos neste arquivo.")

    problems = evidence_problems(output.entries)
    if problems:
        raise ExtractionFailed("conferência linha a linha: " + "; ".join(problems))

    entries = [EntryIn(**e.model_dump(exclude={"source_text"})) for e in output.entries]
    try:
        view = stage_entries(StageEntriesInput(batch=output.batch, entries=entries), ctx)
    except (ToolError, ValidationError) as exc:
        raise ExtractionFailed(f"lote recusado: {str(exc)[:300]}") from exc
    batch = ImportBatch.objects.select_related("payment_method", "balance_account").get(pk=view["batch_id"])

    problem = _reconciliation_problem(batch)
    if problem:
        batch_service.discard(batch.pk)
        raise ExtractionFailed(problem)

    present_batch(BatchIdInput(batch_id=batch.pk), ctx)
    job.import_batch = batch

    lines = [output.summary.strip()] if output.summary.strip() else []
    if output.questions:
        lines.append("Preciso que você me diga:")
        lines.extend(f"{i}. {q}" for i, q in enumerate(output.questions, 1))
    text = "\n".join(lines)

    note = (f"O usuário enviou o arquivo {attachment.filename}. Ele foi lido em segundo plano pelo extrator e virou "
            f"o lote #{batch.pk} ({batch.entries.count()} itens), já apresentado ao usuário com os botões. "
            f"O documento não está nesta conversa: use get_batch para ver os itens.")
    if text:
        note += f"\nO que o extrator disse ao usuário:\n{text}"
    agent.add_note(job.chat_id, note)
    return ExtractionResult(job, text=text, batches_to_present=ctx.batches_to_present)


def _next_attempt(job):
    """Depois de uma extração que não serviu: tenta de novo com o mesmo modelo (os
    erros são em boa parte aleatórios) e, se ainda falhar, com o modelo de reserva.
    Devolve o modelo da próxima tentativa, ou None se só resta o agente."""
    previous = ExtractionJob.objects.filter(attachment=job.attachment, chat_id=job.chat_id).count()
    fallback = settings.ANTHROPIC_EXTRACTION_FALLBACK_MODEL
    if previous == 1:
        return job.model
    if previous == 2 and fallback and fallback != job.model:
        return fallback
    return None


def _finish(job, message=None, error=""):
    """Fecha o job com a resposta do modelo (ou um erro) e devolve o resultado."""
    result = None
    if message is not None:
        job.usage = message.usage.to_dict(mode="json") if message.usage else {}
        try:
            result = apply_output(job, parse_output(message))
        except ExtractionFailed as exc:
            error = str(exc)
        except Exception as exc:  # resposta inesperada não pode derrubar o worker: segue a escada
            logger.exception("Erro inesperado ao montar o lote da extração #%s", job.pk)
            error = f"erro inesperado: {exc}"[:500]
    job.finished_at = timezone.now()
    if result is None:
        logger.warning("Extração #%s não serviu: %s", job.pk, error)
        job.status = ExtractionJob.Status.FALLBACK
        job.error = error[:2000]
        job.save()
        retry_model = _next_attempt(job)
        if retry_model:
            return run_direct(job.chat_id, job.attachment, job.caption, model=retry_model)
        return ExtractionResult(job, needs_agent=True, reason=error)
    job.status = ExtractionJob.Status.DONE
    job.save()
    return result


def run_direct(chat_id, attachment, caption="", model=None):
    """Extrai agora (sem o desconto de batch)."""
    params = build_params(attachment, caption, model=model, chat_id=chat_id)
    job = ExtractionJob.objects.create(chat_id=chat_id, attachment=attachment, caption=caption,
                                       mode=ExtractionJob.Mode.DIRECT, model=params["model"])
    try:
        with get_client().messages.stream(**params) as stream:
            message = stream.get_final_message()
    except (anthropic.APIError, ValueError) as exc:
        return _finish(job, error=f"erro da API: {exc}")
    return _finish(job, message)


def submit_batch(chat_id, attachment, caption=""):
    """Envia para a API de batches. O resultado sai em `poll()`."""
    params = build_params(attachment, caption, chat_id=chat_id)
    job = ExtractionJob.objects.create(chat_id=chat_id, attachment=attachment, caption=caption,
                                       mode=ExtractionJob.Mode.BATCH, model=params["model"])
    try:
        created = get_client().messages.batches.create(
            requests=[{"custom_id": f"job-{job.pk}", "params": params}])
    except anthropic.APIError as exc:
        job.status = ExtractionJob.Status.FAILED
        job.error = str(exc)[:2000]
        job.finished_at = timezone.now()
        job.save()
        raise ExtractionFailed(f"não consegui enviar para processamento em segundo plano: {exc}") from exc
    job.provider_batch_id = created.id
    job.save(update_fields=["provider_batch_id"])
    return job


def pending_jobs():
    return ExtractionJob.objects.filter(status=ExtractionJob.Status.SUBMITTED, mode=ExtractionJob.Mode.BATCH)


def poll():
    """Consulta os batches pendentes e devolve os resultados dos que terminaram."""
    results = []
    client = get_client()
    for job in pending_jobs().select_related("attachment"):
        try:
            batch = client.messages.batches.retrieve(job.provider_batch_id)
        except anthropic.APIError:
            logger.exception("Falha ao consultar batch %s", job.provider_batch_id)
            continue
        if batch.processing_status != "ended":
            if timezone.now() - job.created_at > BATCH_EXPIRY:
                results.append(_finish(job, error="o processamento em segundo plano passou de 24 horas"))
            continue
        message, error = None, "o batch terminou sem resultado"
        try:
            for item in client.messages.batches.results(job.provider_batch_id):
                if item.result.type == "succeeded":
                    message = item.result.message
                else:
                    error = f"o batch terminou com status {item.result.type}"
        except anthropic.APIError as exc:
            logger.exception("Falha ao ler resultado do batch %s", job.provider_batch_id)
            error = f"erro ao ler o resultado: {exc}"
        results.append(_finish(job, message, error))
    return results
