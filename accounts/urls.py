from django.urls import path
from .views import *


app_name = "accounts"
urlpatterns = [
    path("metodos-de-pagamento/", PaymentMethodListView.as_view(), name="payment_method_list"),
    path("metodos-de-pagamento/criar/", PaymentMethodCreateView.as_view(), name="payment_method_create"),
]