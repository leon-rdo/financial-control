from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Lookup a dictionary value by key in templates."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, None)
    return None
