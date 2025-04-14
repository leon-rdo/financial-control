from django.urls import reverse

urls_data = [
    {
        "name": "Registros",
        "icon": "bx bx-money-withdraw",
        "permissions": ["view_record"],
        "sub_urls": [
            {
                "name": "Lista",
                "url": "financial:financial_record_list",
                "icon": "bx bx-list-ul",
                "permissions": ["financial.view_record"],
            },
            {
                "name": "Adicionar",
                "url": "financial:financial_record_create",
                "icon": "bx bx-list-plus",
                "permissions": ["financial.add_record"],
            },
        ],
    },
    {
        "name": "Categorias",
        "url": "financial:category_list",
        "icon": "bx bx-category",
        "permissions": ["financial.view_category"]
    },
    {
        "name": "Formas de Pagamento",
        "icon": "bx bx-credit-card",
        "permissions": ["accounts.view_paymentmethod"],
        "sub_urls": [
            {
                "name": "Lista",
                "url": "accounts:payment_method_list",
                "icon": "bx bx-list-ul",
                "permissions": ["accounts.view_paymentmethod"],
            },
            {
                "name": "Adicionar",
                "url": "accounts:payment_method_create",
                "icon": "bx bx-list-plus",
                "permissions": ["accounts.add_paymentmethod"],
            },
        ],
    },
    {
        "name": "Administração",
        "url": "admin:index",
        "icon": "bx bx-cog",
        "permissions": ["view_settings"],
    },
]


def check_permission(user, permissions):
    """Função para verificar se o usuário tem as permissões necessárias."""
    return any(user.has_perm(perm) for perm in permissions)


def resolve_url(url):
    """Resolve URLs no formato app_name:url_name para a URL correspondente."""
    if ":" in url:
        try:
            app_name, url_name = url.split(":")
            return reverse(f"{app_name}:{url_name}")
        except Exception as e:
            print(f"Erro ao resolver a URL {url}: {e}")
            return "#"
    return url


def urls_context(request):
    accessible_urls = []

    for link in urls_data:
        if "permissions" in link and check_permission(
            request.user, link["permissions"]
        ):
            # Criar cópia do link para evitar modificar o original
            processed_link = link.copy()

            # Resolver URL principal
            if "url" in processed_link and processed_link["url"]:
                processed_link["url"] = resolve_url(processed_link["url"])
            else:
                processed_link["url"] = "#"

            # Processar sub_urls
            accessible_sub_urls = []
            for sub_link in processed_link.get("sub_urls", []):
                if "permissions" in sub_link and check_permission(
                    request.user, sub_link["permissions"]
                ):
                    sub_link_copy = sub_link.copy()
                    sub_link_copy["url"] = resolve_url(sub_link_copy["url"])
                    accessible_sub_urls.append(sub_link_copy)
            processed_link["sub_urls"] = accessible_sub_urls

            # Verificar se o link ou sublinks estão ativos
            is_active = (request.path == processed_link["url"]) or any(
                sub_link["url"] == request.path for sub_link in accessible_sub_urls
            )
            processed_link["is_active"] = is_active

            accessible_urls.append(processed_link)

    return {"urls": accessible_urls}
