from django.contrib import admin
from .models import Entity, PaymentMethod


admin.site.site_header = "Controle Financeiro"
admin.site.site_title = "Controle Financeiro"
admin.site.index_title = "Bem-vindo ao painel de controle financeiro!"


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("name", "person_type", "document")
    search_fields = ("name", "document")


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("fin_institution", "owner")
    search_fields = ("fin_institution", "owner__name")
