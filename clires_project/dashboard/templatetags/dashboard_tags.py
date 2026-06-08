from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def startswith(text, prefix):
    return str(text).startswith(prefix)
