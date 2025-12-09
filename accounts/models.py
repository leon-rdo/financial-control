from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator


class BankAccount(models.Model):
    """Bank account for managing finances"""

    class TypeChoices(models.TextChoices):
        CHECKING = "CHECKING", _("Checking Account")
        SAVINGS = "SAVINGS", _("Savings Account")
        INVESTMENT = "INVESTMENT", _("Investment Account")

    name = models.CharField(
        _("name"),
        max_length=100,
        help_text=_('Account name (e.g., "Nubank", "Bradesco CC")'),
    )
    bank = models.CharField(_("bank"), max_length=100)
    type = models.CharField(
        _("type"),
        max_length=15,
        choices=TypeChoices.choices,
        default=TypeChoices.CHECKING,
    )
    color = models.CharField(
        _("color"),
        max_length=7,
        blank=True,
        help_text=_("Hex color code (e.g., #FF5733)"),
    )
    active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("bank account")
        verbose_name_plural = _("bank accounts")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["active"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.bank}"


class PaymentMethod(models.Model):
    """Payment method for transactions"""

    class TypeChoices(models.TextChoices):
        PIX = "PIX", _("PIX")
        DEBIT = "DEBIT", _("Debit Card")
        CREDIT = "CREDIT", _("Credit Card")
        CASH = "CASH", _("Cash")
        TRANSFER = "TRANSFER", _("Bank Transfer")
        BOLETO = "BOLETO", _("Boleto")

    name = models.CharField(
        _("name"),
        max_length=100,
        help_text=_('Payment method name (e.g., "Nubank Credit Card")'),
    )
    type = models.CharField(_("type"), max_length=10, choices=TypeChoices.choices)
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name="payment_methods",
        verbose_name=_("bank account"),
        null=True,
        blank=True,
        help_text=_("Associated bank account (for debit/PIX)"),
    )

    # Credit card specific fields
    credit_limit = models.DecimalField(
        _("credit limit"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=_("Only for credit cards"),
    )
    closing_day = models.PositiveSmallIntegerField(
        _("closing day"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=_("Day of month when the statement closes (1-31)"),
    )
    due_day = models.PositiveSmallIntegerField(
        _("due day"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=_("Day of month when payment is due (1-31)"),
    )

    active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("payment method")
        verbose_name_plural = _("payment methods")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["active", "type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError

        # Validate credit card fields
        if self.type == self.TypeChoices.CREDIT:
            if self.closing_day and (self.closing_day < 1 or self.closing_day > 31):
                raise ValidationError(
                    {"closing_day": _("Closing day must be between 1 and 31")}
                )
            if self.due_day and (self.due_day < 1 or self.due_day > 31):
                raise ValidationError(
                    {"due_day": _("Due day must be between 1 and 31")}
                )
