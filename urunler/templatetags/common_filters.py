from django import template

register = template.Library()


@register.filter
def at_index(list_obj, index):
    """List'ten index'te öğe al"""
    try:
        return list_obj[int(index)]
    except (IndexError, ValueError, TypeError):
        return '-'


@register.filter
def get_item(dictionary, key):
    """Dictionary'den key ile item al"""
    try:
        return dictionary.get(key, '-')
    except (AttributeError, TypeError):
        return '-'
