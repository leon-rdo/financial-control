import json
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views.generic import CreateView, UpdateView, DeleteView


class HxModalCreateView(CreateView):
    template_name = "snippets/partials/form.html"
    modal_title = "Adicionar"
    submit_label = "Adicionar"
    row_template = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "modal_title": self.modal_title,
                "submit_label": self.submit_label,
                "form_action": self.request.path,
            }
        )
        return context

    def form_valid(self, form):
        self.object = form.save()
        context = self.get_row_context_data()
        row_html = render_to_string(self.row_template, context, request=self.request)

        return HttpResponse(row_html, headers={"HX-Trigger": "objectAdded"})

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_row_context_data(self):
        return {
            "object": self.object,
            "model_name": self.model.__name__.lower(),
            "edit_url": self.edit_url_name,
            "delete_url": self.delete_url_name,
        }


class HxModalUpdateView(UpdateView):
    template_name = "snippets/partials/form.html"
    modal_title = "Editar"
    submit_label = "Salvar"
    row_template = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "modal_title": self.modal_title,
                "submit_label": self.submit_label,
                "form_action": self.request.path,
            }
        )
        return context

    def form_valid(self, form):
        self.object = form.save()
        context = self.get_row_context_data()

        return HttpResponse(
            "",
            headers={
                "HX-Trigger": json.dumps(
                    {
                        "objectUpdated": render_to_string(
                            self.row_template, context, request=self.request
                        )
                    }
                )
            },
        )

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_row_context_data(self):
        return {
            "object": self.object,
            "model_name": self.model.__name__.lower(),
            "edit_url": self.edit_url_name,
            "delete_url": self.delete_url_name,
        }


class HxModalDeleteView(DeleteView):
    template_name = "snippets/partials/confirm_delete.html"
    modal_title = "Confirmar Exclusão"
    submit_label = "Excluir"
    success_message = "Registro excluído com sucesso."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "modal_title": self.modal_title,
                "submit_label": self.submit_label,
                "form_action": self.request.path,
                "object_name": str(self.get_object()),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        """Evita fluxo padrão que exige success_url e envia evento HTMX."""
        self.object = self.get_object()
        object_id = self.object.id
        model_name = self.model.__name__
        self.object.delete()

        return HttpResponse(
            "",
            headers={
                "HX-Trigger": json.dumps(
                    {"objectDeleted": {"id": object_id, "model": model_name}}
                )
            },
        )
