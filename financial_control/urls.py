from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include

admin.site.site_header = "Controle Financeiro"
admin.site.site_title = "Controle Financeiro Admin"
admin.site.index_title = "Painel Administrativo"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("entrar/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("select2/", include("django_select2.urls")),
    path("", include("core.urls")),
    path("", include("accounts.urls")),
    path("", include("financial.urls")),
    path("telegram/", include("telegram_bot.urls")),
]
