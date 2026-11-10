"""Recebimento de arquivos: detecta o tipo, abre PDFs protegidos e guarda em
ASSISTANT_STORAGE_DIR (fora de MEDIA_ROOT)."""

import hashlib
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from .models import Attachment

logger = logging.getLogger(__name__)

IMAGE_MIMES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
IMAGE_EXTS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
              ".webp": "image/webp", ".gif": "image/gif"}
TEXT_EXTS = {".csv": "text/csv", ".ofx": "application/x-ofx", ".qfx": "application/x-ofx", ".txt": "text/plain"}
MAX_TEXT_CHARS = 400_000


class DocumentError(Exception):
    """Mensagem amigável para o usuário."""


@dataclass
class SavedAttachment:
    attachment: Attachment
    needs_password: bool = False


def detect_kind(filename, mime):
    ext = Path(filename or "").suffix.lower()
    mime = (mime or "").lower()
    if mime == "application/pdf" or ext == ".pdf":
        return "pdf", "application/pdf"
    if mime in IMAGE_MIMES:
        return "image", mime
    if ext in IMAGE_EXTS:
        return "image", IMAGE_EXTS[ext]
    if ext in TEXT_EXTS:
        return "text", TEXT_EXTS[ext]
    if mime.startswith("text/"):
        return "text", "text/plain"
    return None, mime


def _decode_text(data):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _try_decrypt(data, passwords):
    """Devolve os bytes do PDF sem senha, ou None se nenhuma senha serviu."""
    reader = PdfReader(io.BytesIO(data))
    if not reader.is_encrypted:
        return data
    for password in passwords:
        try:
            if reader.decrypt(password):
                out = io.BytesIO()
                PdfWriter(clone_from=reader).write(out)
                return out.getvalue()
        except Exception:  # senha errada ou algoritmo sem suporte
            logger.debug("Senha de PDF não serviu", exc_info=True)
    return None


def _storage_path(sha, filename):
    now = timezone.now()
    folder = Path(settings.ASSISTANT_STORAGE_DIR) / f"{now:%Y}" / f"{now:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename or "arquivo").name)[:80] or "arquivo"
    return folder / f"{sha[:16]}_{safe}"


def save_attachment(conversation, data, filename, mime):
    kind, mime = detect_kind(filename, mime)
    if kind is None:
        raise DocumentError("Formato não suportado. Envie PDF, foto (JPG/PNG), CSV ou OFX.")

    sha = hashlib.sha256(data).hexdigest()
    needs_password = False

    if kind == "pdf":
        try:
            decrypted = _try_decrypt(data, ["", *settings.PDF_PASSWORDS])
        except PdfReadError:
            raise DocumentError("Não consegui abrir este PDF (arquivo inválido ou corrompido).")
        if decrypted is None:
            needs_password = True
        else:
            data = decrypted
    elif kind == "text":
        text = _decode_text(data)
        if len(text) > MAX_TEXT_CHARS:
            raise DocumentError("Arquivo de texto grande demais. Envie um período menor.")
        data = text.encode("utf-8")

    path = _storage_path(sha, filename)
    path.write_bytes(data)
    attachment = Attachment.objects.create(
        conversation=conversation, kind=kind, filename=(filename or path.name)[:255], mime=mime,
        size=len(data), sha256=sha, storage_path=str(path),
    )
    return SavedAttachment(attachment, needs_password)


def unlock_pdf(attachment, password):
    """Tenta abrir o PDF com a senha informada; se der certo, regrava sem senha."""
    path = Path(attachment.storage_path)
    try:
        decrypted = _try_decrypt(path.read_bytes(), [password])
    except (PdfReadError, OSError):
        return False
    if decrypted is None:
        return False
    path.write_bytes(decrypted)
    attachment.size = len(decrypted)
    attachment.save(update_fields=["size"])
    return True
