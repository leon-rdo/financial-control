import logging

from accounts.models import PaymentMethod
from core.models import Category, Entity

logger = logging.getLogger(__name__)


def match_category(ai_data):
    """Resolve categoria: primeiro por ID direto, depois por hint."""
    # Tenta ID direto (retornado pela IA com contexto do banco)
    cat_id = ai_data.get("category_id")
    if cat_id:
        try:
            return Category.objects.get(pk=int(cat_id), active=True)
        except (Category.DoesNotExist, ValueError, TypeError):
            pass

    # Fallback: busca por hint textual
    hint = ai_data.get("category_hint")
    if not hint:
        return None

    qs = Category.objects.filter(active=True, name__icontains=hint)
    if qs.exists():
        return qs.first()

    # Tenta primeira palavra
    first_word = hint.split()[0] if hint else ""
    if first_word and len(first_word) > 2:
        qs = Category.objects.filter(active=True, name__icontains=first_word)
        if qs.exists():
            return qs.first()

    return None


def _resolve_payment_type(hint):
    """Converte hint textual para tipo de PaymentMethod."""
    if not hint:
        return None
    type_map = {
        "PIX": "PIX",
        "CREDITO": "CREDIT", "CRÉDITO": "CREDIT", "CREDIT": "CREDIT",
        "CARTAO": "CREDIT", "CARTÃO": "CREDIT",
        "DEBITO": "DEBIT", "DÉBITO": "DEBIT", "DEBIT": "DEBIT",
        "DINHEIRO": "CASH", "CASH": "CASH",
        "TRANSFERENCIA": "TRANSFER", "TRANSFERÊNCIA": "TRANSFER",
        "TRANSFER": "TRANSFER", "TED": "TRANSFER", "DOC": "TRANSFER",
        "BOLETO": "BOLETO",
    }
    return type_map.get(hint.upper(), hint.upper())


def match_payment_method(ai_data):
    """Resolve método de pagamento: por ID (validado), por instituição de origem, ou por tipo."""
    hint = ai_data.get("payment_type_hint", "")
    expected_type = _resolve_payment_type(hint)
    source = ai_data.get("source_institution") or ""

    # Tenta ID direto, mas valida se o tipo bate com o hint
    pm_id = ai_data.get("payment_method_id")
    if pm_id:
        try:
            pm = PaymentMethod.objects.get(pk=int(pm_id), active=True)
            if not expected_type or pm.type == expected_type:
                return pm
            logger.warning(
                "payment_method_id=%s tipo=%s não bate com hint=%s, ignorando",
                pm_id, pm.type, hint,
            )
        except (PaymentMethod.DoesNotExist, ValueError, TypeError):
            pass

    # Busca por nome da instituição de origem + tipo esperado
    if source and expected_type:
        for word in source.split():
            if len(word) > 2:
                qs = PaymentMethod.objects.filter(
                    active=True, type=expected_type, name__icontains=word,
                )
                if qs.exists():
                    return qs.first()

    # Busca por nome da instituição de origem (qualquer tipo)
    if source:
        for word in source.split():
            if len(word) > 2:
                qs = PaymentMethod.objects.filter(active=True, name__icontains=word)
                if qs.exists():
                    return qs.first()

    # Busca por tipo esperado
    if expected_type:
        qs = PaymentMethod.objects.filter(active=True, type=expected_type)
        if qs.exists():
            return qs.first()

    return None


def match_entity(ai_data):
    """Resolve entidade: primeiro por ID direto, depois por nome."""
    ent_id = ai_data.get("entity_id")
    if ent_id:
        try:
            return Entity.objects.get(pk=int(ent_id), active=True)
        except (Entity.DoesNotExist, ValueError, TypeError):
            pass

    # Fallback: busca por nome
    name = ai_data.get("entity_name")
    if not name:
        return None

    qs = Entity.objects.filter(active=True, name__icontains=name)
    if qs.exists():
        return qs.first()

    # Tenta primeira palavra significativa (>3 chars)
    for word in name.split():
        if len(word) > 3:
            qs = Entity.objects.filter(active=True, name__icontains=word)
            if qs.exists():
                return qs.first()

    return None


def resolve_pending_data(ai_data):
    """Resolve os dados da IA para objetos do banco."""
    return {
        "category": match_category(ai_data),
        "payment_method": match_payment_method(ai_data),
        "entity": match_entity(ai_data),
    }
