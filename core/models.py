from django.db import models
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    """Category for financial transactions"""

    class TypeChoices(models.TextChoices):
        INCOME = "INCOME", _("Income")
        EXPENSE = "EXPENSE", _("Expense")
        BOTH = "BOTH", _("Both")

    name = models.CharField(_("name"), max_length=100)
    type = models.CharField(
        _("type"), max_length=10, choices=TypeChoices.choices, default=TypeChoices.BOTH
    )
    color = models.CharField(
        _("color"),
        max_length=7,
        blank=True,
        help_text=_("Hex color code (e.g., #FF5733)"),
    )
    icon = models.CharField(
        _("icon"), max_length=50, blank=True, help_text=_("Icon identifier")
    )
    active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["active", "type"]),
        ]

    def __str__(self):
        return self.name


class Tag(models.Model):
    """Tag for organizing transactions"""

    name = models.CharField(_("name"), max_length=50, unique=True)
    color = models.CharField(
        _("color"),
        max_length=7,
        blank=True,
        help_text=_("Hex color code (e.g., #FF5733)"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("tag")
        verbose_name_plural = _("tags")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Entity(models.Model):
    """Entity that receives or makes financial transactions"""

    class TypeChoices(models.TextChoices):
        SUPPLIER = "SUPPLIER", _("Supplier")
        EMPLOYER = "EMPLOYER", _("Employer")
        CLIENT = "CLIENT", _("Client")
        PERSON = "PERSON", _("Person")
        OTHER = "OTHER", _("Other")

    name = models.CharField(_("name"), max_length=200)
    type = models.CharField(
        _("type"), max_length=10, choices=TypeChoices.choices, default=TypeChoices.OTHER
    )
    document = models.CharField(
        _("document"), max_length=20, blank=True, help_text=_("CPF or CNPJ")
    )
    email = models.EmailField(_("email"), blank=True)
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("entity")
        verbose_name_plural = _("entities")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["active", "type"]),
            models.Index(fields=["document"]),
        ]

    def __str__(self):
        return self.name


class FamilyMember(models.Model):
    """Pessoa da família. As finanças são conjuntas: isto serve para saber de quem
    é cada conta/cartão, quem está falando com o bot e quando um Pix é apenas
    dinheiro mudando de mãos dentro da família."""

    name = models.CharField(_("name"), max_length=100, unique=True)
    aliases = models.TextField(
        _("names on documents"),
        blank=True,
        help_text=_("How this person's name appears on statements and invoices, one per line"),
    )
    telegram_chat_id = models.BigIntegerField(
        _("Telegram chat id"), null=True, blank=True, unique=True,
        help_text=_("Chat this person uses to talk to the bot"),
    )
    active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("family member")
        verbose_name_plural = _("family members")
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def alias_list(self):
        return [a.strip() for a in self.aliases.splitlines() if a.strip()]
