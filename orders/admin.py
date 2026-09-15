from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from core.admin_display import ORDER_STATUS_TONES, badge, order_customer_name, toman
from core.text import to_persian_digits
from payments.models import Payment

from . import services
from .models import Invoice, Order, OrderAddress, OrderItem

AMOUNT_FIELDS = ('subtotal_amount', 'shipping_total', 'tax_amount', 'discount_total', 'total_amount')


class OrderAdminForm(forms.ModelForm):
    """Offers only the statuses the order may move to next."""

    class Meta:
        model = Order
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'status' not in self.fields:
            return
        current = self.instance.status if self.instance.pk else Order.Status.PENDING
        allowed = {current, *Order.TRANSITIONS.get(current, set())} if self.instance.pk else {current}
        self.fields['status'].choices = [(value, label) for value, label in Order.Status.choices if value in allowed]
        self.fields['status'].help_text = (
            'فقط مراحل مجاز بعدی نمایش داده می‌شود. «پرداخت شده» موجودی را کسر و فاکتور صادر می‌کند؛ '
            '«لغو شده» موجودی کسرشده را برمی‌گرداند. مشتری از هر تغییر با پیامک مطلع می‌شود.'
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('status') == Order.Status.SHIPPED and not cleaned.get('carrier'):
            self.add_error('carrier', 'برای ثبت ارسال، روش ارسال را مشخص کنید.')
        return cleaned


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ('name', 'sku', 'quantity', 'unit_price', 'total')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class OrderAddressInline(admin.StackedInline):
    model = OrderAddress
    extra = 0
    max_num = 2
    fields = (('first_name', 'last_name'), 'phone', ('state', 'city', 'postcode'), 'address_1', 'address_2')


class InvoiceInline(admin.StackedInline):
    model = Invoice
    extra = 0
    can_delete = False
    fields = ('number', 'issued_at', 'customer_name', 'customer_phone', 'total')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ('created_at', 'gateway', 'amount', 'status', 'reference_id', 'card_pan')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = ('number', 'customer_name', 'status_badge', 'total', 'carrier', 'tracking_code', 'created_at')
    list_display_links = ('number', 'customer_name')
    list_filter = ('status', 'carrier', 'created_at')
    search_fields = ('=id', 'addresses__phone', 'addresses__last_name', 'addresses__first_name', 'tracking_code', 'customer__phone')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('customer',)
    inlines = [OrderItemInline, OrderAddressInline, PaymentInline, InvoiceInline]
    actions = ['mark_processing', 'mark_delivered', 'cancel_orders']
    fieldsets = (
        (None, {'fields': ('status', 'customer', 'customer_note', 'staff_note')}),
        ('ارسال و رهگیری', {
            'description': 'پس از ذخیره، روش ارسال و کد رهگیری در صفحه سفارش مشتری و پیگیری سفارش نمایش داده می‌شود.',
            'fields': ('carrier', 'tracking_code'),
        }),
        ('مبالغ (تومان)', {'fields': (*AMOUNT_FIELDS, 'currency')}),
        ('پرداخت', {'fields': ('payment_method', 'transaction_id', 'paid_at')}),
        ('زمان‌ها', {'classes': ('collapse',), 'fields': ('created_at', 'shipped_at', 'completed_at', 'cancelled_at', 'updated_at')}),
        ('سایر', {
            'classes': ('collapse',),
            'fields': ('stock_deducted', 'billing_email', 'created_via', 'order_key', 'ip_address', 'user_agent'),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        always = ('stock_deducted', 'created_at', 'updated_at', 'paid_at', 'shipped_at', 'completed_at', 'cancelled_at')
        if obj is None:
            return always
        return (*always, *AMOUNT_FIELDS, 'currency', 'payment_method', 'transaction_id', 'customer', 'order_key', 'created_via')

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('addresses')

    def save_model(self, request, obj, form, change):
        if not (change and 'status' in form.changed_data):
            super().save_model(request, obj, form, change)
            return
        # Save the other edits (e.g. carrier and tracking code) under the old status
        # first, so the status change and its SMS see them.
        new_status = obj.status
        obj.status = Order.objects.values_list('status', flat=True).get(pk=obj.pk)
        super().save_model(request, obj, form, change)
        try:
            services.change_status(obj, new_status)
        except services.InvalidTransition as error:
            messages.error(request, str(error))
        obj.refresh_from_db()

    def _bulk_change(self, request, queryset, status):
        changed, skipped = 0, 0
        for order in queryset:
            try:
                services.change_status(order, status)
                changed += 1
            except services.InvalidTransition:
                skipped += 1
        if changed:
            messages.success(request, f'{changed} سفارش به «{Order.Status(status).label}» تغییر کرد.')
        if skipped:
            messages.warning(request, f'{skipped} سفارش به دلیل وضعیت فعلی قابل تغییر نبود.')

    @admin.action(description='تغییر به «در حال آماده‌سازی»')
    def mark_processing(self, request, queryset):
        self._bulk_change(request, queryset, Order.Status.PROCESSING)

    @admin.action(description='تغییر به «تحویل شده»')
    def mark_delivered(self, request, queryset):
        self._bulk_change(request, queryset, Order.Status.DELIVERED)

    @admin.action(description='لغو سفارش‌های انتخاب‌شده')
    def cancel_orders(self, request, queryset):
        self._bulk_change(request, queryset, Order.Status.CANCELLED)

    @admin.display(description='سفارش', ordering='pk')
    def number(self, obj):
        return format_html('<strong>#{}</strong>', to_persian_digits(obj.pk))

    @admin.display(description='مشتری')
    def customer_name(self, obj):
        return order_customer_name(obj)

    @admin.display(description='وضعیت', ordering='status')
    def status_badge(self, obj):
        return badge(obj.get_status_display(), ORDER_STATUS_TONES.get(obj.status, 'gray'))

    @admin.display(description='مبلغ کل', ordering='total_amount')
    def total(self, obj):
        return toman(obj.total_amount)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'order', 'customer_name', 'amount', 'issued_at')
    search_fields = ('number', 'customer_name', 'customer_phone', '=order__id')
    date_hierarchy = 'issued_at'

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in Invoice._meta.fields]

    def has_add_permission(self, request):
        return False  # issued automatically when an order is paid

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='مبلغ', ordering='total')
    def amount(self, obj):
        return toman(obj.total)
