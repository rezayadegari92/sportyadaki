from django.conf import settings
from django.db import models
from django.utils import timezone

from core.text import normalize_iran_mobile, to_ascii_digits


class Carrier(models.TextChoices):
    POST = 'post', 'پست ایران'
    TIPAX = 'tipax', 'تیپاکس'
    COURIER = 'courier', 'پیک موتوری'


# TODO: confirm against the tracking links in the WordPress snippet.
CARRIER_TRACKING_URLS = {
    Carrier.TIPAX: 'https://tipaxco.com/tracking',
    Carrier.POST: 'https://tracking.post.ir/',
}


class OrderQuerySet(models.QuerySet):
    def find_for_tracking(self, order_number, phone):
        """Return the order only if `phone` matches its billing or shipping phone.

        Any mismatch returns None, same as a missing order, so the public form
        can't be used to find out which order numbers exist.
        """
        number = to_ascii_digits(order_number).strip().lstrip('#')
        phone = normalize_iran_mobile(phone)
        if not number.isdecimal() or not phone:
            return None
        order = self.filter(pk=int(number)).prefetch_related('addresses').first()
        if order and any(normalize_iran_mobile(a.phone) == phone for a in order.addresses.all()):
            return order
        return None


class Order(models.Model):
    """A customer order. The primary key is the order number customers see
    (imported WooCommerce orders keep their original id).

    Status changes with side effects (stock, invoice, SMS) go through
    orders.services.change_status(), never by assigning `status` directly.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'در انتظار پرداخت'
        PAID = 'paid', 'پرداخت شده'
        PROCESSING = 'processing', 'در حال آماده‌سازی'
        SHIPPED = 'shipped', 'ارسال شده'
        DELIVERED = 'delivered', 'تحویل شده'
        CANCELLED = 'cancelled', 'لغو شده'
        FAILED = 'failed', 'پرداخت ناموفق'

    # Allowed next statuses. Cancelling is admin-only (there is no customer view for it).
    TRANSITIONS = {
        Status.PENDING: {Status.PAID, Status.FAILED, Status.CANCELLED},
        Status.FAILED: {Status.PENDING, Status.PAID, Status.CANCELLED},
        Status.PAID: {Status.PROCESSING, Status.CANCELLED},
        Status.PROCESSING: {Status.SHIPPED, Status.CANCELLED},
        Status.SHIPPED: {Status.DELIVERED, Status.CANCELLED},
        Status.DELIVERED: set(),
        Status.CANCELLED: set(),
    }
    PAID_STATUSES = {Status.PAID, Status.PROCESSING, Status.SHIPPED, Status.DELIVERED}

    status = models.CharField('وضعیت', max_length=20, choices=Status, default=Status.PENDING, db_index=True)
    currency = models.CharField('واحد پول', max_length=10, default='IRT')
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders', verbose_name='مشتری',
    )
    billing_email = models.EmailField('ایمیل', blank=True)
    customer_note = models.TextField('یادداشت مشتری', blank=True)
    staff_note = models.TextField('یادداشت داخلی', blank=True, help_text='فقط برای مدیران نمایش داده می‌شود.')

    subtotal_amount = models.DecimalField('جمع کالاها', max_digits=15, decimal_places=2, default=0)
    shipping_total = models.DecimalField('هزینه ارسال', max_digits=15, decimal_places=2, default=0)
    shipping_tax = models.DecimalField('مالیات ارسال', max_digits=15, decimal_places=2, default=0)
    discount_total = models.DecimalField('تخفیف', max_digits=15, decimal_places=2, default=0)
    discount_tax = models.DecimalField('مالیات تخفیف', max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField('مالیات', max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField('مبلغ کل', max_digits=15, decimal_places=2, default=0)

    payment_method = models.CharField('روش پرداخت', max_length=100, blank=True)
    payment_method_title = models.CharField('عنوان روش پرداخت', max_length=200, blank=True)
    transaction_id = models.CharField('شناسه تراکنش', max_length=100, blank=True)

    # Filled in by staff; shown to the customer once set.
    carrier = models.CharField('روش / شرکت ارسال', max_length=20, choices=Carrier, blank=True)
    tracking_code = models.CharField('کد رهگیری مرسوله', max_length=100, blank=True)

    # Set when stock was deducted for this order, so it happens (and is undone) once.
    stock_deducted = models.BooleanField('کسر از موجودی', default=False, editable=False)

    created_via = models.CharField('ایجاد از طریق', max_length=100, blank=True)
    order_key = models.CharField('کلید سفارش', max_length=100, blank=True)
    ip_address = models.GenericIPAddressField('IP مشتری', null=True, blank=True)
    user_agent = models.TextField('مرورگر مشتری', blank=True)

    created_at = models.DateTimeField('تاریخ ثبت', default=timezone.now, db_index=True)
    updated_at = models.DateTimeField('آخرین ویرایش', auto_now=True)
    paid_at = models.DateTimeField('تاریخ پرداخت', null=True, blank=True)
    shipped_at = models.DateTimeField('تاریخ ارسال', null=True, blank=True)
    completed_at = models.DateTimeField('تاریخ تحویل', null=True, blank=True)
    cancelled_at = models.DateTimeField('تاریخ لغو', null=True, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'سفارش'
        verbose_name_plural = 'سفارش‌ها'

    def __str__(self):
        return f'سفارش #{self.pk}'

    def can_transition_to(self, status):
        return status in self.TRANSITIONS.get(self.status, set())

    @property
    def is_paid(self):
        return self.status in self.PAID_STATUSES

    @property
    def tracking_url(self):
        return CARRIER_TRACKING_URLS.get(self.carrier, '')

    @property
    def progress_steps(self):
        """Fulfilment steps for a progress bar; empty for unpaid, failed or cancelled orders."""
        flow = [self.Status.PAID, self.Status.PROCESSING, self.Status.SHIPPED, self.Status.DELIVERED]
        if self.status not in flow:
            return []
        reached = flow.index(self.status)
        return [
            {'label': status.label, 'done': index <= reached, 'current': index == reached}
            for index, status in enumerate(flow)
        ]

    @property
    def shipping_address(self):
        addresses = {address.address_type: address for address in self.addresses.all()}
        return addresses.get(OrderAddress.AddressType.SHIPPING) or addresses.get(OrderAddress.AddressType.BILLING)


class OrderAddress(models.Model):
    """`wp_wc_order_addresses` — one billing and one shipping row per order.
    A snapshot: later edits to the customer's saved address don't change it."""

    class AddressType(models.TextChoices):
        BILLING = 'billing', 'صورتحساب'
        SHIPPING = 'shipping', 'ارسال'

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='addresses', verbose_name='سفارش')
    address_type = models.CharField('نوع', max_length=10, choices=AddressType)
    first_name = models.CharField('نام', max_length=100, blank=True)
    last_name = models.CharField('نام خانوادگی', max_length=100, blank=True)
    company = models.CharField('شرکت', max_length=200, blank=True)
    address_1 = models.CharField('آدرس', max_length=255, blank=True)
    address_2 = models.CharField('ادامه آدرس', max_length=255, blank=True)
    city = models.CharField('شهر', max_length=100, blank=True)
    state = models.CharField('استان', max_length=100, blank=True)
    postcode = models.CharField('کد پستی', max_length=20, blank=True)
    country = models.CharField('کشور', max_length=2, default='IR')
    email = models.EmailField('ایمیل', blank=True)
    phone = models.CharField('تلفن', max_length=20, blank=True)

    class Meta:
        verbose_name = 'آدرس سفارش'
        verbose_name_plural = 'آدرس‌های سفارش'
        constraints = [
            models.UniqueConstraint(fields=['order', 'address_type'], name='unique_order_address_type'),
        ]

    def __str__(self):
        return f'{self.get_address_type_display()} — {self.first_name} {self.last_name}'.strip()

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()


class OrderItem(models.Model):
    """A product line. Name, SKU and prices are copied at purchase time so the
    order still reads correctly after the product is edited or deleted."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='سفارش')
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='order_items', verbose_name='محصول',
    )
    name = models.CharField('نام محصول', max_length=255)
    sku = models.CharField('شناسه (SKU)', max_length=100, blank=True)
    quantity = models.PositiveIntegerField('تعداد', default=1)
    unit_price = models.DecimalField('قیمت واحد', max_digits=15, decimal_places=2, default=0)
    subtotal = models.DecimalField('جمع قبل از تخفیف', max_digits=15, decimal_places=2, default=0)
    subtotal_tax = models.DecimalField('مالیات قبل از تخفیف', max_digits=15, decimal_places=2, default=0)
    total = models.DecimalField('جمع', max_digits=15, decimal_places=2, default=0)
    total_tax = models.DecimalField('مالیات', max_digits=15, decimal_places=2, default=0)
    wp_order_item_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True, editable=False)

    class Meta:
        verbose_name = 'قلم سفارش'
        verbose_name_plural = 'اقلام سفارش'

    def __str__(self):
        return f'{self.name} × {self.quantity}'


