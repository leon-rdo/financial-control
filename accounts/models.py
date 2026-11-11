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
    holder = models.ForeignKey(
        "core.FamilyMember",
        on_delete=models.SET_NULL,
        related_name="bank_accounts",
        verbose_name=_("holder"),
        null=True,
        blank=True,
        help_text=_("Family member who owns this account (pots inherit from their account)"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        verbose_name=_("parent account"),
        null=True,
        blank=True,
        help_text=_("Fill in for a savings pot (caixinha/cofrinho) that lives inside another account"),
    )
    opening_balance = models.DecimalField(
        _("opening balance"),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_("Balance at the end of the opening balance date"),
    )
    opening_balance_date = models.DateField(
        _("opening balance date"),
        null=True,
        blank=True,
        help_text=_("Only movements after this date change the balance. Blank: all movements count."),
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
        if self.parent_id:
            return f"{self.parent.name} › {self.name}"
        return f"{self.name} - {self.bank}"

    @property
    def effective_holder(self):
        """Titular desta conta; a caixinha herda o da conta em que fica."""
        if self.holder_id:
            return self.holder
        return self.parent.holder if self.parent_id else None

    @property
    def is_reserve(self):
        """Dinheiro guardado (caixinha/cofrinho/investimento), fora do saldo do dia a dia."""
        return bool(self.parent_id) or self.type == self.TypeChoices.INVESTMENT

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.parent_id and (self.parent_id == self.pk or self.parent.parent_id):
            raise ValidationError({"parent": _("A pot must belong to a regular account (one level only)")})


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

    holder = models.ForeignKey(
        "core.FamilyMember",
        on_delete=models.SET_NULL,
        related_name="payment_methods",
        verbose_name=_("holder"),
        null=True,
        blank=True,
        help_text=_("Family member who uses this card/method. Blank: the holder of its account or main card."),
    )
    billing_card = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="billed_cards",
        verbose_name=_("billed with"),
        null=True,
        blank=True,
        help_text=_("Additional/virtual card billed on another card's invoice. "
                    "Closing and due days come from that card."),
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

    @property
    def effective_holder(self):
        """Quem usa este método: o titular informado, senão o da conta, senão o do
        cartão principal da fatura."""
        if self.holder_id:
            return self.holder
        if self.bank_account_id and self.bank_account.effective_holder:
            return self.bank_account.effective_holder
        if self.billing_card_id:
            return self.billing_card.effective_holder
        return None

    @property
    def invoice_card(self):
        """Cartão em cuja fatura este cartão é cobrado (ele mesmo, se for o principal)."""
        return self.billing_card if self.billing_card_id else self

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.billing_card_id:
            if self.billing_card_id == self.pk or self.billing_card.billing_card_id:
                raise ValidationError({"billing_card": _("Choose the main card of the invoice")})
            if self.type != self.TypeChoices.CREDIT or self.billing_card.type != self.TypeChoices.CREDIT:
                raise ValidationError({"billing_card": _("Only credit cards can share an invoice")})

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


class BalanceSnapshot(models.Model):
    """Saldo conhecido de uma conta no fim de um dia (de extrato ou informado).

    O saldo atual é calculado a partir do snapshot mais recente + movimentos
    posteriores (ver financial.forecast.account_balances)."""

    class SourceChoices(models.TextChoices):
        MANUAL = "MANUAL", _("Manual")
        STATEMENT = "STATEMENT", _("Statement")
        ASSISTANT = "ASSISTANT", _("Assistant")

    account = models.ForeignKey(
        BankAccount,
        on_delete=models.CASCADE,
        related_name="balance_snapshots",
        verbose_name=_("bank account"),
    )
    date = models.DateField(_("date"))
    balance = models.DecimalField(_("balance"), max_digits=12, decimal_places=2)
    source = models.CharField(
        _("source"), max_length=10, choices=SourceChoices.choices, default=SourceChoices.MANUAL
    )
    notes = models.CharField(_("notes"), max_length=200, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("balance snapshot")
        verbose_name_plural = _("balance snapshots")
        ordering = ["-date"]
        unique_together = [["account", "date"]]

    def __str__(self):
        return f"{self.account.name} {self.date:%d/%m/%Y}: {self.balance}"
