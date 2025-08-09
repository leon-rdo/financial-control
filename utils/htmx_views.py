from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views.generic import CreateView


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
