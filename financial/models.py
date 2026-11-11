from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator


class Recurrence(models.Model):
    """Recurrence pattern for automatic transaction generation"""

    class TypeChoices(models.TextChoices):
        INCOME = "INCOME", _("Income")
        EXPENSE = "EXPENSE", _("Expense")

    class FrequencyChoices(models.TextChoices):
        WEEKLY = "WEEKLY", _("Weekly")
        MONTHLY = "MONTHLY", _("Monthly")
        YEARLY = "YEARLY", _("Yearly")
        CUSTOM = "CUSTOM", _("Custom")

    description = models.CharField(_("description"), max_length=200)
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    type = models.CharField(_("type"), max_length=10, choices=TypeChoices.choices)
    category = models.ForeignKey(
        "core.Category",
        on_delete=models.PROTECT,
        related_name="recurrences",
        verbose_name=_("category"),
    )
    entity = models.ForeignKey(
        "core.Entity",
        on_delete=models.PROTECT,
        related_name="recurrences",
        verbose_name=_("entity"),
        null=True,
        blank=True,
    )
    payment_method = models.ForeignKey(
        "accounts.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="recurrences",
        verbose_name=_("payment method"),
    )
    frequency = models.CharField(
        _("frequency"),
        max_length=10,
        choices=FrequencyChoices.choices,
        default=FrequencyChoices.MONTHLY,
    )
    reference_day = models.PositiveSmallIntegerField(
        _("reference day"),
        validators=[MinValueValidator(1)],
        help_text=_("Day of month (1-31) or day of week (1-7)"),
    )
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(
        _("end date"),
        null=True,
        blank=True,
        help_text=_("Leave blank for infinite recurrence"),
    )
    active = models.BooleanField(_("active"), default=True)
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("recurrence")
        verbose_name_plural = _("recurrences")
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["active", "frequency"]),
            models.Index(fields=["start_date", "end_date"]),
        ]

    def __str__(self):
        return f"{self.description} - {self.get_frequency_display()}"


class Transaction(models.Model):
    """Financial transaction (income or expense)"""

    class TypeChoices(models.TextChoices):
        INCOME = "INCOME", _("Income")
        EXPENSE = "EXPENSE", _("Expense")

    type = models.CharField(_("type"), max_length=10, choices=TypeChoices.choices)
    description = models.CharField(_("description"), max_length=200)
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    date = models.DateField(_("date"))
    category = models.ForeignKey(
        "core.Category",
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name=_("category"),
    )
    entity = models.ForeignKey(
        "core.Entity",
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name=_("entity"),
        null=True,
        blank=True,
    )
    payment_method = models.ForeignKey(
        "accounts.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name=_("payment method"),
    )
    confirmed = models.BooleanField(
        _("confirmed"),
        default=False,
        help_text=_("Whether the transaction has been confirmed"),
    )
    notes = models.TextField(_("notes"), blank=True)
    recurrence = models.ForeignKey(
        Recurrence,
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name=_("recurrence"),
        null=True,
        blank=True,
        help_text=_("If generated from a recurrence"),
    )
    purchase = models.ForeignKey(
        "financial.Purchase",
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name=_("purchase"),
        null=True,
        blank=True,
        help_text=_("If this is a statement payment linked to a purchase"),
    )
    tags = models.ManyToManyField(
        "core.Tag",
        through="TransactionTag",
        related_name="transactions",
        verbose_name=_("tags"),
        blank=True,
    )
    on_behalf_of = models.ForeignKey(
        "core.Entity",
        on_delete=models.PROTECT,
        related_name="third_party_transactions",
        verbose_name=_("on behalf of"),
        null=True,
        blank=True,
        help_text=_("Someone outside the family who owes this purchase back (lent card), or who "
                    "paid it back (income). Left out of the family's spending and income."),
    )
    invoice_month = models.DateField(
        _("invoice month"),
        null=True,
        blank=True,
        help_text=_("Credit card only: first day of the due month of the invoice that billed this "
                    "purchase. Blank: computed from the card's closing day."),
    )
    external_id = models.CharField(
        _("external id"),
        max_length=120,
        null=True,
        blank=True,
        unique=True,
        help_text=_("Import key used to avoid duplicates (e.g., card invoice line, OFX FITID)"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("transaction")
        verbose_name_plural = _("transactions")
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date", "type"]),
            models.Index(fields=["confirmed"]),
            models.Index(fields=["-date", "category"]),
            models.Index(fields=["-date", "payment_method"]),
        ]

    def __str__(self):
        return f"{self.description} - {self.amount} ({self.date})"


class TransactionTag(models.Model):
    """Many-to-many relationship between Transaction and Tag"""

    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, verbose_name=_("transaction")
    )
    tag = models.ForeignKey("core.Tag", on_delete=models.CASCADE, verbose_name=_("tag"))

    class Meta:
        verbose_name = _("transaction tag")
        verbose_name_plural = _("transaction tags")
        unique_together = [["transaction", "tag"]]
        indexes = [
            models.Index(fields=["transaction", "tag"]),
        ]

    def __str__(self):
        return f"{self.transaction.description} - {self.tag.name}"


