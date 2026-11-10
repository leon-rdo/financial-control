import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from telegram_bot.client import webhook_secret_token


class Command(BaseCommand):
    help = "Configura (ou remove) o webhook do Telegram Bot"

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            type=str,
            help="URL pública do webhook (ex: https://meudominio.com/telegram/webhook/<secret>/)",
        )
        parser.add_argument("--delete", action="store_true", help="Remove o webhook atual")

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise CommandError("TELEGRAM_BOT_TOKEN não configurado no .env")
        api = f"https://api.telegram.org/bot{token}"

        if options["delete"]:
            data = requests.post(f"{api}/deleteWebhook", timeout=10).json()
            if data.get("ok"):
                self.stdout.write(self.style.SUCCESS("Webhook removido com sucesso"))
            else:
                self.stderr.write(self.style.ERROR(f"Erro: {data}"))
            return

        url = options["url"]
        if not url:
            raise CommandError("Informe --url (ou use --delete).")
        if not settings.TELEGRAM_WEBHOOK_SECRET:
            raise CommandError("TELEGRAM_WEBHOOK_SECRET não configurado no .env")

        data = requests.post(
            f"{api}/setWebhook",
            json={
                "url": url,
                "allowed_updates": ["message", "callback_query"],
                "secret_token": webhook_secret_token(),
            },
            timeout=10,
        ).json()
        if data.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"Webhook configurado: {url}"))
            self.stdout.write("Lembre de manter o worker rodando: python manage.py run_telegram_worker")
        else:
            self.stderr.write(self.style.ERROR(f"Erro: {data}"))
