import json

import requests
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DeleteView, UpdateView
from django_filters.views import FilterView

from .filters import BankAccountFilter, PaymentMethodFilter
from .forms import BankAccountForm, PaymentMethodForm, SimplePaymentMethodForm
from .models import BankAccount, PaymentMethod


class BankAccountListView(FilterView):
    model = BankAccount
    template_name = "accounts/bankaccount_list.html"
    context_object_name = "object_list"
    filterset_class = BankAccountFilter
    paginate_by = 20

    def get_template_names(self):
        if self.request.htmx:
            return ["accounts/bankaccount_table.html"]
        return [self.template_name]


class BankAccountCreateView(CreateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = "accounts/bankaccount_form.html"
    success_url = reverse_lazy("bankaccount_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "bankAccountCreated"
            context = {
                "object_list": BankAccount.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "accounts/bankaccount_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class BankAccountUpdateView(UpdateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = "accounts/bankaccount_form.html"
    success_url = reverse_lazy("bankaccount_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "bankAccountUpdated"
            context = {
                "object_list": BankAccount.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "accounts/bankaccount_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class BankAccountDeleteView(DeleteView):
    model = BankAccount
    success_url = reverse_lazy("bankaccount_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        if request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "bankAccountDeleted"
            context = {
                "object_list": BankAccount.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "accounts/bankaccount_table.html", context, request=request
            )
            response.content = html
            return response

        return super().delete(request, *args, **kwargs)


class PaymentMethodListView(FilterView):
    model = PaymentMethod
    template_name = "accounts/paymentmethod_list.html"
    context_object_name = "object_list"
    filterset_class = PaymentMethodFilter
    paginate_by = 20

    def get_template_names(self):
        if self.request.htmx:
            return ["accounts/paymentmethod_table.html"]
        return [self.template_name]


class PaymentMethodCreateView(CreateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "accounts/paymentmethod_form.html"
    success_url = reverse_lazy("accounts:paymentmethod_list")

    def dispatch(self, request, *args, **kwargs):
        if request.GET.get("inline") and request.method == "POST":
            return self.create_inline(request)
        return super().dispatch(request, *args, **kwargs)

    def create_inline(self, request):
        try:
            data = json.loads(request.body)
            form = SimplePaymentMethodForm(data)

            if form.is_valid():
                obj = form.save()
                return JsonResponse(
                    {
                        "success": True,
                        "object": {"id": obj.pk, "name": obj.name, "type": obj.type},
                    }
                )
            else:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Dados inválidos",
                        "errors": form.errors,
                    },
                    status=400,
                )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "paymentMethodCreated"
            context = {
                "object_list": PaymentMethod.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "accounts/paymentmethod_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class PaymentMethodUpdateView(UpdateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "accounts/paymentmethod_form.html"
    success_url = reverse_lazy("paymentmethod_list")

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "paymentMethodUpdated"
            context = {
                "object_list": PaymentMethod.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "accounts/paymentmethod_table.html", context, request=self.request
            )
            response.content = html
            return response
        return super().form_valid(form)


class PaymentMethodDeleteView(DeleteView):
    model = PaymentMethod
    success_url = reverse_lazy("paymentmethod_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        if request.htmx:
            response = HttpResponse()
            response["HX-Trigger"] = "paymentMethodDeleted"
            context = {
                "object_list": PaymentMethod.objects.all()[:20],
                "page_obj": None,
                "is_paginated": False,
            }
            html = render_to_string(
                "accounts/paymentmethod_table.html", context, request=request
            )
            response.content = html
            return response

        return super().delete(request, *args, **kwargs)


# Bank API
@require_http_methods(["GET"])
def fetch_banks(request):
    """Busca lista de bancos da API Brasil"""
    try:
        response = requests.get("https://brasilapi.com.br/api/banks/v1", timeout=10)

        if response.status_code != 200:
            return JsonResponse(
                {"error": "Erro ao consultar bancos. Tente novamente."}, status=500
            )

        banks_data = response.json()

        # Formata os dados para o formato esperado
        banks = []
        for bank in banks_data:
            code = bank.get("code")
            full_name = bank.get("fullName", "")
            name = bank.get("name", "")

            # Cria o texto do banco: "code - fullName" ou apenas "fullName" se code for None
            if code:
                bank_text = f"{code} - {full_name}"
            else:
                bank_text = full_name

            banks.append({"name": name, "bank": bank_text})

        # Ordena por nome
        banks.sort(key=lambda x: x["name"])

        return JsonResponse({"success": True, "banks": banks})

    except requests.Timeout:
        return JsonResponse(
            {"error": "Tempo esgotado ao consultar bancos. Tente novamente."},
            status=500,
        )
    except requests.RequestException as e:
        return JsonResponse(
            {"error": f"Erro ao consultar bancos: {str(e)}"}, status=500
        )
    except Exception as e:
        return JsonResponse({"error": f"Erro inesperado: {str(e)}"}, status=500)
