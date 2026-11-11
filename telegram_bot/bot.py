"""Fluxo do bot com o assistente de IA.

- `ingest_update`: chamado pelo webhook (e pelo modo --poll). Grava o update na
  fila; botões de lote são tratados na hora (só banco de dados, rápido).
- `process_chat_updates`: chamado pelo worker com as mensagens agrupadas de um
  chat; monta as partes (texto, fotos, arquivos) e roda o agente.
"""

import logging
import threading
from contextlib import contextmanager
from html import escape
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from assistant import agent, batch_service, documents, extraction
from assistant.models import Attachment, ImportBatch
from assistant.providers import Part, ProviderNotAvailable, get_provider

from . import client, render
from .models import TelegramUpdate

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "👋 Olá! Sou seu assistente financeiro.\n\n"
    "Você pode me mandar:\n"
    "• Foto de comprovante (PIX, cartão, boleto)\n"
    "• Fatura do cartão ou extrato em PDF, CSV ou OFX\n"
    "• Texto: \"almoço 45 reais no pix\", \"TV 2400 em 12x no Nubank\"\n"
    "• Perguntas: \"quanto vou pagar de fatura em dezembro?\", \"quanto gastei com mercado este mês?\"\n\n"
    "Eu monto um lote com os lançamentos e você confirma com um toque. Nada é gravado sem sua confirmação.\n\n"
    "Comandos: /novo (nova conversa), /desfazer (desfaz o último lote confirmado), /cancelar"
)


def _chat_id_of(update):
    if "callback_query" in update:
        return update["callback_query"].get("message", {}).get("chat", {}).get("id")
    for key in ("message", "edited_message"):
        if key in update:
            return update[key].get("chat", {}).get("id")
    return None


def ingest_update(update):
    """Grava o update (deduplicado por update_id) e trata callbacks na hora."""
    update_id = update.get("update_id")
    if update_id is None:
        return
    record, created = TelegramUpdate.objects.get_or_create(
        update_id=update_id, defaults={"payload": update, "chat_id": _chat_id_of(update)}
    )
    if not created:
        return
    if "callback_query" in update:
        try:
            handle_callback(update["callback_query"])
            record.status = TelegramUpdate.Status.DONE
        except Exception as exc:
            logger.exception("Erro ao tratar callback")
            record.status = TelegramUpdate.Status.FAILED
            record.error = repr(exc)
        record.processed_at = timezone.now()
        record.save(update_fields=["status", "error", "processed_at"])
    elif "message" not in update:
        record.status = TelegramUpdate.Status.DONE
        record.processed_at = timezone.now()
        record.save(update_fields=["status", "processed_at"])


# ---------------------------------------------------------------------------
# Botões
# ---------------------------------------------------------------------------

def handle_callback(cq):
    cb_id = cq["id"]
    message = cq.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    data = cq.get("data", "")

    if not client.is_allowed(chat_id):
        client.answer_callback(cb_id, "Não autorizado")
        return

    if not data.startswith("b:"):
        # Botões do fluxo antigo (PendingTransaction)
        from .handlers import handle_callback as legacy_handle_callback

        legacy_handle_callback(cq)
        return

    try:
        parts = data.split(":")
        action, batch_id = parts[1], int(parts[2])
        version = int(parts[3]) if len(parts) > 3 else None
    except (IndexError, ValueError):
        client.answer_callback(cb_id, "Botão inválido")
        return

    batch = ImportBatch.objects.filter(pk=batch_id, chat_id=chat_id).select_related(
        "payment_method", "balance_account").first()
    if batch is None:
        client.answer_callback(cb_id, "Lote não encontrado")
        return

    if action == "v":
        client.answer_callback(cb_id)
        client.send_message(chat_id, render.batch_items(batch))
        return

    if action == "c":
        result = batch_service.commit(batch_id, version)
        if result.ok:
            client.edit_message(
                chat_id, message_id,
                f"✅ <b>Lote #{batch_id} confirmado</b>\n{escape(result.message)}\nPara desfazer: /desfazer",
                html=True,
            )
            client.answer_callback(cb_id, "Gravado!")
            agent.add_note(chat_id, f"O usuário confirmou o lote #{batch_id}: {result.message}")
        else:
            client.answer_callback(cb_id, result.message[:190])
        return

    if action == "d":
        if batch_service.discard(batch_id, version):
            client.edit_message(chat_id, message_id, f"❌ Lote #{batch_id} descartado.")
            client.answer_callback(cb_id)
            agent.add_note(chat_id, f"O usuário descartou o lote #{batch_id}.")
        else:
            client.answer_callback(cb_id, "Lote já processado ou alterado depois deste resumo.")
        return

    client.answer_callback(cb_id, "Ação desconhecida")


