import json


def inline_keyboard(buttons_rows):
    """Cria InlineKeyboardMarkup como dict para enviar via API."""
    return {
        "inline_keyboard": [
            [
                {"text": btn["text"], "callback_data": btn["data"]}
                for btn in row
            ]
            for row in buttons_rows
        ]
    }


def confirmation_keyboard(
    pending_id,
    show_create_entity=False,
    entity_name="",
    show_create_category=False,
    category_hint="",
    show_create_payment=False,
    payment_hint="",
):
    """Teclado de Confirmar / Editar / Cancelar, com botões opcionais de criação."""
    rows = [
        [
            {"text": "✅ Confirmar", "data": json.dumps({"a": "confirm", "id": pending_id})},
            {"text": "❌ Cancelar", "data": json.dumps({"a": "cancel", "id": pending_id})},
        ],
        [
            {"text": "✏️ Editar", "data": json.dumps({"a": "edit", "id": pending_id})},
        ],
    ]
    if show_create_payment and payment_hint:
        short_hint = payment_hint[:25]
        rows.insert(1, [
            {
                "text": f"💳 Criar pagamento: {short_hint}",
                "data": json.dumps({"a": "create_pay", "id": pending_id}),
            },
        ])
    if show_create_category and category_hint:
        short_hint = category_hint[:30]
        rows.insert(1, [
            {
                "text": f"📂 Criar categoria: {short_hint}",
                "data": json.dumps({"a": "create_cat", "id": pending_id}),
            },
        ])
    if show_create_entity and entity_name:
        short_name = entity_name[:30]
        rows.insert(1, [
            {
                "text": f"➕ Criar: {short_name}",
                "data": json.dumps({"a": "create_ent", "id": pending_id}),
            },
        ])
    return inline_keyboard(rows)


def edit_field_keyboard(pending_id):
    """Teclado para escolher qual campo editar."""
    fields = [
        ("Descrição", "desc"),
        ("Valor", "amount"),
        ("Data", "date"),
        ("Categoria", "cat"),
        ("Pagamento", "pay"),
        ("Parcelas", "inst"),
    ]
    rows = []
    for i in range(0, len(fields), 2):
        row = []
        for label, field in fields[i : i + 2]:
            row.append(
                {
                    "text": label,
                    "data": json.dumps({"a": "edit_field", "id": pending_id, "f": field}),
                }
            )
        rows.append(row)
    rows.append(
        [{"text": "⬅️ Voltar", "data": json.dumps({"a": "back", "id": pending_id})}]
    )
    return inline_keyboard(rows)


def options_keyboard(pending_id, field, options):
    """Teclado com lista de opções (categoria, pagamento)."""
    rows = []
    for opt in options[:20]:
        rows.append(
            [
                {
                    "text": opt["name"],
                    "data": json.dumps(
                        {"a": "set", "id": pending_id, "f": field, "v": opt["id"]}
                    ),
                }
            ]
        )
    rows.append(
        [{"text": "⬅️ Voltar", "data": json.dumps({"a": "edit", "id": pending_id})}]
    )
    return inline_keyboard(rows)
