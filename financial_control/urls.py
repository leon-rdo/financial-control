from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("select2/", include("django_select2.urls")),
    path("", include("core.urls")),
    path("", include("accounts.urls")),
    path("", include("financial.urls")),
]
