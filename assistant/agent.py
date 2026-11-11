"""Loop do agente: uma mensagem do usuário -> chamadas ao modelo e às
ferramentas -> resposta final. Independe do canal (Telegram/web)."""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import FamilyMember

from .models import ChatMessage, Conversation
from .prompts import SYSTEM_PROMPT
from .providers import Part, ProviderError, get_provider
from .tools import TOOLS, ToolContext, ToolResult, execute

logger = logging.getLogger(__name__)

WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
            "sexta-feira", "sábado", "domingo"]

REFUSAL_TEXT = ("Não consegui processar este pedido. Se for um documento financeiro, "
                "tente reenviar ou descrever o lançamento por texto.")


@dataclass
class TurnResult:
    text: str
    conversation: Conversation
    batches_to_present: list = field(default_factory=list)
    error: bool = False


def get_conversation(chat_id, provider, channel="telegram", force_new=False):
    """Conversa aberta compatível, ou uma nova (inatividade, /novo, troca de
    provedor/modelo/prompt, ou histórico interrompido)."""
    now = timezone.now()
    fingerprint = provider.fingerprint(SYSTEM_PROMPT, TOOLS)
    conv = Conversation.objects.filter(
        chat_id=chat_id, channel=channel, closed_at__isnull=True
    ).order_by("-last_activity_at").first()

    if conv and not force_new:
        last = conv.messages.order_by("-id").first()
        compatible = (
            conv.provider == provider.name
            and conv.model == provider.model
            and conv.prompt_hash == fingerprint
            and conv.last_activity_at >= now - timedelta(hours=settings.ASSISTANT_IDLE_HOURS)
            and not (last and last.role == ChatMessage.Role.NOTE)  # turno interrompido
        )
        if compatible:
            return conv

    notes, awaiting, awaiting_data = [], "", {}
    if conv:
        notes = conv.pending_notes
        if not force_new:
            awaiting, awaiting_data = conv.awaiting, conv.awaiting_data
        conv.closed_at = now
        conv.save(update_fields=["closed_at"])

    return Conversation.objects.create(
        chat_id=chat_id, channel=channel, provider=provider.name, model=provider.model,
        prompt_hash=fingerprint, last_activity_at=now, pending_notes=notes,
        awaiting=awaiting, awaiting_data=awaiting_data,
    )


def open_conversation(chat_id, channel="telegram"):
    """Conversa aberta atual (sem criar), para estados como senha de PDF."""
    return Conversation.objects.filter(
        chat_id=chat_id, channel=channel, closed_at__isnull=True
    ).order_by("-last_activity_at").first()


def close_conversation(chat_id, channel="telegram"):
    Conversation.objects.filter(chat_id=chat_id, channel=channel, closed_at__isnull=True).update(
        closed_at=timezone.now()
    )


def add_note(chat_id, text, channel="telegram"):
    """Aviso para o modelo na próxima mensagem (ex.: lote confirmado pelo botão)."""
    conv = open_conversation(chat_id, channel)
    if conv:
        conv.pending_notes = [*conv.pending_notes, text]
        conv.save(update_fields=["pending_notes"])


def _extend(history, native):
    """Uma ChatMessage pode guardar várias mensagens nativas (ex.: resultados de
    ferramenta na OpenAI, um por chamada)."""
    if isinstance(native, list):
        history.extend(native)
    else:
        history.append(native)


def _time_note(chat_id=None):
    now = timezone.localtime() if settings.USE_TZ else timezone.now()
    note = f"Agora: {now:%d/%m/%Y %H:%M} ({WEEKDAYS[now.weekday()]})."
    speaker = FamilyMember.objects.filter(telegram_chat_id=chat_id, active=True).first() if chat_id else None
    if speaker:
        note += f" Quem está falando: {speaker.name}."
    elif FamilyMember.objects.filter(active=True).exists():
        note += " Quem está falando: pessoa ainda não identificada."
    return note


