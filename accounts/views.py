from django.shortcuts import redirect
from django.views.generic import CreateView, UpdateView
from django.urls import reverse_lazy
from django_filters.views import FilterView
from django.contrib.auth import get_user_model

from accounts.filters import EntityFilter, PaymentMethodFilter, UserFilter
from accounts.forms import PaymentMethodForm
from .models import Entity, PaymentMethod


class UserListView(FilterView):
    template_name = "accounts/users/list.html"
    model = get_user_model()
    paginate_by = 10
    filterset_class = UserFilter
    extra_context = {
        "title": "Usuários",
        "description": "Lista de usuários",
    }


class EntityListView(FilterView):
    template_name = "accounts/entities/list.html"
    model = Entity
    paginate_by = 40
    filterset_class = EntityFilter
    extra_context = {"title": "Entidades", "description": "Lista de entidades"}

    def post(self, request, *args, **kwargs):
        name = request.POST.get("name")
        delete_id = request.POST.get("delete_id")
        edit_id = request.POST.get("edit_id")

        # Editar
        if edit_id:
            entity = Entity.objects.get(id=edit_id)
            entity.name = request.POST.get("name")
            entity.description = request.POST.get("description")
            entity.person_type = request.POST.get("person_type")
            entity.document = request.POST.get("document")
            entity.save()
            return redirect(request.path)

        # Criar
        if name and not delete_id:
            Entity.objects.create(
                name=name,
                description=request.POST.get("description", ""),
                person_type=request.POST.get("person_type"),
                document=request.POST.get("document"),
            )

        # Deletar
        if delete_id:
            Entity.objects.filter(id=delete_id).delete()

        return redirect(request.path)


class PaymentMethodCreateView(CreateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "accounts/payment_methods/form.html"
    success_url = reverse_lazy("accounts:payment_method_list")
    extra_context = {
        "title": "Criar Forma de Pagamento",
        "description": "Criar uma nova forma de pagamento",
    }


class PaymentMethodListView(FilterView):
    template_name = "accounts/payment_methods/list.html"
    model = PaymentMethod
    paginate_by = 40
    filterset_class = PaymentMethodFilter
    extra_context = {
        "title": "Formas de Pagamento",
        "description": "Lista de formas de pagamento",
    }

    def post(self, request, *args, **kwargs):
        delete_id = request.POST.get("delete_id")

        if delete_id:
            PaymentMethod.objects.filter(id=delete_id).delete()

        return redirect(request.path)


class PaymentMethodUpdateView(UpdateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "accounts/payment_methods/form.html"
    success_url = reverse_lazy("accounts:payment_method_list")
    extra_context = {
        "title": "Atualizar Forma de Pagamento",
        "description": "Atualizar uma forma de pagamento",
    }
