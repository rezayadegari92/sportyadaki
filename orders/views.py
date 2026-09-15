from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render

from cart.services import calculate_totals, get_cart, refresh_prices, stock_problems
from payments.views import begin_payment

from . import services
from .forms import CheckoutForm, TrackOrderForm
from .models import Order

TRACK_ATTEMPTS_LIMIT = 10
TRACK_ATTEMPTS_WINDOW = 15 * 60  # seconds


@login_required
def checkout(request):
    cart = get_cart(request)
    items = list(cart.items.select_related('product')) if cart else []
    if not items:
        messages.info(request, 'سبد خرید شما خالی است.')
        return redirect('cart:detail')
    problems = stock_problems(items)
    if problems:
        for problem in problems:
            messages.error(request, problem['message'])
        return redirect('cart:detail')
    changed = refresh_prices(items)
    if changed:
        messages.info(request, 'قیمت این کالاها تغییر کرده و به‌روز شد: ' + '، '.join(changed))

    form = CheckoutForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            order = services.place_order(
                cart=cart, user=request.user, address=form.cleaned_data['address'],
                note=form.cleaned_data['note'], request=request,
            )
        except services.OutOfStockError as error:
            for problem in error.problems:
                messages.error(request, problem['message'])
            return redirect('cart:detail')
        return begin_payment(request, order)

    return render(request, 'orders/checkout.html', {
        'form': form,
        'items': items,
        'totals': calculate_totals(items),
    })


@login_required
def checkout_result(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('items', 'addresses'), pk=pk, customer=request.user)
    return render(request, 'orders/checkout_result.html', {'order': order})


def track_order(request):
    """Public order lookup by order number + phone (no login).

    POST keeps phone numbers out of URLs and server logs; attempts are limited
    per IP so the form can't be used to guess orders. Requests sent by the
    homepage sheet (X-Requested-With: fetch) get just the result fragment.
    """
    form = TrackOrderForm(request.POST or None)
    order, searched, throttled = None, False, False
    if request.method == 'POST' and form.is_valid():
        key = f"track-order:{request.META.get('REMOTE_ADDR', '')}"
        attempts = cache.get(key, 0)
        if attempts >= TRACK_ATTEMPTS_LIMIT:
            throttled = True
        else:
            cache.set(key, attempts + 1, TRACK_ATTEMPTS_WINDOW)
            searched = True
            order = Order.objects.find_for_tracking(form.cleaned_data['order_number'], form.cleaned_data['phone'])

    context = {'form': form, 'order': order, 'searched': searched, 'throttled': throttled}
    if request.headers.get('X-Requested-With') == 'fetch':
        return render(request, 'orders/includes/track_result.html', context)
    return render(request, 'orders/track.html', context)
