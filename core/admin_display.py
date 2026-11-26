"""Small HTML helpers for admin list columns (styled by static/css/admin.css)."""
from django.utils.html import format_html

from .templatetags.sporty import fa_decimal, fa_number
from .text import to_persian_digits
from .thumbnails import thumbnail_url

ORDER_STATUS_TONES = {
    'pending': 'gray', 'paid': 'navy', 'processing': 'blue', 'shipped': 'orange',
    'delivered': 'green', 'cancelled': 'red', 'failed': 'red',
}


def thumbnail(image, *, contain=False, wide=False, large=False):
    classes = (
        'sy-thumb' + (' sy-thumb--contain' if contain else '') + (' sy-thumb--wide' if wide else '')
        + (' sy-thumb--large' if large else '')
    )
    if not image:
        return format_html('<span class="{} sy-thumb--empty"></span>', classes)
    # Thumbnails are at most 92px wide: a 200px copy instead of the full upload (core/thumbnails.py).
    return format_html('<img class="{}" src="{}" alt="" loading="lazy">', classes, thumbnail_url(image, 200))


def image_preview(image):
    """A saved image shown at a readable size on a change form, linked to the full file."""
    if not image:
        return format_html('<span class="sy-muted">{}</span>', 'هنوز تصویری بارگذاری نشده است.')
    return format_html(
        '<a href="{}" target="_blank" rel="noopener"><img class="sy-preview" src="{}" alt="" loading="lazy"></a>',
        image.url, thumbnail_url(image, 520),
    )


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
