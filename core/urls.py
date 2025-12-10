from django.urls import path
from .views import (
    CategoryListView,
    CategoryCreateView,
    CategoryUpdateView,
    CategoryDeleteView,
    TagListView,
    TagCreateView,
    TagUpdateView,
    TagDeleteView,
    EntityListView,
    EntityCreateView,
    EntityUpdateView,
    EntityDeleteView,
    fetch_cnpj_data,
)

app_name = 'core'
urlpatterns = [
    # Categories
    path('categories/', CategoryListView.as_view(), name='category_list'),
    path('categories/create/', CategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:pk>/update/', CategoryUpdateView.as_view(), name='category_update'),
    path('categories/<int:pk>/delete/', CategoryDeleteView.as_view(), name='category_delete'),
    
    # Tags
    path('tags/', TagListView.as_view(), name='tag_list'),
    path('tags/create/', TagCreateView.as_view(), name='tag_create'),
    path('tags/<int:pk>/update/', TagUpdateView.as_view(), name='tag_update'),
    path('tags/<int:pk>/delete/', TagDeleteView.as_view(), name='tag_delete'),
    
    # Entities
    path('entities/', EntityListView.as_view(), name='entity_list'),
    path('entities/create/', EntityCreateView.as_view(), name='entity_create'),
    path('entities/<int:pk>/update/', EntityUpdateView.as_view(), name='entity_update'),
    path('entities/<int:pk>/delete/', EntityDeleteView.as_view(), name='entity_delete'),
    
    # API
    path('api/fetch-cnpj/', fetch_cnpj_data, name='fetch_cnpj'),
]
