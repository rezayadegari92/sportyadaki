from django import template

from core.text import to_persian_digits

register = template.Library()


@register.filter
def fa_digits(value):
    return to_persian_digits(value)


@register.filter
def fa_number(value):
    """Whole number with Persian digits and separators: 1250000 -> '۱٬۲۵۰٬۰۰۰'."""
    if value is None or value == '':
        return ''
    try:
        number = int(value)
    except (TypeError, ValueError):
        return value
    return to_persian_digits(f'{number:,}').replace(',', '٬')


@register.filter
def fa_decimal(value):
    """One decimal place with Persian digits: 4.25 -> '۴٫۳'."""
    if value is None or value == '':
        return ''
    return to_persian_digits(f'{float(value):.1f}').replace('.', '٫')


@register.filter
def rating_percent(value):
    """Star fill width for a 0–5 rating, as a plain (unlocalized) string for CSS."""
    return f'{max(0.0, min(100.0, float(value or 0) * 20)):.1f}'
