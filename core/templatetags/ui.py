"""Peças de interface usadas em todos os templates: valores em reais, ícones e
pequenos cálculos de apresentação."""
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html, mark_safe

register = template.Library()

MONTHS = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
          "outubro", "novembro", "dezembro"]
MONTHS_SHORT = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _dec(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _fmt(value):
    """1234.5 -> '1.234,50'."""
    q = abs(value).quantize(Decimal("0.01"))
    whole, cents = f"{q:.2f}".split(".")
    groups = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{'.'.join(groups)},{cents}"


@register.filter
def brl(value):
    """Valor em reais sem o símbolo: '1.234,56' (negativo com sinal de menos)."""
    d = _dec(value)
    if d is None:
        return "—"
    return ("−" if d < 0 else "") + _fmt(d)


@register.filter
def rs(value):
    """Valor em reais com o símbolo: 'R$ 1.234,56'."""
    d = _dec(value)
    if d is None:
        return "—"
    return ("−" if d < 0 else "") + "R$ " + _fmt(d)


@register.filter
def signed(value, kind="EXPENSE"):
    """'+1.234,56' para receita, '−1.234,56' para despesa."""
    d = _dec(value)
    if d is None:
        return "—"
    return ("+" if kind == "INCOME" else "−") + _fmt(d)


@register.filter
def short_brl(value):
    """Valor arredondado, para espaços curtos: '2.904'."""
    d = _dec(value)
    if d is None:
        return "—"
    q = abs(d).quantize(Decimal("1"))
    s = f"{q:,.0f}".replace(",", ".")
    return ("−" if d < 0 else "") + s


@register.filter
def pct(part, whole):
    """Porcentagem inteira de part sobre whole, limitada a 0..100 (para larguras)."""
    p, w = _dec(part), _dec(whole)
    if not p or not w or w <= 0:
        return 0
    return max(0, min(100, int(round(p / w * 100))))


@register.filter
def month_name(month):
    try:
        return MONTHS[int(month)]
    except (TypeError, ValueError, IndexError):
        return ""


@register.filter
def month_short(month):
    try:
        return MONTHS_SHORT[int(month)]
    except (TypeError, ValueError, IndexError):
        return ""


@register.filter
def ym_label(key):
    """'2026-11' -> 'nov/26'."""
    try:
        y, m = (int(p) for p in str(key).split("-"))
    except ValueError:
        return key
    return f"{MONTHS_SHORT[m]}/{y % 100:02d}"


@register.filter
def get_item(mapping, key):
    if isinstance(mapping, dict):
        return mapping.get(key)
    return None


# Ícones: traçados do Lucide (lucide.dev, licença ISC), 24x24, traço 2.
ICONS = {
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "menu": '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "pencil": '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "home": '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/><path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "list": '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M8 6h13"/>',
    "card": '<rect width="20" height="14" x="2" y="5" rx="2"/><path d="M2 10h20"/>',
    "wallet": '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "transfer": '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    "repeat": '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "chart": '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    "bot": '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "calendar": '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    "arrow-up-right": '<path d="M7 7h10v10"/><path d="M7 17 17 7"/>',
    "more": '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    "filter": '<path d="M10 20a1 1 0 0 0 .553.895l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .517-1.341L21.74 4.67A1 1 0 0 0 21 3H3a1 1 0 0 0-.742 1.67l7.225 7.989A2 2 0 0 1 10 14z"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
    "bank": '<path d="M3 22h18"/><path d="M6 18v-7"/><path d="M10 18v-7"/><path d="M14 18v-7"/><path d="M18 18v-7"/><path d="m12 2 8 5H4z"/>',
    "tag": '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "check-circle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "circle": '<circle cx="12" cy="12" r="9"/>',
    "eye": '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "dollar": '<path d="M12 2v20"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
}


@register.simple_tag
def icon(name, size=18, label=""):
    paths = ICONS.get(name, ICONS["circle"])
    aria = format_html('role="img" aria-label="{}"', label) if label else mark_safe('aria-hidden="true"')
    return format_html(
        '<svg class="icon" width="{}" height="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" {}>{}</svg>',
        size, size, aria, mark_safe(paths),
    )


@register.simple_tag(takes_context=True)
def nav_active(context, *prefixes):
    """'is-active' quando a rota atual começa com um dos nomes dados."""
    match = getattr(context.get("request"), "resolver_match", None)
    if not match:
        return ""
    name = match.url_name or ""
    full = f"{match.namespace}:{name}" if match.namespace else name
    return "is-active" if any(full.startswith(p) for p in prefixes) else ""


@register.simple_tag(takes_context=True)
def query_with(context, **kwargs):
    """Query string atual trocando/acrescentando parâmetros (paginação com filtros)."""
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.filter
def active_count(form):
    """Quantos filtros estão em uso (ignora paginação)."""
    data = getattr(form, "data", None) or {}
    count = 0
    for key in data:
        if key == "page":
            continue
        values = data.getlist(key) if hasattr(data, "getlist") else [data.get(key)]
        if any(v not in (None, "") for v in values):
            count += 1
    return count
