from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from django_filters.views import FilterView

from accounts.filters import EntityFilter, PaymentMethodFilter, UserFilter
from accounts.forms import PaymentMethodForm
from .models import Entity, PaymentMethod


class LoginView(LoginView):
    extra_context = {
        "title": "Entrar",
        "description": "Entre na sua conta",
    }


class LogoutView(LogoutView):
    next_page = reverse_lazy("accounts:login")
    extra_context = {
        "title": "Sair",
        "description": "Você saiu da sua conta",
    }


class UserListView(PermissionRequiredMixin, FilterView):
    template_name = "accounts/users/list.html"
    model = get_user_model()
    paginate_by = 10
    filterset_class = UserFilter
    extra_context = {
        "title": "Usuários",
        "description": "Lista de usuários",
    }
    permission_required = "auth.view_user"


class EntityListView(PermissionRequiredMixin, FilterView):
    template_name = "accounts/entities/list.html"
    model = Entity
    paginate_by = 40
    filterset_class = EntityFilter
    extra_context = {"title": "Entidades", "description": "Lista de entidades"}
    permission_required = "accounts.view_entity"

    def post(self, request, *args, **kwargs):
        user = request.user
        name = request.POST.get("name")
        delete_id = request.POST.get("delete_id")
        edit_id = request.POST.get("edit_id")

        # Editar
        if edit_id:
            if not user.has_perm("accounts.change_entity"):
                messages.error(request, "Você não tem permissão para editar esta entidade.")
                return redirect(request.path)
            entity = Entity.objects.get(id=edit_id)
            entity.name = request.POST.get("name")
            entity.description = request.POST.get("description")
            entity.person_type = request.POST.get("person_type")
            entity.document = request.POST.get("document")
            entity.save()
            messages.success(request, "Entidade editada com sucesso.")
            return redirect(request.path)

        # Criar
        if name and not delete_id:
            if not user.has_perm("accounts.add_entity"):
                messages.error(request, "Você não tem permissão para criar uma nova entidade.")
                return redirect(request.path)
            Entity.objects.create(
                name=name,
                description=request.POST.get("description", ""),
                person_type=request.POST.get("person_type"),
                document=request.POST.get("document"),
            )
            messages.success(request, "Entidade criada com sucesso.")

        # Deletar
        if delete_id:
            if not user.has_perm("accounts.delete_entity"):
                messages.error(request, "Você não tem permissão para deletar esta entidade.")
                return redirect(request.path)
            Entity.objects.filter(id=delete_id).delete()
            messages.success(request, "Entidade deletada com sucesso.")

        return redirect(request.path)


class PaymentMethodCreateView(PermissionRequiredMixin, CreateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "accounts/payment_methods/form.html"
    success_url = reverse_lazy("accounts:payment_method_list")
    extra_context = {
        "title": "Criar Forma de Pagamento",
        "description": "Criar uma nova forma de pagamento",
    }
    permission_required = "accounts.add_paymentmethod"


class PaymentMethodListView(PermissionRequiredMixin, FilterView):
    template_name = "accounts/payment_methods/list.html"
    model = PaymentMethod
    paginate_by = 40
    filterset_class = PaymentMethodFilter
    extra_context = {
        "title": "Formas de Pagamento",
        "description": "Lista de formas de pagamento",
    }
    permission_required = "accounts.view_paymentmethod"

    def post(self, request, *args, **kwargs):
        delete_id = request.POST.get("delete_id")

        if delete_id:
            if not request.user.has_perm("accounts.delete_paymentmethod"):
                messages.error(request, "Você não tem permissão para deletar esta forma de pagamento.")
                return redirect(request.path)
            PaymentMethod.objects.filter(id=delete_id).delete()
            messages.success(request, "Forma de pagamento deletada com sucesso.")

        return redirect(request.path)


class PaymentMethodUpdateView(PermissionRequiredMixin, UpdateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "accounts/payment_methods/form.html"
    success_url = reverse_lazy("accounts:payment_method_list")
    extra_context = {
        "title": "Atualizar Forma de Pagamento",
        "description": "Atualizar uma forma de pagamento",
    }
    permission_required = "accounts.change_paymentmethod"