# ---------------------------------------------------------------------------
# Mensagens
# ---------------------------------------------------------------------------

@contextmanager
def typing(chat_id):
    """Mantém o 'digitando…' enquanto o agente trabalha."""
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            client.send_chat_action(chat_id)
            stop.wait(4.5)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()


def _handle_command(chat_id, text):
    command = text.split()[0].split("@")[0].lower()
    if command == "/start" or command == "/ajuda":
        client.send_message(chat_id, HELP_TEXT)
    elif command == "/novo":
        agent.close_conversation(chat_id)
        client.send_message(chat_id, "🆕 Nova conversa iniciada.")
    elif command == "/cancelar":
        conv = agent.open_conversation(chat_id)
        if conv and conv.awaiting:
            conv.awaiting, conv.awaiting_data = "", {}
            conv.save(update_fields=["awaiting", "awaiting_data"])
        client.send_message(chat_id, "Ok, cancelado.")
    elif command == "/desfazer":
        last = ImportBatch.objects.filter(chat_id=chat_id, status=ImportBatch.Status.CONFIRMED).order_by(
            "-committed_at").first()
        if last is None:
            client.send_message(chat_id, "Não há lote confirmado para desfazer.")
            return
        result = batch_service.undo(last.pk)
        client.send_message(chat_id, ("↩️ " if result.ok else "⚠️ ") + result.message)
        if result.ok:
            agent.add_note(chat_id, f"O usuário desfez o lote #{last.pk} (registros removidos).")
    else:
        client.send_message(chat_id, "Comando desconhecido. Use /ajuda.")


def _save_message_attachment(msg):
    """Baixa foto/documento da mensagem. Retorna SavedAttachment ou None."""
    if msg.get("photo"):
        file_id, filename, mime, size = msg["photo"][-1]["file_id"], None, "image/jpeg", None
    elif msg.get("document"):
        doc = msg["document"]
        file_id, filename, mime, size = doc["file_id"], doc.get("file_name"), doc.get("mime_type"), doc.get("file_size")
    else:
        return None
    if size and size > client.MAX_DOWNLOAD_BYTES:
        raise documents.DocumentError("Arquivo maior que 20 MB (limite do Telegram para bots).")
    data, file_path = client.download_file(file_id)
    if data is None:
        raise documents.DocumentError("Não consegui baixar o arquivo. Tente enviar de novo.")
    filename = filename or Path(file_path or "foto.jpg").name
    return documents.save_attachment(None, data, filename, mime)


def _try_password(chat_id, msg, conv):
    """Mensagem de texto enquanto um PDF aguarda senha. Retorna partes ou []."""
    client.delete_message(chat_id, msg["message_id"])  # não deixar a senha no chat
    att = Attachment.objects.filter(pk=conv.awaiting_data.get("attachment_id")).first()
    if att is None:
        conv.awaiting, conv.awaiting_data = "", {}
        conv.save(update_fields=["awaiting", "awaiting_data"])
        return []
    if not documents.unlock_pdf(att, msg.get("text", "").strip()):
        client.send_message(chat_id, "🔒 Senha incorreta. Envie de novo ou use /cancelar.")
        return []
    caption = conv.awaiting_data.get("caption", "")
    conv.awaiting, conv.awaiting_data = "", {}
    conv.save(update_fields=["awaiting", "awaiting_data"])
    client.send_message(chat_id, "🔓 PDF aberto. Analisando…")
    parts = [Part("attachment", attachment=att)]
    if caption:
        parts.append(Part("text", text=caption))
    return parts


