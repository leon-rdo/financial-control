from django.contrib import admin
from django.urls import path, include

admin.site.site_header = "Controle Financeiro"
admin.site.site_title = "Controle Financeiro Admin"
admin.site.index_title = "Painel Administrativo"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("select2/", include("django_select2.urls")),
    path("", include("core.urls")),
    path("", include("accounts.urls")),
    path("", include("financial.urls")),
    path("telegram/", include("telegram_bot.urls")),
]
