import base64
import json
import logging
from datetime import date

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Você é um assistente financeiro. Sua ÚNICA tarefa: extrair dados de comprovantes e retornar JSON.

DATA DE HOJE: {today}

{context_data}

EXTRAIA estes campos em JSON:
- type: "EXPENSE", "INCOME", ou "PURCHASE" (PURCHASE = parcelado com mais de 1 parcela)
- description: descrição curta baseada no DESTINATÁRIO (ex: "Internet Predlink")
- amount: valor como string decimal com ponto (ex: "146.52")
- date: data no formato YYYY-MM-DD (leia do comprovante; se ilegível use {today})
- entity_name: nome do DESTINATÁRIO. Em PIX = campo "Para". NUNCA use "De" (quem pagou).
- source_institution: nome da instituição/banco de ORIGEM do pagamento (campo "De", ex: "Mercado Pago", "Nubank", "Banco Inter"). Se não identificável, use null.
- category_id: ID da lista acima, ou null. PROIBIDO inventar IDs.
- payment_method_id: ID da lista acima que melhor corresponda à ORIGEM do pagamento. Ex: se pagou via "Mercado Pago", busque um método com "Mercado Pago" no nome. Se for PIX, busque método de Tipo=PIX. PROIBIDO inventar IDs. Se não souber, use null.
- entity_id: ID da lista acima se existir, ou null.
- payment_type_hint: "PIX", "CREDIT", "DEBIT", "CASH", "TRANSFER" ou "BOLETO"
- category_hint: sugestão de nome se category_id for null
- installments: número de parcelas (1 se à vista)

REGRAS CRÍTICAS (SEGUIR À RISCA):
1. "Comprovante de Pix" ou "Pix enviado" = tipo PIX. O payment_method_id DEVE ser um ID de Tipo=PIX da lista acima. IGNORE qualquer número de cartão que apareça no comprovante PIX.
2. "De" / "Origem" = quem PAGOU (ex: "Leonardo", "Mercado Pago"). NÃO é a entidade.
3. "Para" / "Destino" / "Favorecido" = DESTINATÁRIO = entity_name.
4. Escolha a categoria pelo RAMO DO DESTINATÁRIO: telecomunicações/internet/provedor → busque categoria de internet ou serviços. Restaurante → alimentação. Farmácia → saúde. NÃO use "Alimentação" para tudo.
5. LEIA a data com cuidado. Meses em português: janeiro=01, fevereiro=02, março=03, abril=04, maio=05, junho=06, julho=07, agosto=08, setembro=09, outubro=10, novembro=11, dezembro=12. "10/março/2026" = "2026-03-10".
6. category_id e payment_method_id DEVEM existir na lista fornecida. Se não souber, use null.

Responda APENAS com JSON válido, sem texto adicional."""


def _build_context_data():
    """Carrega categorias, métodos de pagamento e entidades do banco para o prompt."""
    from accounts.models import PaymentMethod
    from core.models import Category, Entity

    categories = list(
        Category.objects.filter(active=True).values("id", "name", "type")
    )
    payment_methods = list(
        PaymentMethod.objects.filter(active=True).values("id", "name", "type")
    )
    entities = list(
        Entity.objects.filter(active=True).values("id", "name")[:50]
    )

    lines = []
    lines.append("=== CATEGORIAS DISPONÍVEIS ===")
    for c in categories:
        lines.append(f"  ID={c['id']} | Nome: {c['name']} | Tipo: {c['type']}")

    lines.append("\n=== MÉTODOS DE PAGAMENTO DISPONÍVEIS ===")
    for p in payment_methods:
        lines.append(f"  ID={p['id']} | Nome: {p['name']} | Tipo: {p['type']}")

    lines.append("\n=== ENTIDADES CADASTRADAS ===")
    if entities:
        for e in entities:
            lines.append(f"  ID={e['id']} | Nome: {e['name']}")
    else:
        lines.append("  (nenhuma cadastrada)")

    return "\n".join(lines)


def _fix_pix_payment(data):
    """Corrige payment_type_hint quando a IA não detecta PIX corretamente."""
    pix_keywords = ["pix", "comprovante de pix", "pix enviado", "pix recebido"]
    desc = (data.get("description") or "").lower()
    entity = (data.get("entity_name") or "").lower()
    hint = (data.get("payment_type_hint") or "").upper()

    # Se já é PIX, nada a fazer
    if hint == "PIX":
        return

    # Checa se há indicadores de PIX na resposta da IA
    all_text = f"{desc} {entity} {json.dumps(data).lower()}"
    is_pix = any(kw in all_text for kw in pix_keywords)

    if is_pix:
        logger.info("Pós-correção: detectado PIX, sobrescrevendo hint=%s", hint)
        data["payment_type_hint"] = "PIX"
        # Limpa payment_method_id que provavelmente é de cartão
        data["payment_method_id"] = None


def extract_transaction_data(image_bytes=None, text=None):
    """Extrai dados de transação usando GPT-4o-mini com visão ou texto."""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    today = date.today().isoformat()
    context_data = _build_context_data()
    system_content = SYSTEM_PROMPT_TEMPLATE.format(today=today, context_data=context_data)

    messages = [{"role": "system", "content": system_content}]

    user_content = []
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
            }
        )
        user_content.append(
            {
                "type": "text",
                "text": f"Analise este comprovante e extraia os dados. Data de hoje: {today}",
            }
        )
    elif text:
        today = date.today().isoformat()
        user_content.append(
            {
                "type": "text",
                "text": f"Extraia os dados desta mensagem (data de hoje: {today}): {text}",
            }
        )
    else:
        return None

    messages.append({"role": "user", "content": user_content})

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.1,
        )

        content = response.choices[0].message.content
        logger.info("OpenAI response: %s", content)
        data = json.loads(content)

        # Normalizar campos
        data.setdefault("type", "EXPENSE")
        data.setdefault("description", "Transação")
        data.setdefault("amount", "0")
        data.setdefault("date", date.today().isoformat())
        data.setdefault("entity_name", None)
        data.setdefault("source_institution", None)
        data.setdefault("category_id", None)
        data.setdefault("payment_method_id", None)
        data.setdefault("entity_id", None)
        data.setdefault("category_hint", None)
        data.setdefault("payment_type_hint", "PIX")
        data.setdefault("installments", 1)

        # Garantir tipos corretos
        data["amount"] = str(data["amount"]).replace(",", ".")
        data["installments"] = int(data.get("installments", 1) or 1)

        # Pós-correção: detectar PIX por palavras-chave na descrição da IA
        _fix_pix_payment(data)

        return data

    except Exception:
        logger.exception("Erro ao chamar OpenAI API")
        return None
