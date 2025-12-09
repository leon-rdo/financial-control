# from django.urls import path
# from django.views.generic import RedirectView

# from .views import *

# app_name = "financial"

# urlpatterns = [
#     path(
#         "",
#         RedirectView.as_view(pattern_name="financial:financial_record_list", permanent=True),
#         name="index",
#     ),
#     path("registros/", FinancialRecordListView.as_view(), name="financial_record_list"),
#     path("registros/criar/", FinancialRecordCreateView.as_view(), name="financial_record_create"),
#     path("registros/<int:pk>/", FinancialRecordDetailView.as_view(), name="financial_record_detail"),
#     path("registros/<int:pk>/editar/", FinancialRecordUpdateView.as_view(), name="financial_record_update"),
#     path("parcelas/", InstallmentListView.as_view(), name="installment_list"),
#     path("categorias/criar/", CategoryCreateView.as_view(), name="category_create"),
#     path("categorias/", CategoryListView.as_view(), name="category_list"),
#     path("categorias/<int:pk>/editar/", CategoryUpdateView.as_view(), name="category_update"),
#     path("categorias/<int:pk>/excluir/", CategoryDeleteView.as_view(), name="category_delete"),
# ]
