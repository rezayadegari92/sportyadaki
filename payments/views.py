import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from cart.services import available_quantity
from orders.models import Order

from . import services
from .gateways.base import PaymentGatewayError
from .gateways.placeholder import PlaceholderGateway, placeholder_allowed
from .models import Payment

logger = logging.getLogger(__name__)


def begin_payment(request, order):
    """Send the customer to the gateway for `order`, or back to the order with an error."""
    try:
        return redirect(services.start_payment(request, order))
    except (PaymentGatewayError, ImproperlyConfigured):
        logger.exception('Could not start payment for order %s', order.pk)
        messages.error(request, 'اتصال به درگاه پرداخت برقرار نشد. سفارش شما ثبت شده است؛ لطفاً چند دقیقه بعد دوباره پرداخت کنید.')
        return redirect('accounts:order_detail', order.pk)


@login_required
@require_POST
def pay_order(request, pk):
    """Pay (again) for the customer's own unpaid order."""
    order = get_object_or_404(Order.objects.prefetch_related('items__product'), pk=pk, customer=request.user)
    if order.status not in (Order.Status.PENDING, Order.Status.FAILED):
        messages.info(request, 'این سفارش در انتظار پرداخت نیست.')
        return redirect('accounts:order_detail', order.pk)
    for item in order.items.all():
        available = available_quantity(item.product) if item.product else 0
        if available is not None and item.quantity > available:
            messages.error(request, f'«{item.name}» به تعداد سفارش موجود نیست. لطفاً با ما تماس بگیرید یا سفارش جدید ثبت کنید.')
            return redirect('accounts:order_detail', order.pk)
    return begin_payment(request, order)


@csrf_exempt  # the gateway redirects or POSTs here from its own site
def payment_callback(request):
    payment = services.complete_payment(request)
    if payment is None:
        messages.error(request, 'اطلاعات پرداخت معتبر نیست.')
        return redirect('core:home')
    return redirect('orders:checkout_result', payment.order_id)


def payment_simulator(request, authority):
    """Stand-in "bank page" for PlaceholderGateway (development only)."""
    if not placeholder_allowed() or not isinstance(services.get_payment_gateway(), PlaceholderGateway):
        raise Http404
    payment = get_object_or_404(
        Payment.objects.select_related('order'), gateway=PlaceholderGateway.code, authority=authority,
        status=Payment.Status.INITIATED,
    )
    callback = reverse('payments:callback')
    return render(request, 'payments/simulator.html', {
        'payment': payment,
        'success_url': f'{callback}?authority={authority}&result=success',
        'failure_url': f'{callback}?authority={authority}&result=failed',
    })
