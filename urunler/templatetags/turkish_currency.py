from django import template

register = template.Library()

def turkish_currency(value):
    try:
        value = float(value)
        # Türkçe format: binlik ayraç nokta, ondalık ayraç virgül
        return '{:,.2f}'.format(value).replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return value

turkish_currency.is_safe = True
register.filter('turkish_currency', turkish_currency)
