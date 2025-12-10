from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("select2/", include("django_select2.urls")),
    path("", TemplateView.as_view(template_name="dashboard.html"), name="dashboard"), # temporary
    path("", include("core.urls")),
    path('', include('accounts.urls')),
    # path('', include('financial.urls')),
]
