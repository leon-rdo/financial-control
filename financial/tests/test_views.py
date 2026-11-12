from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import BalanceSnapshot, BankAccount, PaymentMethod
from core.models import Category
from financial.models import Purchase, Transaction


class LoginRequiredTests(TestCase):
    def test_pages_redirect_to_login(self):
        for name in ("financial:dashboard", "financial:invoice_forecast", "financial:transaction_list",
                     "accounts:bankaccount_list", "core:category_list"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertTrue(response["Location"].startswith(reverse("login")), name)

    def test_login_page_is_public(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)


class PagesTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user("leo", password="x")
        self.client.force_login(user)
        self.cat = Category.objects.create(name="Compras", type="EXPENSE")
        self.acct = BankAccount.objects.create(name="Inter", bank="Inter")
        self.card = PaymentMethod.objects.create(name="Visa", type="CREDIT", bank_account=self.acct,
                                                 closing_day=27, due_day=10)
        today = date.today()
        Purchase.objects.create(description="Geladeira", total_amount=Decimal("900"), purchase_date=today,
                                number_of_installments=3, category=self.cat, payment_method=self.card)
        Transaction.objects.create(type="EXPENSE", description="Mercado à vista", amount=Decimal("80"),
                                   date=today, category=self.cat, payment_method=self.card, confirmed=True)
        BalanceSnapshot.objects.create(account=self.acct, date=today, balance=Decimal("1234.56"))

    def test_invoice_forecast_lists_installments_and_single_purchases(self):
        response = self.client.get(reverse("financial:invoice_forecast"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Geladeira")
        self.assertContains(response, "Mercado à vista")
        self.assertEqual(response.context["grand_total"], Decimal("980"))

    def test_dashboard_uses_account_balances(self):
        response = self.client.get(reverse("financial:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_balance"], Decimal("1234.56"))

    def test_monthly_report_and_account_form_render(self):
        self.assertEqual(self.client.get(reverse("financial:monthly_report")).status_code, 200)
        response = self.client.get(reverse("accounts:bankaccount_update", args=[self.acct.pk]))
        self.assertContains(response, "Saldo inicial")


class RedesignPagesTests(TestCase):
    """Telas novas e o comportamento comum dos modais (HTMX)."""

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("ana", password="x"))
        self.cat = Category.objects.create(name="Casa", type="EXPENSE")
        self.acct = BankAccount.objects.create(name="Inter", bank="Inter")
        self.card = PaymentMethod.objects.create(name="Visa", type="CREDIT", bank_account=self.acct,
                                                 closing_day=27, due_day=10)
        self.purchase = Purchase.objects.create(description="Sofá", total_amount=Decimal("600"),
                                                purchase_date=date.today(), number_of_installments=3,
                                                category=self.cat, payment_method=self.card)

    def test_new_pages_render(self):
        for name in ("financial:transfer_list", "financial:cards", "financial:third_party", "core:family_list",
                     "accounts:bankaccount_list", "accounts:paymentmethod_list", "financial:recurrence_list"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_invalid_modal_form_comes_back_into_the_modal(self):
        response = self.client.post(reverse("financial:transaction_create"), {"_after": "table"},
                                    HTTP_HX_REQUEST="true")
        self.assertEqual(response["HX-Retarget"], "#modal-container")
        self.assertContains(response, "fld-error")

    def test_deleting_a_category_in_use_returns_a_warning(self):
        response = self.client.delete(reverse("core:category_delete", args=[self.cat.pk]), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Category.objects.filter(pk=self.cat.pk).exists())

    def test_invoice_payment_marks_installments_paid(self):
        first = self.purchase.installments.order_by("installment_number").first()
        response = self.client.post(reverse("financial:transfer_create"), {
            "date": date.today().isoformat(), "amount": "200.00", "from_account": self.acct.pk,
            "to_card": self.card.pk, "invoice": f"{first.reference_year}-{first.reference_month:02d}",
            "_after": "table"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        self.assertTrue(first.paid)

    def test_snapshot_on_the_same_day_replaces_the_previous_one(self):
        url = reverse("accounts:snapshot_create")
        for value in ("100.00", "250.00"):
            self.client.post(url, {"account": self.acct.pk, "date": date.today().isoformat(), "balance": value,
                                   "_after": "table"}, HTTP_HX_REQUEST="true")
        snapshots = BalanceSnapshot.objects.filter(account=self.acct, date=date.today())
        self.assertEqual(snapshots.count(), 1)
        self.assertEqual(snapshots.get().balance, Decimal("250.00"))
