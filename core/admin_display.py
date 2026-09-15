"""Small HTML helpers for admin list columns (styled by static/css/admin.css)."""
from django.utils.html import format_html

from .templatetags.sporty import fa_decimal, fa_number
from .text import to_persian_digits

ORDER_STATUS_TONES = {
    'pending': 'gray', 'processing': 'blue', 'on-hold': 'orange', 'completed': 'green',
    'cancelled': 'red', 'refunded': 'navy', 'failed': 'red', 'checkout-draft': 'gray',
}


def thumbnail(image, *, contain=False, wide=False):
    classes = 'sy-thumb' + (' sy-thumb--contain' if contain else '') + (' sy-thumb--wide' if wide else '')
    if not image:
        return format_html('<span class="{} sy-thumb--empty"></span>', classes)
    return format_html('<img class="{}" src="{}" alt="" loading="lazy">', classes, image.url)


def badge(label, tone):
    return format_html('<span class="sy-badge sy-badge--{}">{}</span>', tone, label)


def toman(value):
    if value is None:
        return '—'
    return format_html('{} <small class="sy-muted">تومان</small>', fa_number(value))


def stars(average, count):
    if not count:
        return '—'
    return format_html(
        '<span class="sy-stars">★ {}</span> <small class="sy-muted">({})</small>',
        fa_decimal(average), to_persian_digits(count),
    )


def order_customer_name(order):
    addresses = {address.address_type: address for address in order.addresses.all()}
    address = addresses.get('billing') or addresses.get('shipping')
    name = f'{address.first_name} {address.last_name}'.strip() if address else ''
    return name or order.billing_email or '—'
