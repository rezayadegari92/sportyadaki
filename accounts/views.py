from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from orders.models import Invoice, Order

from .forms import AddressForm, LoginForm, ProfileForm, RegisterForm
from .models import Address


def _safe_next(request):
    target = request.POST.get('next') or request.GET.get('next') or ''
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return ''


def register(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user, backend='accounts.backends.PhoneBackend')
        messages.success(request, f'{user.first_name} عزیز، به اسپرت یدکی خوش آمدید.')
        return redirect(_safe_next(request) or 'accounts:dashboard')
    return render(request, 'accounts/register.html', {'form': form, 'next': _safe_next(request)})


class SiteLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True


class SitePasswordChangeView(PasswordChangeView):
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:dashboard')

    def form_valid(self, form):
        messages.success(self.request, 'رمز عبور شما تغییر کرد.')
        return super().form_valid(form)


@login_required
def dashboard(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'اطلاعات حساب ذخیره شد.')
        return redirect('accounts:dashboard')
    return render(request, 'accounts/dashboard.html', {
        'form': form,
        'recent_orders': request.user.orders.all()[:3],
        'address_count': request.user.addresses.count(),
    })


# ---- Addresses ---------------------------------------------------------------

@login_required
def address_list(request):
    return render(request, 'accounts/address_list.html', {'addresses': request.user.addresses.all()})


@login_required
def address_create(request):
    form = AddressForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        address.save()
        messages.success(request, 'آدرس جدید ذخیره شد.')
        return redirect(_safe_next(request) or 'accounts:addresses')
    if not request.user.addresses.exists():
        form.initial.setdefault('recipient_name', request.user.get_full_name())
        form.initial.setdefault('recipient_phone', request.user.phone)
    return render(request, 'accounts/address_form.html', {'form': form, 'next': _safe_next(request)})


@login_required
def address_edit(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    form = AddressForm(request.POST or None, instance=address)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'آدرس ویرایش شد.')
        return redirect(_safe_next(request) or 'accounts:addresses')
    return render(request, 'accounts/address_form.html', {'form': form, 'address': address, 'next': _safe_next(request)})


@login_required
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    was_default = address.is_default
    address.delete()
    if was_default:
        replacement = request.user.addresses.first()
        if replacement:
            replacement.is_default = True
            replacement.save()
    messages.info(request, 'آدرس حذف شد.')
    return redirect('accounts:addresses')


@login_required
@require_POST
def address_make_default(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.is_default = True
    address.save()
    return redirect(_safe_next(request) or 'accounts:addresses')


# ---- Orders ------------------------------------------------------------------

@login_required
def order_list(request):
    orders = request.user.orders.prefetch_related('items')
    return render(request, 'accounts/order_list.html', {
        'page': Paginator(orders, 10).get_page(request.GET.get('page')),
    })


@login_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product', 'addresses'), pk=pk, customer=request.user,
    )
    return render(request, 'accounts/order_detail.html', {
        'order': order,
        'invoice': Invoice.objects.filter(order=order).first(),
        'can_pay': order.status in (Order.Status.PENDING, Order.Status.FAILED),
    })
