"""Order lifecycle: placing orders, payment results and admin status changes.

Every status change with side effects goes through this module:
  - paid:       deduct stock, issue the invoice, clear bought items from the cart, SMS
  - cancelled:  put deducted stock back, SMS
  - processing / shipped / delivered: timestamps, SMS
"""
import secrets
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from cart.models import CartItem
from cart.services import calculate_totals, stock_problems
from catalog.models import Product
from notifications import services as notify

from .models import Invoice, Order, OrderAddress, OrderItem


class OutOfStockError(Exception):
    def __init__(self, problems):
        super().__init__('; '.join(problem['message'] for problem in problems))
        self.problems = problems


class InvalidTransition(Exception):
    pass


@transaction.atomic
def place_order(*, cart, user, address, note='', request=None):
    """Create a pending order from the cart at current prices, after re-checking stock.

    The cart is kept until payment succeeds, so a failed payment can be retried.
    """
    items = list(cart.items.select_related('product'))
    if not items:
        raise OutOfStockError([{'message': 'سبد خرید خالی است.'}])
    problems = stock_problems(items)
    if problems:
        raise OutOfStockError(problems)

    totals = calculate_totals(items)
    order = Order.objects.create(
        customer=user,
        status=Order.Status.PENDING,
        subtotal_amount=totals.subtotal,
        shipping_total=totals.shipping,
        tax_amount=totals.tax,
        total_amount=totals.total,
        customer_note=note,
        created_via='checkout',
        order_key=secrets.token_urlsafe(16),
        ip_address=(request.META.get('REMOTE_ADDR') or None) if request else None,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500] if request else '',
    )
    extra = '، '.join(part for part in [f'پلاک {address.plaque}' if address.plaque else '',
                                         f'واحد {address.unit}' if address.unit else ''] if part)
    for address_type in (OrderAddress.AddressType.BILLING, OrderAddress.AddressType.SHIPPING):
        OrderAddress.objects.create(
            order=order, address_type=address_type,
            first_name=address.recipient_name, address_1=address.street, address_2=extra,
            city=address.city, state=address.province, postcode=address.postal_code,
            phone=address.recipient_phone,
        )
    OrderItem.objects.bulk_create([
        OrderItem(
            order=order, product=item.product, name=item.product.name, sku=item.product.sku or '',
            quantity=item.quantity, unit_price=item.product.price,
            subtotal=item.product.price * item.quantity, total=item.product.price * item.quantity,
        )
        for item in items
    ])
    return order


@transaction.atomic
def mark_paid(order, payment=None):
    """Record a successful payment (from the gateway, or an admin confirming a manual payment)."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.is_paid:
        return order
    if not order.stock_deducted:
        _deduct_stock(order)
    order.status = Order.Status.PAID
    order.paid_at = timezone.now()
    if payment is not None:
        order.transaction_id = payment.reference_id
        order.payment_method = payment.gateway
    order.save()
    _issue_invoice(order)
    if order.customer_id:
        bought = order.items.exclude(product=None).values('product')
        CartItem.objects.filter(cart__user=order.customer_id, product__in=bought).delete()
    transaction.on_commit(lambda: notify.order_paid(order))
    return order


def mark_payment_failed(order):
    if order.status == Order.Status.PENDING:
        order.status = Order.Status.FAILED
        order.save(update_fields=['status', 'updated_at'])
    return order


@transaction.atomic
def change_status(order, new_status):
    """Move an order to `new_status` if the flow allows it (used by the admin)."""
    if new_status == order.status:
        return order
    if not order.can_transition_to(new_status):
        raise InvalidTransition(
            f'تغییر وضعیت از «{order.get_status_display()}» به «{Order.Status(new_status).label}» مجاز نیست.'
        )
    if new_status == Order.Status.PAID:
        return mark_paid(order)

    order = Order.objects.select_for_update().get(pk=order.pk)
    now = timezone.now()
    order.status = new_status
    if new_status == Order.Status.SHIPPED:
        order.shipped_at = now
    elif new_status == Order.Status.DELIVERED:
        order.completed_at = now
    elif new_status == Order.Status.CANCELLED:
        order.cancelled_at = now
        if order.stock_deducted:
            _restore_stock(order)
    order.save()
    transaction.on_commit(lambda: notify.order_status_changed(order))
    return order


def _locked_products(order):
    ids = order.items.exclude(product=None).values_list('product_id', flat=True)
    return {product.pk: product for product in Product.objects.select_for_update().filter(pk__in=list(ids))}


def _deduct_stock(order):
    products = _locked_products(order)
    shortages = []
    for item in order.items.all():
        product = products.get(item.product_id)
        if product is None:
            continue
        product.total_sales += item.quantity
        if product.manage_stock and product.stock_quantity is not None:
            if item.quantity > product.stock_quantity:
                shortages.append(f'{product.name}: سفارش {item.quantity}، موجودی {product.stock_quantity}')
            product.stock_quantity = max(product.stock_quantity - item.quantity, 0)
            if product.stock_quantity == 0:
                product.stock_status = Product.StockStatus.OUT_OF_STOCK
        product.save(update_fields=['total_sales', 'stock_quantity', 'stock_status', 'updated_at'])
    if shortages:
        # Stock is checked at checkout, but two customers can pay for the last unit
        # at the same moment. Flag it for staff rather than failing a paid order.
        order.staff_note = '\n'.join(filter(None, [order.staff_note, 'کسری موجودی هنگام پرداخت: ' + '؛ '.join(shortages)]))
    order.stock_deducted = True


def _restore_stock(order):
    products = _locked_products(order)
    for item in order.items.all():
        product = products.get(item.product_id)
        if product is None:
            continue
        product.total_sales = max(product.total_sales - item.quantity, 0)
        if product.manage_stock and product.stock_quantity is not None:
            product.stock_quantity += item.quantity
            if product.stock_quantity > 0 and product.stock_status == Product.StockStatus.OUT_OF_STOCK:
                product.stock_status = Product.StockStatus.IN_STOCK
        product.save(update_fields=['total_sales', 'stock_quantity', 'stock_status', 'updated_at'])
    order.stock_deducted = False


def _issue_invoice(order):
    if Invoice.objects.filter(order=order).exists():
        return
    address = order.shipping_address
    customer = order.customer
    name = (customer.get_full_name() if customer else '') or (address.full_name if address else '')
    phone = (customer.phone if customer else '') or (address.phone if address else '')
    billing = ''
    if address:
        billing = '، '.join(filter(None, [address.state, address.city, address.address_1, address.address_2]))
        if address.postcode:
            billing += f' — کد پستی {address.postcode}'
    tax_rate = (order.tax_amount * 100 / order.subtotal_amount).quantize(Decimal('0.01')) if order.subtotal_amount else 0
    Invoice.objects.create(
        order=order, customer_name=name, customer_phone=phone, billing_address=billing,
        subtotal=order.subtotal_amount, shipping=order.shipping_total, discount=order.discount_total,
        tax_rate=tax_rate, tax=order.tax_amount, total=order.total_amount,
    )
