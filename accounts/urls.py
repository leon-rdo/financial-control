from django.urls import path
from .views import *


app_name = "accounts"
urlpatterns = [
    path("usuarios/", UserListView.as_view(), name="user_list"),
    path("entidades/", EntityListView.as_view(), name="entity_list"),
    path("metodos-de-pagamento/", PaymentMethodListView.as_view(), name="payment_method_list"),
    path("metodos-de-pagamento/criar/", PaymentMethodCreateView.as_view(), name="payment_method_create"),
]