from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/create/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/update/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),

    path("tags/", views.TagListView.as_view(), name="tag_list"),
    path("tags/create/", views.TagCreateView.as_view(), name="tag_create"),
    path("tags/<int:pk>/update/", views.TagUpdateView.as_view(), name="tag_update"),
    path("tags/<int:pk>/delete/", views.TagDeleteView.as_view(), name="tag_delete"),

    path("entities/", views.EntityListView.as_view(), name="entity_list"),
    path("entities/create/", views.EntityCreateView.as_view(), name="entity_create"),
    path("entities/<int:pk>/update/", views.EntityUpdateView.as_view(), name="entity_update"),
    path("entities/<int:pk>/delete/", views.EntityDeleteView.as_view(), name="entity_delete"),

    path("familia/", views.FamilyListView.as_view(), name="family_list"),
    path("familia/criar/", views.FamilyCreateView.as_view(), name="family_create"),
    path("familia/<int:pk>/editar/", views.FamilyUpdateView.as_view(), name="family_update"),
    path("familia/<int:pk>/excluir/", views.FamilyDeleteView.as_view(), name="family_delete"),

    path("api/fetch-cnpj/", views.fetch_cnpj_data, name="fetch_cnpj"),
]
