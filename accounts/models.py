from django.db import models


class Entity(models.Model):
    name = models.CharField("Nome", max_length=100)
    description = models.TextField("Descrição", blank=True, null=True)
    person_type = models.CharField(
        "Tipo de Pessoa",
        max_length=1,
        choices=[
            ("F", "Física"),
            ("J", "Jurídica"),
        ],
        default="F",
    )
    document = models.CharField(
        "CPF/CNPJ", max_length=14, blank=True, null=True
    )

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Entidade"
        verbose_name_plural = "Entidades"


class PaymentMethod(models.Model):
    fin_institution = models.CharField("Instituição Financeira", max_length=100)
    owner = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="payment_methods",
        verbose_name="Proprietário",
    )
    payment_type = models.CharField(
        "Tipo de Pagamento",
        max_length=1,
        choices=[
            ("C", "Cartão"),
            ("B", "Boleto"),
            ("D", "Débito"),
            ("P", "Pix"),
            ("T", "Transferência"),
            ("O", "Outros")
        ],
        default="C",
    )
    description = models.TextField("Descrição", blank=True, null=True)

    def __str__(self):
        return f"{self.fin_institution} - {self.owner.name}"
    
    class Meta:
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"
