from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from catalog.models import Product
from core.text import to_ascii_digits

from . import services
from .models import CartItem


def _quantity(value, default):
    try:
        return int(to_ascii_digits(value or ''))
    except ValueError:
        return default


def _redirect_back(request, fallback):
    target = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect(fallback)


def cart_detail(request):
    cart = services.get_cart(request)
    items = list(cart.items.select_related('product', 'product__part_brand')) if cart else []
    changed = services.refresh_prices(items)
    if changed:
        messages.info(request, 'قیمت این کالاها تغییر کرده و به‌روز شد: ' + '، '.join(changed))
    problems = services.stock_problems(items)
    return render(request, 'cart/cart_detail.html', {
        'items': items,
        'totals': services.calculate_totals(items),
        'problems': problems,
        'problem_item_ids': {problem['item'].pk for problem in problems},
    })


@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product.objects.published(), pk=product_id)
    cart = services.get_cart(request, create=True)
    try:
        _, note = services.add_item(cart, product, _quantity(request.POST.get('quantity'), 1))
    except services.CartError as error:
        messages.error(request, str(error))
        return _redirect_back(request, product.get_absolute_url())
    messages.success(request, f'«{product.name}» به سبد خرید اضافه شد.')
    if note:
        messages.warning(request, note)
    return _redirect_back(request, 'cart:detail')


def _own_item(request, pk):
    # Filtering by the visitor's own cart makes other carts' items a 404.
    return get_object_or_404(CartItem.objects.select_related('product'), pk=pk, cart=services.get_cart(request))


@require_POST
def update_item(request, pk):
    item = _own_item(request, pk)
    note = services.set_quantity(item, _quantity(request.POST.get('quantity'), item.quantity))
    if note:
        messages.warning(request, note)
    return redirect('cart:detail')


@require_POST
def remove_item(request, pk):
    item = _own_item(request, pk)
    name = item.product.name
    item.delete()
    messages.info(request, f'«{name}» از سبد خرید حذف شد.')
    return redirect('cart:detail')
