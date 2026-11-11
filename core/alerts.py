"""Avisos operacionais por e-mail (gasto com IA, falha de backup).

Destinatário em `ALERT_EMAIL`; servidor SMTP em `EMAIL_*`. Sem `EMAIL_HOST` o
e-mail vai para o console (desenvolvimento)."""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_alert(subject, body):
    """Envia o aviso. Nunca levanta erro: devolve True se o e-mail saiu."""
    to = [a.strip() for a in (settings.ALERT_EMAIL or "").split(",") if a.strip()]
    if not to:
        logger.warning("Aviso sem destinatário (ALERT_EMAIL vazio): %s", subject)
        return False
    try:
        send_mail(f"[Confin] {subject}", body, settings.DEFAULT_FROM_EMAIL, to, fail_silently=False)
    except Exception:
        logger.exception("Falha ao enviar aviso por e-mail: %s", subject)
        return False
    return True
