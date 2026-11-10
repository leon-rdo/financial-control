"""Chamadas à Bot API do Telegram (HTTP puro com `requests`)."""

import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 4096
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # limite de getFile da Bot API


def _api(method):
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def call(method, payload=None, timeout=15):
    """Chama um método da Bot API e devolve o JSON. Nunca lança exceção."""
    try:
        resp = requests.post(_api(method), json=payload or {}, timeout=timeout)
        data = resp.json()
    except (requests.RequestException, ValueError):
        logger.exception("Falha ao chamar Telegram %s", method)
        return {"ok": False}
    if not data.get("ok"):
        logger.warning("Telegram %s retornou erro: %s", method, data.get("description"))
    return data


def split_text(text, limit=MAX_MESSAGE_LEN):
    """Quebra texto em blocos <= limit, preferindo quebras de linha."""
    chunks = []
    text = text or ""
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks or [""]


def send_message(chat_id, text, reply_markup=None, html=False):
    """Envia mensagem. Texto do modelo vai sem parse_mode; HTML só para templates
    próprios (já escapados com html.escape). Retorna o resultado do último bloco."""
    result = {"ok": False}
    chunks = split_text(text)
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk}
        if html:
            payload["parse_mode"] = "HTML"
        if reply_markup and i == len(chunks) - 1:
            payload["reply_markup"] = json.dumps(reply_markup)
        result = call("sendMessage", payload)
        if not result.get("ok") and html:
            # Fallback: reenviar sem formatação
            payload.pop("parse_mode", None)
            result = call("sendMessage", payload)
    return result


def edit_message(chat_id, message_id, text, reply_markup=None, html=False):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:MAX_MESSAGE_LEN]}
    if html:
        payload["parse_mode"] = "HTML"
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return call("editMessageText", payload)


def answer_callback(callback_query_id, text=""):
    return call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text}, timeout=5)


def send_chat_action(chat_id, action="typing"):
    return call("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=5)


def delete_message(chat_id, message_id):
    return call("deleteMessage", {"chat_id": chat_id, "message_id": message_id}, timeout=5)


def download_file(file_id):
    """Baixa um arquivo (foto ou documento). Retorna (bytes, file_path) ou (None, None)."""
    data = call("getFile", {"file_id": file_id})
    if not data.get("ok"):
        return None, None
    info = data["result"]
    if info.get("file_size") and info["file_size"] > MAX_DOWNLOAD_BYTES:
        return None, None
    file_path = info["file_path"]
    try:
        resp = requests.get(
            f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}",
            timeout=60,
        )
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception("Falha ao baixar arquivo do Telegram")
        return None, None
    return resp.content, file_path


def get_updates(offset=None, timeout=30):
    """Long polling (modo --poll do worker). Falha com 409 se houver webhook ativo."""
    payload = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    if offset is not None:
        payload["offset"] = offset
    return call("getUpdates", payload, timeout=timeout + 10)


def is_allowed(chat_id):
    """Só aceita chats listados em TELEGRAM_ALLOWED_CHAT_IDS (vazio = ninguém)."""
    allowed = settings.TELEGRAM_ALLOWED_CHAT_IDS
    if not allowed or chat_id is None:
        return False
    try:
        allowed_ids = {int(x.strip()) for x in allowed.split(",") if x.strip()}
    except ValueError:
        logger.error("TELEGRAM_ALLOWED_CHAT_IDS inválido")
        return False
    return int(chat_id) in allowed_ids


def webhook_secret_token():
    """Valor do header X-Telegram-Bot-Api-Secret-Token (só aceita [A-Za-z0-9_-])."""
    import hashlib
    import re

    secret = settings.TELEGRAM_WEBHOOK_SECRET or ""
    if re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secret):
        return secret
    return hashlib.sha256(secret.encode()).hexdigest()
