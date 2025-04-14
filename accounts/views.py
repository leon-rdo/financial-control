from django.shortcuts import redirect
from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy

from accounts.forms import PaymentMethodForm
from .models import PaymentMethod


class PaymentMethodListView(ListView):
    template_name = "accounts/payment_methods/list.html"
    model = PaymentMethod
    paginate_by = 40
    extra_context = {
        "title": "Formas de Pagamento",
        "description": "Lista de formas de pagamento",
    }

    def post(self, request, *args, **kwargs):
        delete_id = request.POST.get("delete_id")

        if delete_id:
            PaymentMethod.objects.filter(id=delete_id).delete()

        return redirect(request.path)


class PaymentMethodCreateView(CreateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "accounts/payment_methods/create.html"
    success_url = reverse_lazy("accounts:payment_method_list")
    extra_context = {
        "title": "Criar Forma de Pagamento",
        "description": "Criar uma nova forma de pagamento",
    }
