from django.conf import settings
from django.utils.module_loading import import_string


def get_payment_gateway():
    """The payment gateway configured in settings.PAYMENT_GATEWAY."""
    return import_string(settings.PAYMENT_GATEWAY)()
