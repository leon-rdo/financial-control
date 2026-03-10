import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Configura o webhook do Telegram Bot"

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            type=str,
            required=True,
            help="URL pública do webhook (ex: https://meudominio.com/telegram/webhook/<secret>/)",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Remove o webhook atual",
        )

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN não configurado no .env"))
            return

        api = f"https://api.telegram.org/bot{token}"

        if options["delete"]:
            resp = requests.post(f"{api}/deleteWebhook", timeout=10)
            data = resp.json()
            if data.get("ok"):
                self.stdout.write(self.style.SUCCESS("Webhook removido com sucesso"))
            else:
                self.stderr.write(self.style.ERROR(f"Erro: {data}"))
            return

        url = options["url"]
        resp = requests.post(
            f"{api}/setWebhook",
            json={"url": url, "allowed_updates": ["message", "callback_query"]},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"Webhook configurado: {url}"))
        else:
            self.stderr.write(self.style.ERROR(f"Erro: {data}"))
