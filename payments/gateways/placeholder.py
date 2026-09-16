"""Development stand-in for a real payment gateway.

Its "payment page" is a local simulator (payments:simulator) where you choose
whether the payment succeeds or fails, so checkout can be tested end to end.
It refuses to start when DEBUG is off (unless PAYMENT_PLACEHOLDER_ALLOWED is
set, which tests do), so it can never accept orders in production.
"""
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from .base import PaymentGatewayService, PaymentRequest, PaymentVerification


def placeholder_allowed():
    return settings.DEBUG or getattr(settings, 'PAYMENT_PLACEHOLDER_ALLOWED', False)


class PlaceholderGateway(PaymentGatewayService):
    code = 'placeholder'

    def __init__(self):
        if not placeholder_allowed():
            raise ImproperlyConfigured(
                'The placeholder payment gateway is for development only. '
                'Set PAYMENT_GATEWAY to a real gateway implementation.'
            )

    def request_payment(self, *, payment, callback_url, description, mobile=''):
        authority = uuid.uuid4().hex
        query = urlencode({'callback': callback_url})
        redirect_url = f"{reverse('payments:simulator', args=[authority])}?{query}"
        return PaymentRequest(authority=authority, redirect_url=redirect_url, raw={'simulated': True})

    def get_authority(self, request):
        return request.GET.get('authority', '')

    def verify_payment(self, *, payment, request):
        if request.GET.get('result') == 'success':
            return PaymentVerification(
                success=True, reference_id=f'SIM-{payment.pk:08d}', card_pan='6037-99**-****-1234',
                raw={'simulated': True},
            )
        return PaymentVerification(success=False, error='پرداخت در شبیه‌ساز لغو شد.', raw={'simulated': True})
