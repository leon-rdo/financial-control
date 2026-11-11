"""Fechamentos reais de fatura: corrigem a estimativa feita pelo dia de fechamento."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import PaymentMethod
from core.models import Category
from financial import forecast
from financial.models import InvoiceClosing, Transaction


class RealClosingTests(TestCase):
    def setUp(self):
        self.card = PaymentMethod.objects.create(name="Cartão", type="CREDIT", closing_day=3, due_day=10)
        self.cat = Category.objects.create(name="Mercado", type="EXPENSE")

    def closing(self, year, month, closing, due=None):
        return InvoiceClosing.objects.create(card=self.card, year=year, month=month, closing_date=closing,
                                             due_date=due)

    def period(self, d, card=None):
        p = forecast.invoice_period_for(card or self.card, d)
        return (p.year, p.month, p.due_date)

    def test_without_known_closings_estimate_is_unchanged(self):
        self.assertEqual(self.period(date(2026, 12, 2)), (2026, 12, date(2026, 12, 10)))
        self.assertEqual(self.period(date(2026, 12, 3)), (2027, 1, date(2027, 1, 10)))

    def test_bank_closed_earlier_than_the_estimate(self):
        # a fatura de 10/12 fechou em 01/12 (estimativa: 03/12): compra de 02/12 já é da fatura de janeiro
        self.closing(2026, 12, date(2026, 12, 1), date(2026, 12, 10))
        self.assertEqual(self.period(date(2026, 12, 2)), (2027, 1, date(2027, 1, 10)))
        self.assertEqual(self.period(date(2026, 11, 30)), (2026, 12, date(2026, 12, 10)))

    def test_bank_closed_later_than_the_estimate(self):
        # a fatura de 10/12 fechou em 05/12 (estimativa: 03/12): compra de 04/12 ainda é desta fatura
        self.closing(2026, 12, date(2026, 12, 5), date(2026, 12, 10))
        self.assertEqual(self.period(date(2026, 12, 4)), (2026, 12, date(2026, 12, 10)))
        self.assertEqual(self.period(date(2026, 12, 5)), (2027, 1, date(2027, 1, 10)))

    def test_previous_closing_pulls_purchase_back(self):
        # fatura de 10/01 fechou em 05/01; compra de 04/01 (estimativa: fatura de fevereiro) é de janeiro
        self.closing(2027, 1, date(2027, 1, 5))
        self.assertEqual(self.period(date(2027, 1, 4)), (2027, 1, date(2027, 1, 10)))
        self.assertEqual(self.period(date(2027, 1, 5)), (2027, 2, date(2027, 2, 10)))

    def test_real_due_date_wins(self):
        self.closing(2026, 12, date(2026, 12, 3), date(2026, 12, 12))  # vencimento deslocado
        self.assertEqual(self.period(date(2026, 12, 1)), (2026, 12, date(2026, 12, 12)))

    def test_other_cards_and_additional_cards(self):
        other = PaymentMethod.objects.create(name="Outro", type="CREDIT", closing_day=3, due_day=10)
        extra = PaymentMethod.objects.create(name="Adicional", type="CREDIT", billing_card=self.card)
        self.closing(2026, 12, date(2026, 12, 1), date(2026, 12, 10))
        self.assertEqual(self.period(date(2026, 12, 2), other), (2026, 12, date(2026, 12, 10)))   # não afetado
        self.assertEqual(self.period(date(2026, 12, 2), extra), (2027, 1, date(2027, 1, 10)))     # segue o principal

    def test_card_without_closing_day_uses_imported_invoices(self):
        bare = PaymentMethod.objects.create(name="Sem dia", type="CREDIT")
        InvoiceClosing.objects.create(card=bare, year=2026, month=12, closing_date=date(2026, 12, 3),
                                      due_date=date(2026, 12, 10))
        self.assertEqual(self.period(date(2026, 12, 2), bare), (2026, 12, date(2026, 12, 10)))
        self.assertEqual(self.period(date(2026, 12, 4), bare), (2027, 1, date(2027, 1, 10)))

    def test_forecast_moves_unstamped_purchase_to_the_real_invoice(self):
        Transaction.objects.create(type="EXPENSE", description="Compra", amount=Decimal("80"), date=date(2026, 12, 2),
                                   category=self.cat, payment_method=self.card, confirmed=True)

        def invoices(**kw):
            return {(b["year"], b["month"]): b["total"]
                    for b in forecast.invoice_forecast((2026, 12), (2027, 1), today=date(2026, 12, 20), **kw)}

        self.assertEqual(invoices(), {(2026, 12): Decimal("80")})        # estimativa: fatura de dezembro
        self.closing(2026, 12, date(2026, 12, 1), date(2026, 12, 10))
        self.assertEqual(invoices(), {(2027, 1): Decimal("80")})         # fechamento real: janeiro
