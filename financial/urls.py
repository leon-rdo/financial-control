from django.urls import path
from . import views

app_name = "financial"

urlpatterns = [
    # Dashboard URL
    path("", views.DashboardView.as_view(), name="dashboard"),
    
    # Recurrence URLs
    path("recorrencias/", views.RecurrenceListView.as_view(), name="recurrence_list"),
    path("recorrencias/criar/", views.RecurrenceCreateView.as_view(), name="recurrence_create"),
    path("recorrencias/<int:pk>/editar/", views.RecurrenceUpdateView.as_view(), name="recurrence_update"),
    path("recorrencias/<int:pk>/excluir/", views.RecurrenceDeleteView.as_view(), name="recurrence_delete"),
    
    # Transaction URLs
    path("transacoes/", views.TransactionListView.as_view(), name="transaction_list"),
    path("transacoes/criar/", views.TransactionCreateView.as_view(), name="transaction_create"),
    path("transacoes/<int:pk>/editar/", views.TransactionUpdateView.as_view(), name="transaction_update"),
    path("transacoes/<int:pk>/excluir/", views.TransactionDeleteView.as_view(), name="transaction_delete"),
    
    # Purchase URLs
    path("compras/", views.PurchaseListView.as_view(), name="purchase_list"),
    path("compras/<int:pk>/", views.PurchaseDetailView.as_view(), name="purchase_detail"),
    path("compras/criar/", views.PurchaseCreateView.as_view(), name="purchase_create"),
    path("compras/<int:pk>/editar/", views.PurchaseUpdateView.as_view(), name="purchase_update"),
    path("compras/<int:pk>/excluir/", views.PurchaseDeleteView.as_view(), name="purchase_delete"),
    
    # Installment API
    path("parcelas/<int:pk>/toggle-paid/", views.toggle_installment_paid, name="toggle_installment_paid"),
]
