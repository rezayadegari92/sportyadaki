"""Connects checkout to the configured payment gateway."""
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from orders import services as order_services
from orders.models import Order

from .gateways import get_payment_gateway
from .gateways.base import PaymentGatewayError
from .models import Payment


def start_payment(request, order):
    """Create a Payment for `order` and return the gateway URL to redirect the customer to.

    Raises PaymentGatewayError if the gateway can't create the payment.
    """
    gateway = get_payment_gateway()
    if order.status == Order.Status.FAILED:
        order_services.change_status(order, Order.Status.PENDING)  # retrying a failed payment
    payment = Payment.objects.create(order=order, gateway=gateway.code, amount=order.total_amount)
    try:
        result = gateway.request_payment(
            payment=payment,
            callback_url=request.build_absolute_uri(reverse('payments:callback')),
            description=f'سفارش #{order.pk} اسپرت یدکی',
            mobile=order.customer.phone if order.customer_id else '',
        )
    except PaymentGatewayError as error:
        payment.status = Payment.Status.FAILED
        payment.raw_response = {'request_error': str(error)}
        payment.save(update_fields=['status', 'raw_response'])
        raise
    payment.authority = result.authority
    payment.raw_response = {'request': result.raw}
    payment.save(update_fields=['authority', 'raw_response'])
    return result.redirect_url


def complete_payment(request):
    """Handle the gateway's callback. Returns the Payment, or None if it's unknown.

    The payment row stays locked while the gateway verifies it, so a callback
    that arrives twice (refresh, double redirect) is processed only once.
    """
    gateway = get_payment_gateway()
    authority = gateway.get_authority(request)
    if not authority:
        return None
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update().select_related('order')
            .filter(gateway=gateway.code, authority=authority).first()
        )
        if payment is None or payment.status != Payment.Status.INITIATED:
            return payment
        verification = gateway.verify_payment(payment=payment, request=request)
        payment.raw_response = {**payment.raw_response, 'verify': verification.raw, 'error': verification.error}
        payment.verified_at = timezone.now()
        if verification.success:
            payment.status = Payment.Status.SUCCEEDED
            payment.reference_id = verification.reference_id
            payment.card_pan = verification.card_pan
            payment.save()
            order_services.mark_paid(payment.order, payment)
        else:
            payment.status = Payment.Status.FAILED
            payment.save()
            order_services.mark_payment_failed(payment.order)
    return payment