def run_turn(chat_id, parts: list[Part], channel="telegram", provider=None) -> TurnResult:
    provider = provider or get_provider()
    conv = get_conversation(chat_id, provider, channel)
    ctx = ToolContext(conversation=conv, chat_id=chat_id)

    for part in parts:
        att = part.attachment
        if att is not None and att.conversation_id != conv.pk:
            att.conversation = conv
            att.save(update_fields=["conversation"])

    try:
        user_native = provider.user_message(parts)
    except ProviderError as exc:
        return TurnResult(f"⚠️ {exc}", conv, error=True)

    notes = [_time_note(chat_id), *conv.pending_notes]
    saved_notes = list(conv.pending_notes)
    with transaction.atomic():
        user_msg = ChatMessage.objects.create(
            conversation=conv, role=ChatMessage.Role.USER, native_content=user_native,
            text_preview=" ".join(p.text for p in parts if p.text)[:2000]
            or ", ".join(p.attachment.filename for p in parts if p.attachment),
        )
        note_msg = ChatMessage.objects.create(
            conversation=conv, role=ChatMessage.Role.NOTE,
            native_content=provider.note_message("\n".join(notes)), text_preview="\n".join(notes)[:2000],
        )
        conv.pending_notes = []
        conv.last_activity_at = timezone.now()
        conv.save(update_fields=["pending_notes", "last_activity_at"])

    history = []
    for native in conv.messages.order_by("id").values_list("native_content", flat=True):
        _extend(history, native)
    assistant_saved = False
    final_text = ""

    try:
        for _ in range(settings.ASSISTANT_MAX_STEPS):
            result = provider.run_step(SYSTEM_PROMPT, history, TOOLS)
            ChatMessage.objects.create(
                conversation=conv, role=ChatMessage.Role.ASSISTANT, native_content=result.native_message,
                text_preview=result.text[:2000], model=result.model, stop_reason=result.stop_reason,
                usage=result.usage,
            )
            assistant_saved = True
            history.append(result.native_message)

            if result.stop_reason in ("refusal", "max_tokens"):
                if result.tool_calls:
                    # Chamada cortada: não executar, mas fechar o par tool_use/tool_result
                    reason = "recusa" if result.stop_reason == "refusal" else "resposta cortada"
                    closing = provider.tool_results([
                        ToolResult(c.id, f"Não executado ({reason}).", is_error=True) for c in result.tool_calls
                    ])
                    ChatMessage.objects.create(conversation=conv, role=ChatMessage.Role.TOOL,
                                               native_content=closing, text_preview="(não executado)")
                    _extend(history, closing)
                if result.stop_reason == "refusal":
                    final_text = REFUSAL_TEXT
                else:
                    final_text = result.text or ("A resposta ficou longa demais. Tente dividir o pedido "
                                                 "(por exemplo, uma página da fatura por vez).")
                break

            if result.stop_reason == "pause_turn":
                continue

            if not result.tool_calls:
                final_text = result.text
                break

            results = [execute(call, ctx) for call in result.tool_calls]
            tool_native = provider.tool_results(results)
            ChatMessage.objects.create(
                conversation=conv, role=ChatMessage.Role.TOOL, native_content=tool_native,
                text_preview=", ".join(c.name for c in result.tool_calls),
            )
            _extend(history, tool_native)
        else:
            final_text = ("Parei aqui para não demorar demais. Me diga se devo continuar.")
    except Exception as exc:
        if not assistant_saved:
            # Nada foi respondido: desfaz o turno para não deixar o histórico inválido
            user_msg.delete()
            note_msg.delete()
            conv.refresh_from_db(fields=["pending_notes"])
            conv.pending_notes = saved_notes + conv.pending_notes
            conv.save(update_fields=["pending_notes"])
        if isinstance(exc, ProviderError):
            logger.warning("Erro do provedor: %s", exc)
            return TurnResult(f"⚠️ {exc}", conv, batches_to_present=ctx.batches_to_present, error=True)
        raise

    conv.last_activity_at = timezone.now()
    conv.save(update_fields=["last_activity_at"])
    return TurnResult(final_text, conv, batches_to_present=ctx.batches_to_present)
