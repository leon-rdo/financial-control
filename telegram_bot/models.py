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
