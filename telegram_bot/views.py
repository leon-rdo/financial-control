import json
import logging

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .handlers import process_update

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def telegram_webhook(request, secret):
    """Endpoint do webhook do Telegram."""
    if secret != settings.TELEGRAM_WEBHOOK_SECRET:
        return HttpResponseForbidden("Invalid secret")

    try:
        update = json.loads(request.body)
        process_update(update)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON from Telegram webhook")
    except Exception:
        logger.exception("Error processing Telegram update")

    return JsonResponse({"ok": True})
