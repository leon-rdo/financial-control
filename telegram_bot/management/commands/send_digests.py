"""Envia os avisos automáticos do dia (rodar 1x por dia, via cron/systemd timer).

    python manage.py send_digests            # envia o que ainda não foi enviado
    python manage.py send_digests --dry-run  # só mostra
"""

from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand

from assistant import agent
from telegram_bot import client
from telegram_bot.digests import build_digests
from telegram_bot.models import DigestLog


class Command(BaseCommand):
    help = "Envia avisos automáticos pelo Telegram (vencimento de fatura, saldo negativo, resumo mensal)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Mostra os avisos sem enviar nem registrar.")
        parser.add_argument("--date", type=date.fromisoformat, help="Simula outra data (AAAA-MM-DD).")

    def handle(self, *args, **options):
        chat_ids = [int(x) for x in settings.TELEGRAM_ALLOWED_CHAT_IDS.split(",") if x.strip()]
        digests = build_digests(options["date"])
        sent_keys = set(DigestLog.objects.filter(key__in=[d.key for d in digests]).values_list("key", flat=True))
        pending = [d for d in digests if d.key not in sent_keys]

        if not pending:
            self.stdout.write("Nenhum aviso novo.")
            return
        for digest in pending:
            if options["dry_run"]:
                self.stdout.write(f"[{digest.key}]\n{digest.text}\n")
                continue
            delivered = False
            for chat_id in chat_ids:
                if client.send_message(chat_id, digest.text).get("ok"):
                    delivered = True
                    agent.add_note(chat_id, f"Aviso automático enviado ao usuário: {digest.text}")
            if delivered:
                DigestLog.objects.create(key=digest.key, text=digest.text)
                self.stdout.write(self.style.SUCCESS(f"Enviado: {digest.key}"))
            else:
                self.stderr.write(self.style.ERROR(f"Falha ao enviar: {digest.key}"))
