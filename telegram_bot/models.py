from django.db import models


class PendingTransaction(models.Model):
    telegram_chat_id = models.BigIntegerField()
    telegram_message_id = models.BigIntegerField(null=True, blank=True)

    # Dados extraídos pela IA
    transaction_type = models.CharField(max_length=10)  # INCOME, EXPENSE, PURCHASE
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    number_of_installments = models.PositiveSmallIntegerField(default=1)

    # Matching (FKs opcionais)
    category = models.ForeignKey(
        "core.Category", null=True, blank=True, on_delete=models.SET_NULL
    )
    payment_method = models.ForeignKey(
        "accounts.PaymentMethod", null=True, blank=True, on_delete=models.SET_NULL
    )
    entity = models.ForeignKey(
        "core.Entity", null=True, blank=True, on_delete=models.SET_NULL
    )

    # Metadados
    raw_ai_response = models.JSONField(default=dict, blank=True)
    image_file_id = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            ("pending", "Pendente"),
            ("confirmed", "Confirmada"),
            ("cancelled", "Cancelada"),
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Transação Pendente"
        verbose_name_plural = "Transações Pendentes"

    def __str__(self):
        return f"[{self.status}] {self.description} - R$ {self.amount}"


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
