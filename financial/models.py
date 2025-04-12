from django.db import models
from django.forms import ValidationError


class Category(models.Model):
    name = models.CharField("Nome", max_length=100)
    description = models.TextField("Descrição", blank=True, null=True)
    is_income = models.BooleanField("Receita?", default=False)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        ordering = ["name"]


class FinancialRecord(models.Model):
    amount = models.DecimalField("Valor", max_digits=10, decimal_places=2)
    description = models.TextField("Descrição")
    entity = models.ForeignKey(
        "accounts.Entity",
        on_delete=models.CASCADE,
        related_name="financial_records",
        verbose_name="Entidade",
    )
    payment_method = models.ForeignKey(
        "accounts.PaymentMethod",
        on_delete=models.CASCADE,
        related_name="financial_records",
        verbose_name="Forma de Pagamento",
    )
    date = models.DateField("Data")
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="financial_records",
        verbose_name="Categoria",
    )

    @property
    def is_income(self):
        return self.amount > 0

    def clean(self):
        if self.category:
            if (self.category.is_income and self.amount < 0) or (
                not self.category.is_income and self.amount > 0
            ):
                raise ValidationError(
                    {"amount": "A categoria escolhida não condiz com o valor."}
                )
        return super().clean()

    def __str__(self):
        return f"{self.entity.name} - R$ {self.amount} em {self.date}"
    
    class Meta:
        verbose_name = "Registro Financeiro"
        verbose_name_plural = "Registros Financeiros"
        ordering = ["-date", "-amount"]


class Installment(models.Model):
    fin_record = models.ForeignKey(
        FinancialRecord,
        on_delete=models.CASCADE,
        related_name="installments",
        blank=True,
        null=True,
        verbose_name="Registro Financeiro",
    )
    installment_number = models.PositiveIntegerField("Número da parcela")
    due_date = models.DateField("Data de vencimento")
    amount = models.DecimalField("Valor", max_digits=10, decimal_places=2)
    is_paid = models.BooleanField("Pago?", default=False)

    def __str__(self):
        return f"{self.installment_number}ª Parcela - R$ {self.amount}"

    class Meta:
        verbose_name = "Parcela"
        verbose_name_plural = "Parcelas"
        ordering = ["-due_date", "installment_number"]