def process_chat_updates(chat_id, payloads):
    """Processa as mensagens agrupadas de um chat (álbum, arquivo + texto, etc.)."""
    if not client.is_allowed(chat_id):
        return
    messages = [p["message"] for p in payloads if "message" in p]
    if not messages:
        return

    try:
        provider = get_provider()
    except ProviderNotAvailable as exc:
        logger.error("AI_PROVIDER inválido: %s", exc)
        client.send_message(chat_id, "⚠️ Assistente mal configurado no servidor (AI_PROVIDER).")
        return

    parts, locked_pdf, texts = [], None, []
    for msg in messages:
        text = (msg.get("text") or msg.get("caption") or "").strip()

        if msg.get("text", "").startswith("/"):
            _handle_command(chat_id, msg["text"])
            continue

        conv = agent.open_conversation(chat_id)
        if conv and conv.awaiting == "pdf_password" and msg.get("text"):
            parts.extend(_try_password(chat_id, msg, conv))
            continue

        try:
            saved = _save_message_attachment(msg)
        except documents.DocumentError as exc:
            client.send_message(chat_id, f"⚠️ {exc}")
            continue

        if saved and saved.needs_password:
            locked_pdf = saved.attachment
        elif saved:
            parts.append(Part("attachment", attachment=saved.attachment))
        elif not text:
            client.send_message(chat_id, "Por enquanto entendo texto, fotos e arquivos (PDF, CSV, OFX).")
            continue
        if text:
            texts.append(text)

    if locked_pdf is not None:
        conv = agent.get_conversation(chat_id, provider)
        locked_pdf.conversation = conv
        locked_pdf.save(update_fields=["conversation"])
        conv.awaiting = "pdf_password"
        conv.awaiting_data = {"attachment_id": locked_pdf.pk, "caption": "\n".join(texts)}
        conv.save(update_fields=["awaiting", "awaiting_data"])
        client.send_message(
            chat_id,
            f"🔒 O arquivo {locked_pdf.filename} tem senha. Envie a senha (apago a mensagem em seguida) "
            "ou use /cancelar.\nDica: configure PDF_PASSWORDS no servidor para abrir automaticamente.",
        )
        if not parts:
            return

    if locked_pdf is None:
        parts.extend(Part("text", text=t) for t in texts)
    if not parts:
        return

    # Documentos (PDF, CSV, OFX) vão para a extração em chamada única, mais barata
    documents_parts = [p for p in parts if p.kind == "attachment" and extraction.handles(p.attachment)]
    if documents_parts and extraction.available():
        caption = "\n".join(p.text for p in parts if p.kind == "text").strip()
        now = caption.lower().startswith("agora")
        if now:
            caption = caption[5:].lstrip(" :,.-")
        for part in documents_parts:
            _extract_document(chat_id, part.attachment, caption, now or settings.ASSISTANT_DOCUMENT_MODE == "direct")
        parts = [p for p in parts if p.kind == "attachment" and p not in documents_parts]
        if not parts:
            return  # o texto era a legenda dos documentos

    _run_agent(chat_id, parts, provider)


def _deliver(chat_id, text, batch_ids):
    """Envia a resposta e o resumo (com botões) de cada lote apresentado."""
    if text:
        client.send_message(chat_id, text)
    for batch_id in batch_ids:
        batch = ImportBatch.objects.select_related("payment_method", "balance_account").get(pk=batch_id)
        summary, keyboard = render.batch_summary(batch)
        sent = client.send_message(chat_id, summary, reply_markup=keyboard, html=True)
        message_id = sent.get("result", {}).get("message_id") if sent.get("ok") else None
        if message_id:
            batch.telegram_message_id = message_id
            batch.save(update_fields=["telegram_message_id"])


def _run_agent(chat_id, parts, provider=None):
    with typing(chat_id):
        result = agent.run_turn(chat_id, parts, provider=provider)
    _deliver(chat_id, result.text, result.batches_to_present)


def _extract_document(chat_id, attachment, caption, immediately):
    if not immediately:
        try:
            extraction.submit_batch(chat_id, attachment, caption)
        except extraction.ExtractionFailed as exc:
            logger.warning("Batch indisponível, lendo na hora: %s", exc)
        else:
            client.send_message(
                chat_id,
                f"📥 Recebi {attachment.filename}. Vou ler em segundo plano, que sai mais barato, e aviso aqui "
                "quando o lote estiver pronto (em geral alguns minutos). Para ler na hora, reenvie com a "
                "legenda \"agora\".",
            )
            return
    with typing(chat_id):
        result = extraction.run_direct(chat_id, attachment, caption)
    _handle_extraction_result(result)


def _handle_extraction_result(result):
    job = result.job
    if result.needs_agent:
        # As conferências não fecharam nem nas novas tentativas: relê com o agente completo
        client.send_message(
            job.chat_id,
            f"A leitura rápida de {job.attachment.filename} não fechou nas conferências. Vou reler com o "
            "modelo completo; pode levar alguns minutos.",
        )
        parts = [Part("attachment", attachment=job.attachment)]
        if job.caption:
            parts.append(Part("text", text=job.caption))
        _run_agent(job.chat_id, parts)
        return
    header = f"📄 Li {job.attachment.filename}."
    _deliver(job.chat_id, f"{header}\n{result.text}".strip(), result.batches_to_present)


def deliver_finished_extractions():
    """Chamado pelo worker: entrega os documentos cuja leitura em batch terminou."""
    for result in extraction.poll():
        try:
            _handle_extraction_result(result)
        except Exception:
            logger.exception("Erro ao entregar extração #%s", result.job.pk)
            client.send_message(result.job.chat_id, "⚠️ Tive um erro ao montar o lote do seu documento. Reenvie, por favor.")
