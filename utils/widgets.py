from django_select2.forms import ModelSelect2MultipleWidget, Select2MultipleWidget
from django_filters import ModelMultipleChoiceFilter, MultipleChoiceFilter


def create_model_select2_filter(model, search_fields=None):
    """
    Cria um filtro ModelMultipleChoiceFilter com ModelSelect2MultipleWidget, útil para buscas em muitos registros.

    :param model: A classe do modelo a ser filtrado
    :param search_fields: Campos para busca no widget Select2
    :return: Instância de ModelMultipleChoiceFilter
    """
    return ModelMultipleChoiceFilter(
        queryset=model.objects.all(),
        widget=ModelSelect2MultipleWidget(
            attrs={
                "data-dropdown-parent": "#filtersOffcanvas",
                "data-placeholder": "Selecione um ou mais itens...",
                "data-ajax--delay": "250",
                "data-minimum-input-length": "0",
            },
            search_fields=search_fields if search_fields else [],
        ),
    )


def create_select2_multiple_filter(choices, **kwargs):
    """
    Função genérica para criar um filtro Select2 com opções múltiplas para campos baseados em choices.
    Aceita kwargs para personalizar o filtro, como label, etc.
    """
    return MultipleChoiceFilter(
        choices=choices,
        widget=Select2MultipleWidget(
            attrs={
                "data-dropdown-parent": "#filtersOffcanvas",
                "data-placeholder": "Selecione um ou mais itens..."
            }
        ),
        **kwargs
    )
