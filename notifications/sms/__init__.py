from django.conf import settings
from django.utils.module_loading import import_string


def get_sms_service():
    """The SMS service configured in settings.SMS_SERVICE."""
    return import_string(settings.SMS_SERVICE)()
