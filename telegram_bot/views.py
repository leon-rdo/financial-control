import hmac
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .bot import ingest_update
from .client import webhook_secret_token

logger = logging.getLogger(__name__)


def _same(a, b):
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


@login_not_required
@csrf_exempt
@require_http_methods(["POST"])
def telegram_webhook(request, secret):
    """Webhook do Telegram: só valida, grava na fila e responde 200 na hora.
    O processamento (IA) acontece no worker `run_telegram_worker`."""
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected or not _same(secret, expected):
        return HttpResponseForbidden("Invalid secret")
    if not _same(request.headers.get("X-Telegram-Bot-Api-Secret-Token"), webhook_secret_token()):
        return HttpResponseForbidden("Invalid secret token")

    try:
        update = json.loads(request.body)
        ingest_update(update)
    except json.JSONDecodeError:
        logger.warning("JSON inválido no webhook do Telegram")
    except Exception:
        logger.exception("Erro ao registrar update do Telegram")

    return JsonResponse({"ok": True})
