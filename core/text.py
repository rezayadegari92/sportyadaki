"""Text helpers for Persian user input."""

_DIGIT_MAP = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '0123456789' * 2)
_PERSIAN_DIGIT_MAP = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def to_ascii_digits(value):
    """Replace Persian and Arabic-Indic digits with ASCII digits."""
    return str(value).translate(_DIGIT_MAP)


def to_persian_digits(value):
    """Replace ASCII digits with Persian digits for display."""
    return str(value).translate(_PERSIAN_DIGIT_MAP)


def normalize_iran_mobile(value):
    """Reduce a phone number to its local 11-digit form, e.g. '09391098198'.

    Accepts Persian digits, spaces/dashes and +98 / 0098 / 98 prefixes, so the
    same number typed differently by a customer and by WooCommerce compares equal.
    """
    digits = ''.join(ch for ch in to_ascii_digits(value or '') if ch in '0123456789')
    if digits.startswith('0098'):
        digits = digits[4:]
    elif digits.startswith('98') and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith('9'):
        digits = '0' + digits
    return digits