class Purchase(models.Model):
    """Purchase with installments"""

    description = models.CharField(_("description"), max_length=200)
    total_amount = models.DecimalField(
        _("total amount"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    purchase_date = models.DateField(_("purchase date"))
    number_of_installments = models.PositiveSmallIntegerField(
        _("number of installments"), validators=[MinValueValidator(1)]
    )
    entity = models.ForeignKey(
        "core.Entity",
        on_delete=models.PROTECT,
        related_name="purchases",
        verbose_name=_("entity"),
        null=True,
        blank=True,
        help_text=_("Where the purchase was made"),
    )
    category = models.ForeignKey(
        "core.Category",
        on_delete=models.PROTECT,
        related_name="purchases",
        verbose_name=_("category"),
    )
    payment_method = models.ForeignKey(
        "accounts.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="purchases",
        verbose_name=_("payment method"),
    )
    on_behalf_of = models.ForeignKey(
        "core.Entity",
        on_delete=models.PROTECT,
        related_name="third_party_purchases",
        verbose_name=_("on behalf of"),
        null=True,
        blank=True,
        help_text=_("Someone outside the family who owes this purchase back (lent card). "
                    "Left out of the family's spending."),
    )
    notes = models.TextField(_("notes"), blank=True)
    first_invoice_month = models.DateField(
        _("first invoice month"),
        null=True,
        blank=True,
        help_text=_("First day of the invoice month of the 1st installment. "
                    "Blank: computed from the card's closing/due days."),
    )
    external_id = models.CharField(
        _("external id"),
        max_length=120,
        null=True,
        blank=True,
        unique=True,
        help_text=_("Import key used to avoid duplicates"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    @property
    def installment_amount(self):
        """Calculate the amount of each installment"""
        return self.total_amount / self.number_of_installments

    @property
    def paid_installments_count(self):
        """Count of paid installments"""
        return self.installments.filter(paid=True).count()

    class Meta:
        verbose_name = _("purchase")
        verbose_name_plural = _("purchases")
        ordering = ["-purchase_date", "-created_at"]
        indexes = [
            models.Index(fields=["-purchase_date"]),
            models.Index(fields=["payment_method", "-purchase_date"]),
        ]

    def __str__(self):
        return f"{self.description} - {self.number_of_installments}x"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # Auto-generate installments if this is a new purchase
        if is_new:
            self.generate_installments()

    def generate_installments(self):
        """Gera (ou regenera) as parcelas desta compra.

        - Vencimento da 1ª parcela: `first_invoice_month` ou fechamento/vencimento
          do cartão (ver `financial.forecast.invoice_period_for`); sem esses dados,
          mantém o comportamento antigo (1ª parcela na data da compra).
        - Valores arredondados em centavos; a última parcela absorve a diferença.
        - Ao regenerar, preserva o `paid` de cada número de parcela.
        """
        from decimal import ROUND_DOWN, Decimal

        from dateutil.relativedelta import relativedelta

        from .forecast import first_installment_due_date

        paid_numbers = set(
            self.installments.filter(paid=True).values_list("installment_number", flat=True)
        )
        self.installments.all().delete()

        n = self.number_of_installments
        total = Decimal(self.total_amount)
        base = (total / n).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        last = total - base * (n - 1)
        first_due = first_installment_due_date(
            self.payment_method, self.purchase_date, self.first_invoice_month
        )

        installments = []
        for i in range(1, n + 1):
            due_date = first_due + relativedelta(months=i - 1)
            installments.append(
                Installment(
                    purchase=self,
                    installment_number=i,
                    amount=last if i == n else base,
                    due_date=due_date,
                    reference_month=due_date.month,
                    reference_year=due_date.year,
                    paid=i in paid_numbers,
                )
            )
        Installment.objects.bulk_create(installments)


class Installment(models.Model):
    """Installment of a purchase"""

    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="installments",
        verbose_name=_("purchase"),
    )
    installment_number = models.PositiveSmallIntegerField(
        _("installment number"), validators=[MinValueValidator(1)]
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    due_date = models.DateField(_("due date"))
    reference_month = models.PositiveSmallIntegerField(
        _("reference month"),
        validators=[MinValueValidator(1)],
        help_text=_("Month number (1-12)"),
    )
    reference_year = models.PositiveIntegerField(_("reference year"))
    paid = models.BooleanField(_("paid"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("installment")
        verbose_name_plural = _("installments")
        ordering = ["purchase", "installment_number"]
        unique_together = [["purchase", "installment_number"]]
        indexes = [
            models.Index(fields=["reference_year", "reference_month"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["paid"]),
        ]

    def __str__(self):
        return f"{self.purchase.description} - {self.installment_number}/{self.purchase.number_of_installments}"


class Transfer(models.Model):
    """Movimento que não é receita nem despesa: pagamento de fatura de cartão
    ou transferência entre contas próprias.

    Fica fora de Transaction de propósito: os gastos do cartão já são contados
    na compra; o pagamento da fatura só tira dinheiro da conta."""

    date = models.DateField(_("date"))
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    description = models.CharField(_("description"), max_length=200, blank=True)
    from_account = models.ForeignKey(
        "accounts.BankAccount",
        on_delete=models.PROTECT,
        related_name="transfers_out",
        verbose_name=_("from account"),
        null=True,
        blank=True,
    )
    to_account = models.ForeignKey(
        "accounts.BankAccount",
        on_delete=models.PROTECT,
        related_name="transfers_in",
        verbose_name=_("to account"),
        null=True,
        blank=True,
    )
    to_card = models.ForeignKey(
        "accounts.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="invoice_payments",
        verbose_name=_("paid card"),
        null=True,
        blank=True,
        help_text=_("Credit card whose invoice was paid"),
    )
    invoice_year = models.PositiveSmallIntegerField(_("invoice year"), null=True, blank=True)
    invoice_month = models.PositiveSmallIntegerField(
        _("invoice month"), null=True, blank=True, help_text=_("Due month of the paid invoice")
    )
    external_id = models.CharField(
        _("external id"), max_length=120, null=True, blank=True, unique=True
    )
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("transfer")
        verbose_name_plural = _("transfers")
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["-date"]),
            models.Index(fields=["to_card", "invoice_year", "invoice_month"]),
        ]

    def __str__(self):
        target = self.to_card or self.to_account or "?"
        return f"{self.date:%d/%m/%Y} {self.amount} -> {target}"

    def mark_invoice_paid(self):
        """Marca como pagas as parcelas do cartão no mês da fatura paga.
        Retorna os ids das parcelas alteradas (para desfazer)."""
        if not (self.to_card_id and self.invoice_year and self.invoice_month):
            return []
        from django.db.models import Q

        qs = Installment.objects.filter(
            Q(purchase__payment_method_id=self.to_card_id)
            | Q(purchase__payment_method__billing_card_id=self.to_card_id),
            reference_year=self.invoice_year,
            reference_month=self.invoice_month,
            paid=False,
        )
        ids = list(qs.values_list("pk", flat=True))
        Installment.objects.filter(pk__in=ids).update(paid=True)
        return ids
