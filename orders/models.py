from django.conf import settings
from django.db import models
from django.utils import timezone

from core.text import normalize_iran_mobile, to_ascii_digits


class Carrier(models.TextChoices):
    TIPAX = 'tipax', 'تیپاکس'
    POST = 'post', 'پست ایران'


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
        order = (
            self.exclude(status=Order.Status.CHECKOUT_DRAFT)
            .filter(pk=int(number))
            .prefetch_related('addresses')
            .first()
        )
        if order and any(normalize_iran_mobile(a.phone) == phone for a in order.addresses.all()):
            return order
        return None


class Order(models.Model):
    """WooCommerce HPOS order (`wp_wc_orders` + `wp_wc_order_operational_data`).

    Imported orders keep their WooCommerce id as the primary key, because that
    is the order number customers already have.
    """

    class Status(models.TextChoices):
        # WooCommerce stores these with a `wc-` prefix.
        PENDING = 'pending', 'در انتظار پرداخت'
        PROCESSING = 'processing', 'در حال انجام'
        ON_HOLD = 'on-hold', 'در انتظار بررسی'
        COMPLETED = 'completed', 'تکمیل شده'
        CANCELLED = 'cancelled', 'لغو شده'
        REFUNDED = 'refunded', 'مسترد شده'
        FAILED = 'failed', 'ناموفق'
        CHECKOUT_DRAFT = 'checkout-draft', 'پیش‌نویس'

    status = models.CharField('وضعیت', max_length=20, choices=Status, default=Status.PENDING, db_index=True)
    currency = models.CharField('واحد پول', max_length=10, default='IRT')
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders', verbose_name='مشتری',
    )
    billing_email = models.EmailField('ایمیل', blank=True)
    customer_note = models.TextField('یادداشت مشتری', blank=True)

    total_amount = models.DecimalField('مبلغ کل', max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField('مالیات', max_digits=15, decimal_places=2, default=0)
    shipping_total = models.DecimalField('هزینه ارسال', max_digits=15, decimal_places=2, default=0)
    shipping_tax = models.DecimalField('مالیات ارسال', max_digits=15, decimal_places=2, default=0)
    discount_total = models.DecimalField('تخفیف', max_digits=15, decimal_places=2, default=0)
    discount_tax = models.DecimalField('مالیات تخفیف', max_digits=15, decimal_places=2, default=0)

    payment_method = models.CharField('روش پرداخت', max_length=100, blank=True)
    payment_method_title = models.CharField('عنوان روش پرداخت', max_length=200, blank=True)
    transaction_id = models.CharField('شناسه تراکنش', max_length=100, blank=True)

    # Previously the `_syt_carrier` / `_syt_tracking_code` order meta.
    carrier = models.CharField('شرکت حمل', max_length=20, choices=Carrier, blank=True)
    tracking_code = models.CharField('کد رهگیری', max_length=100, blank=True)

    created_via = models.CharField('ایجاد از طریق', max_length=100, blank=True)
    order_key = models.CharField('کلید سفارش', max_length=100, blank=True)
    ip_address = models.GenericIPAddressField('IP مشتری', null=True, blank=True)
    user_agent = models.TextField('مرورگر مشتری', blank=True)

    created_at = models.DateTimeField('تاریخ ثبت', default=timezone.now, db_index=True)
    updated_at = models.DateTimeField('آخرین ویرایش', auto_now=True)
    paid_at = models.DateTimeField('تاریخ پرداخت', null=True, blank=True)
    completed_at = models.DateTimeField('تاریخ تکمیل', null=True, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'سفارش'
        verbose_name_plural = 'سفارش‌ها'

    def __str__(self):
        return f'سفارش #{self.pk}'

    @property
    def tracking_url(self):
        return CARRIER_TRACKING_URLS.get(self.carrier, '')


class OrderAddress(models.Model):
    """`wp_wc_order_addresses` — one billing and one shipping row per order."""

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


class OrderItem(models.Model):
    """A product line (`wp_woocommerce_order_items` of type `line_item`).

    Name and SKU are copied at purchase time so the order still reads correctly
    after the product is edited or deleted.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='سفارش')
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='order_items', verbose_name='محصول',
    )
    name = models.CharField('نام محصول', max_length=255)
    sku = models.CharField('شناسه (SKU)', max_length=100, blank=True)
    quantity = models.PositiveIntegerField('تعداد', default=1)
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
