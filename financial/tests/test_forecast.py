from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import PaymentMethod
from core.models import Category
from financial import forecast
from accounts.models import BalanceSnapshot, BankAccount
from financial.models import Purchase, Recurrence, Transaction, Transfer


def card(closing=None, due=None, name="Cartão"):
    return PaymentMethod.objects.create(name=name, type="CREDIT", closing_day=closing, due_day=due)


class InvoicePeriodTests(TestCase):
    def test_without_closing_day_keeps_old_behaviour(self):
        pm = card(closing=None, due=10)
        p = forecast.invoice_period_for(pm, date(2026, 3, 15))
        self.assertEqual((p.year, p.month, p.due_date), (2026, 3, date(2026, 3, 15)))

    def test_purchase_before_closing_goes_to_current_invoice(self):
        pm = card(closing=3, due=10)
        p = forecast.invoice_period_for(pm, date(2026, 3, 2))
        self.assertEqual(p.due_date, date(2026, 3, 10))

    def test_purchase_on_closing_day_goes_to_next_invoice(self):
        pm = card(closing=3, due=10)
        p = forecast.invoice_period_for(pm, date(2026, 3, 3))
        self.assertEqual(p.due_date, date(2026, 4, 10))

    def test_due_day_before_closing_day_is_next_month(self):
        pm = card(closing=25, due=5)
        self.assertEqual(forecast.invoice_period_for(pm, date(2026, 3, 10)).due_date, date(2026, 4, 5))
        self.assertEqual(forecast.invoice_period_for(pm, date(2026, 3, 26)).due_date, date(2026, 5, 5))

    def test_closing_day_clamped_to_month_end(self):
        pm = card(closing=31, due=8)
        # fevereiro fecha dia 28: compra no dia 28 já vai para a fatura seguinte
        self.assertEqual(forecast.invoice_period_for(pm, date(2026, 2, 28)).due_date, date(2026, 4, 8))

    def test_non_credit_method_uses_date(self):
        pix = PaymentMethod.objects.create(name="Pix", type="PIX")
        self.assertEqual(forecast.invoice_period_for(pix, date(2026, 5, 9)).due_date, date(2026, 5, 9))


class InstallmentGenerationTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Teste", type="EXPENSE")

    def make(self, pm, total="100.00", n=3, when=date(2026, 1, 15), **extra):
        return Purchase.objects.create(description="TV", total_amount=Decimal(total), purchase_date=when,
                                       number_of_installments=n, category=self.cat, payment_method=pm, **extra)

    def test_rounding_last_installment_absorbs_cents(self):
        p = self.make(card())
        amounts = list(p.installments.order_by("installment_number").values_list("amount", flat=True))
        self.assertEqual(amounts, [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])
        self.assertEqual(sum(amounts), Decimal("100.00"))

    def test_fallback_matches_old_dates(self):
        p = self.make(card(closing=None, due=10), when=date(2026, 1, 31))
        dues = list(p.installments.order_by("installment_number").values_list("due_date", flat=True))
        self.assertEqual(dues, [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)])

    def test_uses_card_closing_and_due_days(self):
        p = self.make(card(closing=3, due=10), when=date(2026, 1, 15))
        inst = list(p.installments.order_by("installment_number"))
        self.assertEqual([i.due_date for i in inst], [date(2026, 2, 10), date(2026, 3, 10), date(2026, 4, 10)])
        self.assertEqual([(i.reference_year, i.reference_month) for i in inst], [(2026, 2), (2026, 3), (2026, 4)])

    def test_first_invoice_month_overrides(self):
        p = self.make(card(due=12), first_invoice_month=date(2025, 11, 1))
        self.assertEqual(p.installments.get(installment_number=1).due_date, date(2025, 11, 12))

    def test_regenerate_preserves_paid_flags(self):
        p = self.make(card(), n=4)
        p.installments.filter(installment_number__in=[1, 2]).update(paid=True)
        p.number_of_installments = 5
        p.save()
        p.generate_installments()
        paid = set(p.installments.filter(paid=True).values_list("installment_number", flat=True))
        self.assertEqual(paid, {1, 2})
        self.assertEqual(p.installments.count(), 5)


class RecurrenceOccurrenceTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Assinaturas", type="EXPENSE")
        self.pm = card(closing=3, due=10)

    def rec(self, **kw):
        defaults = dict(description="Netflix", amount=Decimal("39.90"), type="EXPENSE", category=self.cat,
                        payment_method=self.pm, frequency="MONTHLY", reference_day=31,
                        start_date=date(2026, 1, 1))
        defaults.update(kw)
        return Recurrence.objects.create(**defaults)

    def test_monthly_clamps_day(self):
        dates = forecast.recurrence_occurrences(self.rec(), date(2026, 1, 1), date(2026, 3, 31))
        self.assertEqual(dates, [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)])

    def test_yearly_uses_reference_day(self):
        r = self.rec(frequency="YEARLY", reference_day=20, start_date=date(2025, 6, 1))
        self.assertEqual(forecast.recurrence_occurrences(r, date(2026, 1, 1), date(2026, 12, 31)),
                         [date(2026, 6, 20)])

    def test_projection_skips_generated_periods(self):
        r = self.rec(reference_day=5)
        Transaction.objects.create(type="EXPENSE", description="Netflix", amount=Decimal("39.90"),
                                   date=date(2026, 2, 5), category=self.cat, payment_method=self.pm, recurrence=r)
        projected = [d for _, d in forecast.projected_recurrences(date(2026, 1, 1), date(2026, 3, 31))]
        self.assertEqual(projected, [date(2026, 1, 5), date(2026, 3, 5)])


class InvoiceForecastTests(TestCase):
    def test_sums_installments_and_single_credit_purchases(self):
        cat = Category.objects.create(name="Compras", type="EXPENSE")
        pm = card(closing=3, due=10)
        Purchase.objects.create(description="TV", total_amount=Decimal("300"), purchase_date=date(2026, 1, 15),
                                number_of_installments=3, category=cat, payment_method=pm)
        Transaction.objects.create(type="EXPENSE", description="Mercado", amount=Decimal("50"),
                                   date=date(2026, 1, 20), category=cat, payment_method=pm, confirmed=True)
        months = forecast.invoice_forecast((2026, 2), (2026, 4), today=date(2026, 1, 25))
        totals = {(m["year"], m["month"]): m["total"] for m in months}
        self.assertEqual(totals[(2026, 2)], Decimal("150.00"))  # parcela 1 + mercado
        self.assertEqual(totals[(2026, 3)], Decimal("100.00"))
        self.assertEqual(totals[(2026, 4)], Decimal("100.00"))


class PaidInvoiceTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Compras", type="EXPENSE")
        self.pm = card(closing=3, due=10)
        Transaction.objects.create(type="EXPENSE", description="Mercado", amount=Decimal("50"),
                                   date=date(2026, 1, 20), category=self.cat, payment_method=self.pm, confirmed=True)

    def total(self, **kw):
        months = forecast.invoice_forecast((2026, 2), (2026, 2), **kw)
        return months[0]["total"] if months else Decimal("0")

    def test_single_purchases_drop_out_when_invoice_is_paid_or_past(self):
        self.assertEqual(self.total(today=date(2026, 2, 1)), Decimal("50"))
        self.assertEqual(self.total(today=date(2026, 3, 1)), Decimal("0"))  # mês passado: histórico
        self.assertEqual(self.total(today=date(2026, 3, 1), include_paid=True), Decimal("50"))
        Transfer.objects.create(date=date(2026, 2, 10), amount=Decimal("50"), to_card=self.pm,
                                invoice_year=2026, invoice_month=2)
        self.assertEqual(self.total(today=date(2026, 2, 1)), Decimal("0"))

    def test_refund_reduces_invoice(self):
        refunds = Category.objects.create(name=forecast.REFUND_CATEGORY_NAME, type="BOTH")
        Transaction.objects.create(type="INCOME", description="Estorno", amount=Decimal("20"),
                                   date=date(2026, 1, 22), category=refunds, payment_method=self.pm, confirmed=True)
        self.assertEqual(self.total(today=date(2026, 2, 1)), Decimal("30"))


class BalanceTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Geral", type="BOTH")
        self.acct = BankAccount.objects.create(name="Inter", bank="Inter")
        self.pix = PaymentMethod.objects.create(name="Pix", type="PIX", bank_account=self.acct)
        self.card = PaymentMethod.objects.create(name="Cartão", type="CREDIT", bank_account=self.acct,
                                                 closing_day=3, due_day=10)

    def tx(self, type_, amount, when, pm=None, confirmed=True, **kw):
        return Transaction.objects.create(type=type_, description="x", amount=Decimal(amount), date=when,
                                          category=self.cat, payment_method=pm or self.pix,
                                          confirmed=confirmed, **kw)

    def test_balance_from_snapshot_ignores_credit_and_older_movements(self):
        self.tx("INCOME", "1000", date(2026, 10, 1))             # antes do snapshot: já está no saldo
        BalanceSnapshot.objects.create(account=self.acct, date=date(2026, 10, 31), balance=Decimal("800"))
        self.tx("EXPENSE", "100", date(2026, 11, 2))
        self.tx("EXPENSE", "999", date(2026, 11, 2), pm=self.card)  # cartão não sai da conta
        self.tx("EXPENSE", "50", date(2026, 11, 3), confirmed=False)
        Transfer.objects.create(date=date(2026, 11, 10), amount=Decimal("300"), from_account=self.acct,
                                to_card=self.card)
        result = forecast.account_balances(date(2026, 11, 30))
        self.assertEqual(result["total"], Decimal("400"))
        self.assertEqual(forecast.account_balances(date(2026, 11, 5))["total"], Decimal("700"))

    def test_account_without_anchor_is_flagged(self):
        result = forecast.account_balances(date(2026, 11, 30))
        self.assertFalse(result["all_anchored"])
        self.assertIsNone(result["accounts"][0]["anchor"])

    def test_cash_flow_projection(self):
        today = date(2026, 11, 10)
        BalanceSnapshot.objects.create(account=self.acct, date=date(2026, 11, 9), balance=Decimal("1000"))
        Recurrence.objects.create(description="Salário", amount=Decimal("5000"), type="INCOME", category=self.cat,
                                  payment_method=self.pix, frequency="MONTHLY", reference_day=5,
                                  start_date=date(2026, 1, 1))
        Recurrence.objects.create(description="Aluguel", amount=Decimal("2000"), type="EXPENSE", category=self.cat,
                                  payment_method=self.pix, frequency="MONTHLY", reference_day=15,
                                  start_date=date(2026, 1, 1))
        self.tx("EXPENSE", "600", date(2026, 11, 20), pm=self.card)  # fatura que vence em 10/12
        self.tx("EXPENSE", "150", date(2026, 11, 25), confirmed=False)  # boleto previsto

        flow = forecast.monthly_cash_flow(1, today=today)
        nov, dec = flow["months"]
        self.assertEqual(flow["start_balance"], Decimal("1000"))
        # novembro: salário do dia 5 já passou; aluguel e boleto ainda vêm
        self.assertEqual((nov["expected_income"], nov["expected_expenses"], nov["card_invoices"]),
                         (Decimal("0"), Decimal("2150"), Decimal("0")))
        self.assertEqual(nov["projected_end_balance"], Decimal("-1150"))
        self.assertEqual((dec["expected_income"], dec["expected_expenses"], dec["card_invoices"]),
                         (Decimal("5000"), Decimal("2000"), Decimal("600")))
        self.assertEqual(dec["projected_end_balance"], Decimal("1250"))
