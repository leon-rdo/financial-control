from django.db.models import Q


def get_page_number(qs, obj, per_page):
    """
    Retorna (int) o número da página onde `obj` aparece em `qs` já ordenado.
    """
    order_fields = qs.query.order_by
    if not order_fields:
        raise ValueError(
            "O queryset precisa estar ordenado antes de chamar get_page_number()."
        )

    # pega o primeiro critério de ordenação
    primary = order_fields[0]
    desc = primary.startswith("-")
    field = primary.lstrip("-")
    val = getattr(obj, field)

    # conta quantos itens vêm antes de obj (tie‑break por pk)
    lookup = f"{field}__{'gt' if desc else 'lt'}"
    cond = Q(**{lookup: val}) | (Q(**{field: val}) & Q(pk__lte=obj.pk))
    idx = qs.filter(cond).count()  # posição de obj na lista

    # converte posição em página (1‑based)
    return (idx - 1) // per_page + 1
