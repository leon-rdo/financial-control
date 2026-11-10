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
