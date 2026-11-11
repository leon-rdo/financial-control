from django.db import models


class TelegramUpdate(models.Model):
    """Fila de updates recebidos pelo webhook (ou polling), processados pelo worker.

    O `update_id` único deduplica reenvios do Telegram.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PROCESSING = "processing", "Processando"
        DONE = "done", "Concluído"
        FAILED = "failed", "Falhou"

    update_id = models.BigIntegerField(unique=True)
    chat_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    payload = models.JSONField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["update_id"]
        verbose_name = "Update do Telegram"
        verbose_name_plural = "Updates do Telegram"
        indexes = [models.Index(fields=["status", "update_id"])]

    def __str__(self):
        return f"#{self.update_id} [{self.status}]"


class DigestLog(models.Model):
    """Avisos automáticos já enviados (evita repetir o mesmo aviso)."""

    key = models.CharField(max_length=120, unique=True)
    text = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        verbose_name = "Aviso enviado"
        verbose_name_plural = "Avisos enviados"

    def __str__(self):
        return self.key
