from django.core.management.base import BaseCommand, CommandError

from core.alerts import send_alert


class Command(BaseCommand):
    help = "Envia um aviso por e-mail para ALERT_EMAIL (serve para testar a configuração de e-mail)."

    def add_arguments(self, parser):
        parser.add_argument("subject")
        parser.add_argument("body", nargs="?", default="")

    def handle(self, *args, **options):
        if not send_alert(options["subject"], options["body"] or options["subject"]):
            raise CommandError("O aviso não foi enviado (veja ALERT_EMAIL e EMAIL_* no .env e o log).")
        self.stdout.write("Aviso enviado.")
