import calendar
import logging
from datetime import timedelta

from django.db.models import Q

from financial.models import Recurrence, Transaction

logger = logging.getLogger(__name__)


def generate_transactions_for_date(reference_date, dry_run=False):
    """
    Generate transactions from active recurrences for the given reference date.
    Returns the count of transactions created.
    """
    recurrences = Recurrence.objects.filter(
        active=True,
        start_date__lte=reference_date,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=reference_date))

    created = 0

    for rec in recurrences:
        if rec.frequency == Recurrence.FrequencyChoices.MONTHLY:
            exists = Transaction.objects.filter(
                recurrence=rec,
                date__year=reference_date.year,
                date__month=reference_date.month,
            ).exists()
            if exists:
                continue

            last_day = calendar.monthrange(reference_date.year, reference_date.month)[1]
            day = min(rec.reference_day, last_day)
            tx_date = reference_date.replace(day=day)

        elif rec.frequency == Recurrence.FrequencyChoices.WEEKLY:
            iso_year, iso_week, _ = reference_date.isocalendar()
            exists = Transaction.objects.filter(
                recurrence=rec,
                date__week=iso_week,
                date__iso_year=iso_year,
            ).exists()
            if exists:
                continue

            # reference_day: 1=Monday to 7=Sunday
            current_weekday = reference_date.isoweekday()
            target_weekday = min(max(rec.reference_day, 1), 7)
            tx_date = reference_date + timedelta(days=target_weekday - current_weekday)

        elif rec.frequency == Recurrence.FrequencyChoices.YEARLY:
            exists = Transaction.objects.filter(
                recurrence=rec,
                date__year=reference_date.year,
            ).exists()
            if exists:
                continue

            tx_date = reference_date

        elif rec.frequency == Recurrence.FrequencyChoices.CUSTOM:
            logger.warning(
                "Recurrence %s (%s) has CUSTOM frequency, skipping.",
                rec.pk,
                rec.description,
            )
            continue
        else:
            continue

        if dry_run:
            logger.info(
                "[DRY-RUN] Would create: %s - R$ %s on %s",
                rec.description,
                rec.amount,
                tx_date,
            )
        else:
            Transaction.objects.create(
                type=rec.type,
                description=rec.description,
                amount=rec.amount,
                date=tx_date,
                category=rec.category,
                payment_method=rec.payment_method,
                entity=rec.entity,
                confirmed=False,
                recurrence=rec,
            )

        created += 1

    return created
