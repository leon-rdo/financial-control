from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
    # BankAccount URLs
    path("contas/", views.BankAccountListView.as_view(), name="bankaccount_list"),
    path("contas/criar/", views.BankAccountCreateView.as_view(), name="bankaccount_create"),
    path("contas/<int:pk>/editar/", views.BankAccountUpdateView.as_view(), name="bankaccount_update"),
    path("contas/<int:pk>/excluir/", views.BankAccountDeleteView.as_view(), name="bankaccount_delete"),
    
    # PaymentMethod URLs
    path("metodos-pagamento/", views.PaymentMethodListView.as_view(), name="paymentmethod_list"),
    path("metodos-pagamento/criar/", views.PaymentMethodCreateView.as_view(), name="paymentmethod_create"),
    path("metodos-pagamento/<int:pk>/editar/", views.PaymentMethodUpdateView.as_view(), name="paymentmethod_update"),
    path("metodos-pagamento/<int:pk>/excluir/", views.PaymentMethodDeleteView.as_view(), name="paymentmethod_delete"),
    
    # API URLs
    path("api/fetch-banks/", views.fetch_banks, name="fetch_banks"),
]