class Invoice(models.Model):
    """Issued when an order is paid. Amounts and customer details are copied
    from the order, so the invoice doesn't change if the order is edited."""

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name='invoice', verbose_name='سفارش')
    number = models.CharField('شماره فاکتور', max_length=30, unique=True, editable=False)
    issued_at = models.DateTimeField('تاریخ صدور', default=timezone.now)
    customer_name = models.CharField('نام خریدار', max_length=200)
    customer_phone = models.CharField('موبایل خریدار', max_length=20)
    billing_address = models.TextField('نشانی', blank=True)
    subtotal = models.DecimalField('جمع کالاها', max_digits=15, decimal_places=2)
    shipping = models.DecimalField('هزینه ارسال', max_digits=15, decimal_places=2)
    discount = models.DecimalField('تخفیف', max_digits=15, decimal_places=2, default=0)
    tax_rate = models.DecimalField('نرخ مالیات (درصد)', max_digits=5, decimal_places=2, default=0)
    tax = models.DecimalField('مالیات', max_digits=15, decimal_places=2, default=0)
    total = models.DecimalField('مبلغ قابل پرداخت', max_digits=15, decimal_places=2)

    class Meta:
        ordering = ['-issued_at']
        verbose_name = 'فاکتور'
        verbose_name_plural = 'فاکتورها'

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        # One invoice per order, so the order id keeps numbers unique without a counter.
        if not self.number:
            self.number = f'INV-{self.issued_at:%Y}-{self.order_id:06d}'
        super().save(*args, **kwargs)
