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
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

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
        """Generate installments for this purchase"""
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta

        # Delete existing installments (if any)
        self.installments.all().delete()

        installment_amount = self.total_amount / self.number_of_installments

        for i in range(1, self.number_of_installments + 1):
            # Calculate due date (first installment on purchase date, then monthly)
            due_date = self.purchase_date + relativedelta(months=i - 1)

            Installment.objects.create(
                purchase=self,
                installment_number=i,
                amount=installment_amount,
                due_date=due_date,
                reference_month=due_date.month,
                reference_year=due_date.year,
            )


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
