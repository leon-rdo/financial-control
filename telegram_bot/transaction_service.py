from core.models import Category
from financial.models import Purchase, Transaction

from .models import PendingTransaction


def _get_fallback_category():
    """Retorna categoria 'Outros' como fallback, criando se necessário."""
    cat, _ = Category.objects.get_or_create(
        name="Outros",
        defaults={"type": "BOTH", "active": True},
    )
    return cat


def create_from_pending(pending_id):
    """Cria Transaction ou Purchase a partir de um PendingTransaction."""
    pending = PendingTransaction.objects.get(pk=pending_id)

    if pending.status != "pending":
        return None

    if not pending.payment_method:
        return {"error": "payment_method_required"}

    category = pending.category or _get_fallback_category()

    if pending.number_of_installments > 1:
        purchase = Purchase.objects.create(
            description=pending.description,
            total_amount=pending.amount,
            purchase_date=pending.date,
            number_of_installments=pending.number_of_installments,
            category=category,
            payment_method=pending.payment_method,
            entity=pending.entity,
        )
        pending.status = "confirmed"
        pending.save()
        return {
            "type": "purchase",
            "id": purchase.pk,
            "installments": pending.number_of_installments,
        }
    else:
        tx_type = pending.transaction_type
        if tx_type == "PURCHASE":
            tx_type = "EXPENSE"

        transaction = Transaction.objects.create(
            type=tx_type,
            description=pending.description,
            amount=pending.amount,
            date=pending.date,
            category=category,
            payment_method=pending.payment_method,
            entity=pending.entity,
            confirmed=True,
        )
        pending.status = "confirmed"
        pending.save()
        return {"type": "transaction", "id": transaction.pk}
