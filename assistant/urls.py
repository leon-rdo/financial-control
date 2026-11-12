from django.urls import path

from . import views

app_name = "assistant"
urlpatterns = [
    path("lotes/", views.BatchListView.as_view(), name="batch_list"),
    path("lotes/<int:pk>/", views.BatchDetailView.as_view(), name="batch_detail"),
    path("lotes/<int:pk>/<str:action>/", views.batch_action, name="batch_action"),
    path("regras/", views.RuleListView.as_view(), name="rule_list"),
    path("regras/criar/", views.RuleCreateView.as_view(), name="rule_create"),
    path("regras/<int:pk>/editar/", views.RuleUpdateView.as_view(), name="rule_update"),
    path("regras/<int:pk>/excluir/", views.RuleDeleteView.as_view(), name="rule_delete"),
    path("regras/<int:pk>/alternar/", views.rule_toggle, name="rule_toggle"),
    path("custo/", views.CostView.as_view(), name="cost"),
]
