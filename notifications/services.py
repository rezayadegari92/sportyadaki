"""Order notifications. Each function writes the message and hands it to the
configured SMSService (notifications/sms). Call them after the database
transaction commits, e.g. transaction.on_commit(lambda: order_paid(order))."""
import logging

from core.models import SiteSettings
from core.templatetags.sporty import fa_number
from core.text import normalize_iran_mobile, to_persian_digits

from .sms import get_sms_service

logger = logging.getLogger(__name__)


def _send(phone, message):
    phone = normalize_iran_mobile(phone)
    if len(phone) != 11:
        return None
    result = get_sms_service().send(phone, message)
    if not result.success:
        logger.warning('SMS to %s failed: %s', phone, result.error)
    return result


def _customer_phone(order):
    if order.customer_id and order.customer.phone:
        return order.customer.phone
    address = order.shipping_address
    return address.phone if address else ''


def order_paid(order):
    number, amount = to_persian_digits(order.pk), fa_number(order.total_amount)
    _send(_customer_phone(order), f'اسپرت یدکی: سفارش #{number} به مبلغ {amount} تومان پرداخت شد و در صف آماده‌سازی است.')
    # Staff alert goes to the store's number from site settings.
    _send(SiteSettings.load().phone, f'سفارش جدید #{number} به مبلغ {amount} تومان پرداخت شد.')


def order_status_changed(order):
    from orders.models import Order

    number = to_persian_digits(order.pk)
    if order.status == Order.Status.PROCESSING:
        message = f'اسپرت یدکی: سفارش #{number} در حال آماده‌سازی است.'
    elif order.status == Order.Status.SHIPPED:
        message = f'اسپرت یدکی: سفارش #{number} ارسال شد.'
        if order.carrier:
            message += f' روش ارسال: {order.get_carrier_display()}.'
        if order.tracking_code:
            message += f' کد رهگیری: {order.tracking_code}'
    elif order.status == Order.Status.DELIVERED:
        message = f'اسپرت یدکی: سفارش #{number} تحویل شد. از خرید شما سپاسگزاریم.'
    elif order.status == Order.Status.CANCELLED:
        message = f'اسپرت یدکی: سفارش #{number} لغو شد. برای پیگیری با ما در تماس باشید.'
    else:
        return
    _send(_customer_phone(order), message)
