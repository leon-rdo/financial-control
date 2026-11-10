"""Worker do bot: processa a fila de TelegramUpdate (um chat por vez).

Uso:
    python manage.py run_telegram_worker          # produção (com webhook)
    python manage.py run_telegram_worker --poll   # desenvolvimento, sem URL pública
                                                  # (antes: setup_telegram_webhook --delete)
"""

import logging
import time
import traceback

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection
from django.db.models import F, Max
from django.utils import timezone

from telegram_bot import bot, client
from telegram_bot.models import TelegramUpdate

logger = logging.getLogger("telegram_bot.worker")


class Command(BaseCommand):
    help = "Processa as mensagens do Telegram recebidas pelo webhook (ou por polling com --poll)."

    def add_arguments(self, parser):
        parser.add_argument("--poll", action="store_true", help="Busca updates via getUpdates (sem webhook).")
        parser.add_argument("--once", action="store_true", help="Processa o que estiver pronto e sai.")
        parser.add_argument("--quiet-seconds", type=float, default=2.0,
                            help="Espera este silêncio do chat para juntar mensagens (álbuns, arquivo + texto).")
        parser.add_argument("--max-attempts", type=int, default=1,
                            help="Tentativas por update antes de marcar como falho.")

    def handle(self, *args, **options):
        self.quiet = options["quiet_seconds"]
        self.max_attempts = options["max_attempts"]
        stale = TelegramUpdate.objects.filter(status=TelegramUpdate.Status.PROCESSING).update(
            status=TelegramUpdate.Status.PENDING)
        if stale:
            logger.info("%s update(s) interrompido(s) voltaram para a fila", stale)

        offset = None
        if options["poll"]:
            last = TelegramUpdate.objects.aggregate(m=Max("update_id"))["m"]
            offset = last + 1 if last is not None else None
            self.stdout.write("Worker em modo polling. Ctrl+C para sair.")
        else:
            self.stdout.write("Worker iniciado. Ctrl+C para sair.")

        try:
            while True:
                # Processo de longa duração: recicla conexões velhas com o banco
                # (nunca no meio de uma transação, como nos testes)
                if not connection.in_atomic_block:
                    close_old_connections()
                if options["poll"]:
                    has_pending = TelegramUpdate.objects.filter(status=TelegramUpdate.Status.PENDING).exists()
                    data = client.get_updates(offset, timeout=1 if has_pending else 20)
                    if data.get("ok"):
                        for update in data.get("result", []):
                            bot.ingest_update(update)
                            offset = update["update_id"] + 1
                    elif data.get("error_code") == 409:
                        self.stderr.write("Há um webhook ativo. Rode: python manage.py setup_telegram_webhook --delete")
                        return
                    else:
                        time.sleep(3)

                worked = self.process_ready()
                if options["once"] and not worked and not self._pending_exists():
                    return
                if not worked and not options["poll"]:
                    time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write("Encerrado.")

    def _pending_exists(self):
        return TelegramUpdate.objects.filter(status=TelegramUpdate.Status.PENDING).exists()

    def process_ready(self):
        """Processa o próximo chat cujas mensagens já 'assentaram'. True se processou algo."""
        first = TelegramUpdate.objects.filter(status=TelegramUpdate.Status.PENDING).order_by("update_id").first()
        if first is None:
            return False

        if first.chat_id is None:
            TelegramUpdate.objects.filter(pk=first.pk).update(
                status=TelegramUpdate.Status.DONE, processed_at=timezone.now())
            return True

        batch = list(TelegramUpdate.objects.filter(
            status=TelegramUpdate.Status.PENDING, chat_id=first.chat_id).order_by("update_id"))
        newest = max(u.received_at for u in batch)
        if (timezone.now() - newest).total_seconds() < self.quiet:
            time.sleep(0.3)
            return False

        ids = [u.pk for u in batch]
        claimed = TelegramUpdate.objects.filter(pk__in=ids, status=TelegramUpdate.Status.PENDING).update(
            status=TelegramUpdate.Status.PROCESSING, attempts=F("attempts") + 1)
        if not claimed:
            return False

        try:
            bot.process_chat_updates(first.chat_id, [u.payload for u in batch])
        except Exception:
            logger.exception("Erro ao processar updates do chat %s", first.chat_id)
            error = traceback.format_exc()[-4000:]
            for u in TelegramUpdate.objects.filter(pk__in=ids):
                u.status = (TelegramUpdate.Status.FAILED if u.attempts >= self.max_attempts
                            else TelegramUpdate.Status.PENDING)
                u.error = error
                u.save(update_fields=["status", "error"])
            client.send_message(first.chat_id, "⚠️ Tive um erro ao processar sua mensagem. Tente novamente.")
            return True

        TelegramUpdate.objects.filter(pk__in=ids).update(
            status=TelegramUpdate.Status.DONE, processed_at=timezone.now())
        return True
