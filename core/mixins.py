import json

from django.contrib import messages
from django.db.models import ProtectedError
from django.http import HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string


def hx_trigger(response, event=None, message=None, kind="success"):
    """Põe no HX-Trigger o evento da tela e o aviso (toast) mostrado pelo base.html."""
    payload = {}
    if event:
        payload[event] = True
    if message:
        payload["showToast"] = {"message": message, "type": kind}
    if payload:
        response["HX-Trigger"] = json.dumps(payload)
    return response


class HtmxModalFormMixin:
    """Formulário em modal (Create/UpdateView).

    Enviado por HTMX, devolve a tabela da lista atualizada (`table_target`). Aberto
    fora da lista (ex.: "Nova transação" no topo, com ?depois=recarregar), salva e
    recarrega a página, com o aviso guardado para depois do recarregamento. Com erro,
    o modal volta com as mensagens no lugar dele, sem tocar na tabela."""

    table_template = None
    table_target = None
    event = "saved"
    success_message = "Salvo."

    def refresh_after(self):
        return self.request.GET.get("depois") == "recarregar" or self.request.POST.get("_after") == "refresh"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["table_target"] = self.table_target
        context["refresh_after"] = self.refresh_after() or not self.table_target
        return context

    def get_table_queryset(self):
        return self.model._default_manager.all()

    def get_table_context(self):
        return {"object_list": self.get_table_queryset()[:20], "page_obj": None, "is_paginated": False}

    def table_response(self, message, kind="success"):
        html = render_to_string(self.table_template, self.get_table_context(), request=self.request)
        return hx_trigger(HttpResponse(html), self.event, message, kind)

    def form_valid(self, form):
        if not getattr(self.request, "htmx", False):
            return super().form_valid(form)
        self.object = form.save()
        if self.refresh_after() or not self.table_template:
            messages.success(self.request, self.success_message)
            response = HttpResponse(status=204)
            response["HX-Refresh"] = "true"
            return response
        return self.table_response(self.success_message)

    def form_invalid(self, form):
        response = super().form_invalid(form)
        if getattr(self.request, "htmx", False):
            response["HX-Retarget"] = "#modal-container"
            response["HX-Reswap"] = "innerHTML"
        return response


class HtmxDeleteMixin(HtmxModalFormMixin):
    """DeleteView que responde com a tabela atualizada. Registro em uso
    (PROTECT) não quebra a página: volta um aviso explicando."""

    success_message = "Excluído."
    protected_message = "Não dá para excluir: há lançamentos usando este cadastro. Desative-o em vez de excluir."

    def _delete(self):
        self.object = self.get_object()
        try:
            self.object.delete()
        except ProtectedError:
            response = HttpResponse(status=409)
            response["HX-Reswap"] = "none"
            return hx_trigger(response, None, self.protected_message, "error")
        if getattr(self.request, "htmx", False):
            if not self.table_template:
                messages.success(self.request, self.success_message)
                response = HttpResponse(status=204)
                response["HX-Refresh"] = "true"
                return response
            return self.table_response(self.success_message)
        return HttpResponseRedirect(self.get_success_url())

    def delete(self, request, *args, **kwargs):
        return self._delete()

    def post(self, request, *args, **kwargs):
        return self._delete()
