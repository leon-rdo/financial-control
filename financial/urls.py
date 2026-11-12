from django.urls import path

from . import views

app_name = "financial"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),

    path("recorrencias/", views.RecurrenceListView.as_view(), name="recurrence_list"),
    path("recorrencias/gerar/", views.generate_recurrences_view, name="generate_recurrences"),
    path("recorrencias/criar/", views.RecurrenceCreateView.as_view(), name="recurrence_create"),
    path("recorrencias/<int:pk>/editar/", views.RecurrenceUpdateView.as_view(), name="recurrence_update"),
    path("recorrencias/<int:pk>/excluir/", views.RecurrenceDeleteView.as_view(), name="recurrence_delete"),

    path("transacoes/", views.TransactionListView.as_view(), name="transaction_list"),
    path("transacoes/criar/", views.TransactionCreateView.as_view(), name="transaction_create"),
    path("transacoes/<int:pk>/editar/", views.TransactionUpdateView.as_view(), name="transaction_update"),
    path("transacoes/<int:pk>/duplicar/", views.TransactionDuplicateView.as_view(), name="transaction_duplicate"),
    path("transacoes/<int:pk>/excluir/", views.TransactionDeleteView.as_view(), name="transaction_delete"),
    path("transacoes/<int:pk>/toggle-confirmed/", views.toggle_transaction_confirmed,
         name="toggle_transaction_confirmed"),

    path("compras/", views.PurchaseListView.as_view(), name="purchase_list"),
    path("compras/<int:pk>/", views.PurchaseDetailView.as_view(), name="purchase_detail"),
    path("compras/criar/", views.PurchaseCreateView.as_view(), name="purchase_create"),
    path("compras/<int:pk>/editar/", views.PurchaseUpdateView.as_view(), name="purchase_update"),
    path("compras/<int:pk>/excluir/", views.PurchaseDeleteView.as_view(), name="purchase_delete"),

    path("transferencias/", views.TransferListView.as_view(), name="transfer_list"),
    path("transferencias/criar/", views.TransferCreateView.as_view(), name="transfer_create"),
    path("transferencias/<int:pk>/editar/", views.TransferUpdateView.as_view(), name="transfer_update"),
    path("transferencias/<int:pk>/excluir/", views.TransferDeleteView.as_view(), name="transfer_delete"),

    path("previsao-faturas/", views.InvoiceForecastView.as_view(), name="invoice_forecast"),
    path("cartoes/", views.CardsView.as_view(), name="cards"),
    path("terceiros/", views.ThirdPartyView.as_view(), name="third_party"),
    path("relatorios/mensal/", views.MonthlyReportView.as_view(), name="monthly_report"),

    path("parcelas/<int:pk>/toggle-paid/", views.toggle_installment_paid, name="toggle_installment_paid"),
    path("parcelas/bulk-toggle-paid/", views.bulk_toggle_installments_paid, name="bulk_toggle_installments_paid"),
]
