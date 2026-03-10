import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

from accounts.models import BankAccount, PaymentMethod
from core.models import Category, Entity

from .ai_service import extract_transaction_data
from .keyboards import confirmation_keyboard, edit_field_keyboard, options_keyboard
from .matching import resolve_pending_data
from .models import PendingTransaction
from .transaction_service import create_from_pending

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"


def send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    """Envia mensagem via Telegram API."""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    resp = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)
    return resp.json()


def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="Markdown"):
    """Edita mensagem existente via Telegram API."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    resp = requests.post(f"{TELEGRAM_API}/editMessageText", json=payload, timeout=10)
    return resp.json()


def answer_callback(callback_query_id, text=""):
    """Responde a callback query para remover o 'loading'."""
    requests.post(
        f"{TELEGRAM_API}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id, "text": text},
        timeout=5,
    )


def download_photo(file_id):
    """Baixa foto do Telegram e retorna bytes."""
    resp = requests.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id}, timeout=10)
    data = resp.json()
    if not data.get("ok"):
        return None
    file_path = data["result"]["file_path"]
    file_resp = requests.get(
        f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}",
        timeout=30,
    )
    return file_resp.content


def format_pending_message(pending):
    """Formata mensagem com dados da transação pendente."""
    is_purchase = pending.number_of_installments > 1

    if is_purchase:
        installment_amount = pending.amount / pending.number_of_installments
        lines = [
            "🛍️ *Compra parcelada detectada:*",
            "",
            f"*Descrição:* {pending.description}",
            f"*Valor Total:* R$ {pending.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"*Parcelas:* {pending.number_of_installments}x de R$ {installment_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        ]
    else:
        emoji = "📋" if pending.transaction_type == "EXPENSE" else "💰"
        tipo = "Despesa" if pending.transaction_type == "EXPENSE" else "Receita"
        lines = [
            f"{emoji} *Transação detectada:*",
            "",
            f"*Tipo:* {tipo}",
            f"*Descrição:* {pending.description}",
            f"*Valor:* R$ {pending.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        ]

    lines.append(f"*Data:* {pending.date.strftime('%d/%m/%Y')}")

    if pending.category:
        cat_name = pending.category.name
    elif pending.raw_ai_response.get("category_hint"):
        cat_name = f"❓ Sugestão: {pending.raw_ai_response['category_hint']}"
    else:
        cat_name = "❓ Não definida"
    if pending.payment_method:
        pay_name = pending.payment_method.name
    elif pending.raw_ai_response.get("source_institution"):
        source = pending.raw_ai_response["source_institution"]
        pay_type = pending.raw_ai_response.get("payment_type_hint", "")
        pay_name = f"❓ {source} ({pay_type}) — não cadastrado"
    else:
        pay_name = "❓ Não definido"

    if pending.entity:
        entity_display = pending.entity.name
    elif pending.raw_ai_response.get("entity_name"):
        entity_display = f"⚠️ {pending.raw_ai_response['entity_name']} (não cadastrada)"
    else:
        entity_display = "—"

    lines.extend(
        [
            f"*Categoria:* {cat_name}",
            f"*Pagamento:* {pay_name}",
            f"*Entidade:* {entity_display}",
        ]
    )

    return "\n".join(lines)


def _build_confirmation_keyboard(pending):
    """Constrói teclado de confirmação, com botões de criação se necessário."""
    needs_entity = (
        not pending.entity and pending.raw_ai_response.get("entity_name")
    )
    needs_category = (
        not pending.category and pending.raw_ai_response.get("category_hint")
    )
    needs_payment = (
        not pending.payment_method
        and pending.raw_ai_response.get("source_institution")
    )
    source = pending.raw_ai_response.get("source_institution", "")
    pay_type = pending.raw_ai_response.get("payment_type_hint", "")
    payment_hint = f"{source} ({pay_type})" if source else pay_type

    return confirmation_keyboard(
        pending.pk,
        show_create_entity=needs_entity,
        entity_name=pending.raw_ai_response.get("entity_name", ""),
        show_create_category=needs_category,
        category_hint=pending.raw_ai_response.get("category_hint", ""),
        show_create_payment=needs_payment,
        payment_hint=payment_hint,
    )


def is_allowed(chat_id):
    """Verifica se o chat_id está na lista de permitidos."""
    allowed = settings.TELEGRAM_ALLOWED_CHAT_IDS
    if not allowed:
        return True  # Se não configurado, permite todos
    allowed_ids = [int(x.strip()) for x in allowed.split(",") if x.strip()]
    return chat_id in allowed_ids


def process_update(update):
    """Processa um update do Telegram."""
    if "callback_query" in update:
        handle_callback(update["callback_query"])
        return

    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")

    if not chat_id or not is_allowed(chat_id):
        return

    # Verifica se é resposta a uma edição pendente
    reply = message.get("reply_to_message")
    if reply and handle_edit_reply(chat_id, message, reply):
        return

    # Comando /start
    text = message.get("text", "")
    if text.startswith("/start"):
        send_message(
            chat_id,
            "👋 *Olá!* Envie um comprovante (foto) ou descreva a transação por texto.\n\n"
            "Exemplos:\n"
            "• Foto de comprovante PIX\n"
            "• `Almoco restaurante X, 45 reais, pix`\n"
            "• `TV Samsung 2400 reais 12x cartão nubank`",
        )
        return

    # Foto
    if message.get("photo"):
        handle_photo(chat_id, message)
        return

    # Texto
    if text and not text.startswith("/"):
        handle_text(chat_id, text)
        return


def handle_photo(chat_id, message):
    """Processa foto de comprovante."""
    send_message(chat_id, "🔍 Analisando comprovante...")

    # Pega a maior resolução
    photo = message["photo"][-1]
    file_id = photo["file_id"]

    image_bytes = download_photo(file_id)
    if not image_bytes:
        send_message(chat_id, "❌ Erro ao baixar imagem. Tente novamente.")
        return

    ai_data = extract_transaction_data(image_bytes=image_bytes)
    if not ai_data:
        send_message(chat_id, "❌ Não consegui extrair dados do comprovante. Tente enviar outra foto ou descreva por texto.")
        return

    _create_pending_and_respond(chat_id, ai_data, file_id)


def handle_text(chat_id, text):
    """Processa texto livre."""
    send_message(chat_id, "🔍 Analisando...")

    ai_data = extract_transaction_data(text=text)
    if not ai_data:
        send_message(chat_id, "❌ Não consegui entender. Tente algo como:\n`Almoco 35 reais pix`")
        return

    _create_pending_and_respond(chat_id, ai_data)


def _create_pending_and_respond(chat_id, ai_data, file_id=""):
    """Cria PendingTransaction e envia mensagem de confirmação."""
    matches = resolve_pending_data(ai_data)

    tx_type = ai_data.get("type", "EXPENSE")

    try:
        amount = Decimal(str(ai_data["amount"]))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")

    try:
        tx_date = date.fromisoformat(ai_data.get("date", ""))
    except (ValueError, TypeError):
        tx_date = date.today()

    pending = PendingTransaction.objects.create(
        telegram_chat_id=chat_id,
        transaction_type=tx_type,
        description=ai_data.get("description", "Transação")[:200],
        amount=amount,
        date=tx_date,
        number_of_installments=ai_data.get("installments", 1),
        category=matches["category"],
        payment_method=matches["payment_method"],
        entity=matches["entity"],
        raw_ai_response=ai_data,
        image_file_id=file_id,
    )

    msg_text = format_pending_message(pending)
    keyboard = _build_confirmation_keyboard(pending)
    result = send_message(chat_id, msg_text, reply_markup=keyboard)

    if result.get("ok") and result.get("result", {}).get("message_id"):
        pending.telegram_message_id = result["result"]["message_id"]
        pending.save(update_fields=["telegram_message_id"])


def handle_callback(callback_query):
    """Processa callback de botão inline."""
    cb_id = callback_query["id"]
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]

    if not is_allowed(chat_id):
        answer_callback(cb_id, "Não autorizado")
        return

    try:
        data = json.loads(callback_query["data"])
    except (json.JSONDecodeError, KeyError):
        answer_callback(cb_id, "Erro")
        return

    action = data.get("a")
    pending_id = data.get("id")

    try:
        pending = PendingTransaction.objects.get(pk=pending_id)
    except PendingTransaction.DoesNotExist:
        answer_callback(cb_id, "Transação não encontrada")
        return

    if action == "confirm":
        result = create_from_pending(pending_id)
        if not result:
            answer_callback(cb_id, "Já processada")
        elif result.get("error") == "payment_method_required":
            answer_callback(cb_id, "❌ Defina um método de pagamento antes de confirmar")
        else:
            if result["type"] == "purchase":
                msg = (
                    f"✅ *Compra cadastrada!*\n"
                    f"{pending.description}\n"
                    f"{result['installments']}x parcelas geradas"
                )
            else:
                msg = f"✅ *Transação cadastrada!*\n{pending.description} - R$ {pending.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            edit_message(chat_id, message_id, msg)
            answer_callback(cb_id)

    elif action == "cancel":
        pending.status = "cancelled"
        pending.save()
        edit_message(chat_id, message_id, "❌ *Cancelada.*")
        answer_callback(cb_id)

    elif action == "edit":
        msg_text = format_pending_message(pending)
        msg_text += "\n\n✏️ *Qual campo deseja editar?*"
        keyboard = edit_field_keyboard(pending_id)
        edit_message(chat_id, message_id, msg_text, reply_markup=keyboard)
        answer_callback(cb_id)

    elif action == "back":
        msg_text = format_pending_message(pending)
        keyboard = _build_confirmation_keyboard(pending)
        edit_message(chat_id, message_id, msg_text, reply_markup=keyboard)
        answer_callback(cb_id)

    elif action == "edit_field":
        field = data.get("f")
        _handle_edit_field(chat_id, message_id, cb_id, pending, field)

    elif action == "create_cat":
        cat_hint = pending.raw_ai_response.get("category_hint", "")
        if cat_hint and not pending.category:
            cat_type = "EXPENSE" if pending.transaction_type == "EXPENSE" else "BOTH"
            category = Category.objects.create(
                name=cat_hint[:100],
                type=cat_type,
                active=True,
            )
            pending.category = category
            pending.save(update_fields=["category"])
            msg_text = format_pending_message(pending)
            keyboard = _build_confirmation_keyboard(pending)
            edit_message(chat_id, message_id, msg_text, reply_markup=keyboard)
            answer_callback(cb_id, f"✅ Categoria '{cat_hint}' criada!")
        else:
            answer_callback(cb_id, "Categoria já associada")

    elif action == "create_pay":
        source = pending.raw_ai_response.get("source_institution", "")
        pay_type = pending.raw_ai_response.get("payment_type_hint", "PIX")
        if source and not pending.payment_method:
            # Cria conta bancária para a instituição
            bank_account, _ = BankAccount.objects.get_or_create(
                name=source[:100],
                defaults={"bank": source[:100], "type": "CHECKING", "active": True},
            )
            # Cria método de pagamento vinculado à conta
            from telegram_bot.matching import _resolve_payment_type
            pm_type = _resolve_payment_type(pay_type) or "PIX"
            pm_name = f"{source} {pay_type}".strip()[:100]
            payment_method = PaymentMethod.objects.create(
                name=pm_name,
                type=pm_type,
                bank_account=bank_account,
                active=True,
            )
            pending.payment_method = payment_method
            pending.save(update_fields=["payment_method"])
            msg_text = format_pending_message(pending)
            keyboard = _build_confirmation_keyboard(pending)
            edit_message(chat_id, message_id, msg_text, reply_markup=keyboard)
            answer_callback(cb_id, f"✅ {pm_name} criado!")
        else:
            answer_callback(cb_id, "Pagamento já associado")

    elif action == "create_ent":
        entity_name = pending.raw_ai_response.get("entity_name", "")
        if entity_name and not pending.entity:
            entity = Entity.objects.create(
                name=entity_name[:100],
                type="SUPPLIER",
                active=True,
            )
            pending.entity = entity
            pending.save(update_fields=["entity"])
            msg_text = format_pending_message(pending)
            keyboard = _build_confirmation_keyboard(pending)
            edit_message(chat_id, message_id, msg_text, reply_markup=keyboard)
            answer_callback(cb_id, f"✅ {entity_name} criada!")
        else:
            answer_callback(cb_id, "Entidade já associada")

    elif action == "set":
        field = data.get("f")
        value = data.get("v")
        _handle_set_field(chat_id, message_id, cb_id, pending, field, value)


def _handle_edit_field(chat_id, message_id, cb_id, pending, field):
    """Mostra opções para editar um campo específico."""
    if field == "cat":
        categories = Category.objects.filter(active=True).values("id", "name")
        keyboard = options_keyboard(pending.pk, "cat", list(categories))
        edit_message(chat_id, message_id, "📂 *Selecione a categoria:*", reply_markup=keyboard)
        answer_callback(cb_id)

    elif field == "pay":
        methods = PaymentMethod.objects.filter(active=True).values("id", "name")
        keyboard = options_keyboard(pending.pk, "pay", list(methods))
        edit_message(chat_id, message_id, "💳 *Selecione o pagamento:*", reply_markup=keyboard)
        answer_callback(cb_id)

    elif field in ("desc", "amount", "date", "inst"):
        labels = {
            "desc": "descrição",
            "amount": "valor (ex: 45.90)",
            "date": "data (ex: 10/03/2026)",
            "inst": "número de parcelas (ex: 12)",
        }
        msg = f"✏️ *Responda a esta mensagem* com o novo valor para *{labels[field]}*:"
        result = send_message(chat_id, msg)
        if result.get("ok"):
            # Salva contexto de edição como metadado temporário
            pending.raw_ai_response["_editing"] = {
                "field": field,
                "reply_msg_id": result["result"]["message_id"],
            }
            pending.save(update_fields=["raw_ai_response"])
        answer_callback(cb_id)


def _handle_set_field(chat_id, message_id, cb_id, pending, field, value):
    """Define o valor de um campo via botão inline."""
    if field == "cat":
        try:
            pending.category = Category.objects.get(pk=value)
            pending.save(update_fields=["category"])
        except Category.DoesNotExist:
            pass
    elif field == "pay":
        try:
            pending.payment_method = PaymentMethod.objects.get(pk=value)
            pending.save(update_fields=["payment_method"])
        except PaymentMethod.DoesNotExist:
            pass

    # Volta para tela de confirmação
    msg_text = format_pending_message(pending)
    keyboard = _build_confirmation_keyboard(pending)
    edit_message(chat_id, message_id, msg_text, reply_markup=keyboard)
    answer_callback(cb_id, "✅ Atualizado")


def handle_edit_reply(chat_id, message, reply):
    """Processa resposta do usuário a uma mensagem de edição."""
    # Busca pending com edição em andamento para este chat
    pendings = PendingTransaction.objects.filter(
        telegram_chat_id=chat_id,
        status="pending",
    ).order_by("-created_at")

    for pending in pendings[:5]:
        editing = pending.raw_ai_response.get("_editing")
        if not editing:
            continue
        if editing.get("reply_msg_id") != reply.get("message_id"):
            continue

        field = editing["field"]
        text = message.get("text", "").strip()

        if field == "desc":
            pending.description = text[:200]
            pending.save(update_fields=["description"])
        elif field == "amount":
            try:
                pending.amount = Decimal(text.replace(",", ".").replace("R$", "").strip())
                pending.save(update_fields=["amount"])
            except (InvalidOperation, ValueError):
                send_message(chat_id, "❌ Valor inválido. Tente novamente (ex: 45.90)")
                return True
        elif field == "date":
            try:
                parts = text.replace("-", "/").split("/")
                if len(parts) == 3:
                    if len(parts[0]) == 4:  # YYYY/MM/DD
                        pending.date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    else:  # DD/MM/YYYY
                        pending.date = date(int(parts[2]), int(parts[1]), int(parts[0]))
                    pending.save(update_fields=["date"])
                else:
                    send_message(chat_id, "❌ Formato inválido. Use DD/MM/AAAA")
                    return True
            except (ValueError, IndexError):
                send_message(chat_id, "❌ Data inválida. Use DD/MM/AAAA")
                return True
        elif field == "inst":
            try:
                pending.number_of_installments = max(1, int(text))
                pending.save(update_fields=["number_of_installments"])
            except ValueError:
                send_message(chat_id, "❌ Número inválido.")
                return True

        # Limpa estado de edição
        pending.raw_ai_response.pop("_editing", None)
        pending.save(update_fields=["raw_ai_response"])

        # Envia nova mensagem de confirmação
        msg_text = format_pending_message(pending)
        msg_text += "\n\n✅ _Campo atualizado!_"
        keyboard = _build_confirmation_keyboard(pending)
        send_message(chat_id, msg_text, reply_markup=keyboard)
        return True

    return False
