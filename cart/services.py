"""Cart operations, stock availability and order totals."""
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from catalog.models import Product
from core.models import SiteSettings

from .models import Cart, CartItem

SESSION_CART_KEY = 'cart_id'


class CartError(Exception):
    """A request the cart can't fulfil; the message is shown to the customer."""


# ---- Finding the cart --------------------------------------------------------

def get_cart(request, *, create=False):
    """The signed-in user's cart, or the visitor's session cart.

    The anonymous cart's id lives in the session data (not the session key),
    because Django issues a new session key on login and the cart must survive
    that to be merged (see cart/signals.py).
    """
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if cart is None and create:
            cart = Cart.objects.create(user=request.user)
        return cart

    cart_id = request.session.get(SESSION_CART_KEY)
    cart = Cart.objects.filter(pk=cart_id, user__isnull=True).first() if cart_id else None
    if cart is None and create:
        if not request.session.session_key:
            request.session.save()
        cart = Cart.objects.create(session_key=request.session.session_key)
        request.session[SESSION_CART_KEY] = cart.pk
    return cart


def merge_session_cart(request, user):
    """Move the visitor's session cart into `user`'s cart after they sign in."""
    cart_id = request.session.pop(SESSION_CART_KEY, None)
    session_cart = Cart.objects.filter(pk=cart_id, user__isnull=True).first() if cart_id else None
    if session_cart is None:
        return
    user_cart, _ = Cart.objects.get_or_create(user=user)
    for item in session_cart.items.select_related('product'):
        existing = user_cart.items.filter(product=item.product).first()
        if existing:
            existing.quantity = clamp_quantity(item.product, existing.quantity + item.quantity) or existing.quantity
            existing.save(update_fields=['quantity', 'updated_at'])
        else:
            item.cart = user_cart
            item.save(update_fields=['cart', 'updated_at'])
    session_cart.delete()


def item_count(cart):
    if cart is None:
        return 0
    return cart.items.aggregate(total=Sum('quantity'))['total'] or 0


# ---- Stock -------------------------------------------------------------------

def available_quantity(product):
    """How many units can be ordered right now; None means no limit."""
    if product.status != Product.Status.PUBLISHED or product.price is None:
        return 0
    if product.stock_status == Product.StockStatus.OUT_OF_STOCK:
        return 0
    if product.manage_stock and product.stock_quantity is not None:
        return max(product.stock_quantity, 0)
    return None


def clamp_quantity(product, quantity):
    available = available_quantity(product)
    return quantity if available is None else min(quantity, available)


def stock_problems(items):
    """Cart items that can't be ordered as they are, with a message for each."""
    problems = []
    for item in items:
        available = available_quantity(item.product)
        if available == 0:
            problems.append({'item': item, 'available': 0, 'message': f'«{item.product.name}» در حال حاضر موجود نیست.'})
        elif available is not None and item.quantity > available:
            problems.append({
                'item': item, 'available': available,
                'message': f'از «{item.product.name}» فقط {available} عدد موجود است.',
            })
    return problems


# ---- Changing the cart -------------------------------------------------------

def add_item(cart, product, quantity=1):
    """Add `quantity` of `product`. Returns (item, note); note explains a reduced quantity."""
    available = available_quantity(product)
    if available == 0:
        raise CartError('این محصول در حال حاضر قابل خرید نیست.')
    item = cart.items.filter(product=product).first()
    wanted = (item.quantity if item else 0) + max(quantity, 1)
    allowed = clamp_quantity(product, wanted)
    note = f'از این محصول فقط {available} عدد موجود است.' if allowed < wanted else ''
    if item:
        item.quantity, item.unit_price = allowed, product.price
        item.save(update_fields=['quantity', 'unit_price', 'updated_at'])
    else:
        item = CartItem.objects.create(cart=cart, product=product, quantity=allowed, unit_price=product.price)
    return item, note


def set_quantity(item, quantity):
    """Change an item's quantity (0 removes it). Returns a note if it was reduced to the stock."""
    if quantity <= 0:
        item.delete()
        return ''
    allowed = clamp_quantity(item.product, quantity)
    if allowed == 0:
        item.delete()
        return f'«{item.product.name}» دیگر موجود نیست و از سبد حذف شد.'
    item.quantity = allowed
    item.save(update_fields=['quantity', 'updated_at'])
    return f'از این محصول فقط {allowed} عدد موجود است.' if allowed < quantity else ''


def refresh_prices(items):
    """Update price snapshots to current prices. Returns the names of products whose price changed."""
    changed = []
    for item in items:
        price = item.product.price
        if price is not None and price != item.unit_price:
            item.unit_price = price
            item.save(update_fields=['unit_price', 'updated_at'])
            changed.append(item.product.name)
    return changed


# ---- Totals ------------------------------------------------------------------

@dataclass
class CartTotals:
    item_count: int
    subtotal: Decimal
    shipping: Decimal
    tax: Decimal
    total: Decimal
    shipping_cost: Decimal  # the configured fixed cost, for "free shipping" display
    items_to_free_shipping: int | None  # items still needed for free shipping (None: rule off or met)
    amount_to_free_shipping: Decimal | None  # amount still needed for free shipping

    @property
    def free_shipping(self):
        return self.item_count > 0 and self.shipping == 0 and self.shipping_cost > 0


def calculate_totals(items, site_settings=None):
    """Totals for a list of cart items at current product prices."""
    site_settings = site_settings or SiteSettings.load()
    count = sum(item.quantity for item in items)
    subtotal = sum(((item.product.price or Decimal(0)) * item.quantity for item in items), Decimal(0))
    shipping = site_settings.shipping_cost_for(count, subtotal) if count else Decimal(0)
    tax = (subtotal * site_settings.tax_rate / 100).quantize(Decimal('1'))

    items_to_free = amount_to_free = None
    if count and shipping > 0:
        if site_settings.free_shipping_min_items:
            items_to_free = site_settings.free_shipping_min_items - count
        if site_settings.free_shipping_min_amount is not None:
            amount_to_free = site_settings.free_shipping_min_amount - subtotal
    return CartTotals(
        item_count=count, subtotal=subtotal, shipping=shipping, tax=tax, total=subtotal + shipping + tax,
        shipping_cost=site_settings.shipping_cost,
        items_to_free_shipping=items_to_free, amount_to_free_shipping=amount_to_free,
    )
