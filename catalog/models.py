from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Case, Count, F, Q, When
from django.urls import reverse
from django.utils import timezone


class Term(models.Model):
    """Common shape of a WordPress taxonomy term."""

    name = models.CharField('نام', max_length=200)
    slug = models.SlugField('نامک', max_length=200, unique=True, allow_unicode=True)
    wp_term_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True, editable=False)

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductCategory(Term):
    """WooCommerce `product_cat`."""

    parent = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='children', verbose_name='دسته والد',
    )
    description = models.TextField('توضیحات', blank=True)
    image = models.ImageField('تصویر', upload_to='categories/', blank=True)

    class Meta(Term.Meta):
        verbose_name = 'دسته‌بندی محصول'
        verbose_name_plural = 'دسته‌بندی‌های محصول'


class CarBrand(Term):
    """Car manufacturer — WooCommerce `product_brand` (Saipa, Iran Khodro, Chery...)."""

    # WordPress had no field for this: the homepage logos were hardcoded HTML.
    # Nothing to import, so logos are uploaded here by hand.
    image = models.ImageField('لوگو', upload_to='car-brands/', blank=True)
    position = models.PositiveSmallIntegerField('ترتیب نمایش', default=0)

    class Meta(Term.Meta):
        ordering = ['position', 'name']
        verbose_name = 'برند خودرو'
        verbose_name_plural = 'برندهای خودرو'

    def get_absolute_url(self):
        return reverse('catalog:car_brand', args=[self.slug])


class CarModel(Term):
    """Car model — the misleadingly named `pa_car_brand` attribute (Pride, Tiba, 206...)."""

    # ACF `car_model_brand`: a `product_brand` term id in wp_termmeta. The field
    # has save_terms off, so wp_term_relationships has no row for it. It is
    # optional in ACF, hence nullable.
    brand = models.ForeignKey(
        CarBrand, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='car_models', verbose_name='برند خودرو',
    )
    # ACF `car_model_image`: wp_termmeta stores the attachment id, not a URL.
    # return_format=url only changes what get_field() returns.
    image = models.ImageField('عکس مدل خودرو', upload_to='car-models/', blank=True)

    class Meta(Term.Meta):
        verbose_name = 'مدل خودرو'
        verbose_name_plural = 'مدل‌های خودرو'

    def get_absolute_url(self):
        """The model's page under its brand; '' for a model without a brand."""
        if not self.brand_id:
            return ''
        return reverse('catalog:car_model', args=[self.brand.slug, self.slug])


class PartBrand(Term):
    """Part manufacturer — `pa_brands` (Bosch, NGK, Monroe...)."""

    image = models.ImageField('لوگو', upload_to='part-brands/', blank=True)

    class Meta(Term.Meta):
        verbose_name = 'برند قطعه'
        verbose_name_plural = 'برندهای قطعه'


class Color(Term):
    """`pa_color`."""

    class Meta(Term.Meta):
        verbose_name = 'رنگ'
        verbose_name_plural = 'رنگ‌ها'


class Make(Term):
    """`pa_make`."""

    class Meta(Term.Meta):
        verbose_name = 'سازنده'
        verbose_name_plural = 'سازنده‌ها'


class BodyStyle(Term):
    """`pa_model` — sedan, hatchback, SUV..."""

    class Meta(Term.Meta):
        verbose_name = 'نوع بدنه'
        verbose_name_plural = 'انواع بدنه'


class ManufactureYear(Term):
    """`pa_yearr`."""

    class Meta(Term.Meta):
        verbose_name = 'سال ساخت'
        verbose_name_plural = 'سال‌های ساخت'


# Names of the Product boolean fields behind the sport / accessory browse pages.
PRODUCT_KINDS = ('sport', 'accessory')


def on_sale_condition():
    """Database version of `Product.is_on_sale`."""
    now = timezone.now()
    return (
        Q(sale_price__isnull=False)
        & (Q(regular_price__isnull=True) | Q(sale_price__lt=F('regular_price')))
        & (Q(sale_starts_at__isnull=True) | Q(sale_starts_at__lte=now))
        & (Q(sale_ends_at__isnull=True) | Q(sale_ends_at__gte=now))
    )


class ProductQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Product.Status.PUBLISHED)

    def of_kind(self, kind):
        """Sport or accessory products, whether or not they fit a specific car."""
        if kind not in PRODUCT_KINDS:
            raise ValueError(f'Unknown product kind: {kind!r}')
        return self.filter(**{kind: True})

    def universal(self):
        """Parts not tied to any car model, i.e. fit any car."""
        return self.filter(car_models__isnull=True)

    def for_car_model(self, car_model):
        return self.filter(car_models=car_model)

    def on_sale(self):
        return self.filter(on_sale_condition())

    def with_effective_price(self):
        """Annotate `effective_price`: the sale price while a sale runs, else the regular price."""
        return self.annotate(effective_price=Case(
            When(on_sale_condition(), then=F('sale_price')),
            default=F('regular_price'),
        ))

    def popular(self):
        return self.order_by('-total_sales', '-average_rating', '-created_at')


class Product(models.Model):
    """A simple WooCommerce product.

    Fields follow `wp_wc_product_meta_lookup`. min_price/max_price aren't stored:
    for simple products both equal `price`. Revisit if the store turns out to
    use variable products.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'پیش‌نویس'
        PUBLISHED = 'publish', 'منتشر شده'
        PRIVATE = 'private', 'خصوصی'

    class StockStatus(models.TextChoices):
        IN_STOCK = 'instock', 'موجود'
        OUT_OF_STOCK = 'outofstock', 'ناموجود'
        ON_BACKORDER = 'onbackorder', 'پیش‌سفارش'

    class TaxStatus(models.TextChoices):
        TAXABLE = 'taxable', 'مشمول مالیات'
        SHIPPING = 'shipping', 'فقط هزینه ارسال'
        NONE = 'none', 'بدون مالیات'

    name = models.CharField('نام', max_length=255)
    slug = models.SlugField('نامک', max_length=255, unique=True, allow_unicode=True)
    status = models.CharField('وضعیت', max_length=20, choices=Status, default=Status.DRAFT, db_index=True)
    short_description = models.TextField('توضیح کوتاه', blank=True)
    description = models.TextField('توضیحات', blank=True)
    image = models.ImageField('تصویر شاخص', upload_to='products/%Y/%m/', blank=True)

    sku = models.CharField('شناسه (SKU)', max_length=100, unique=True, null=True, blank=True)
    global_unique_id = models.CharField('GTIN / UPC / EAN / ISBN', max_length=100, blank=True)

    regular_price = models.DecimalField('قیمت', max_digits=15, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField('قیمت فروش ویژه', max_digits=15, decimal_places=2, null=True, blank=True)
    sale_starts_at = models.DateTimeField('شروع فروش ویژه', null=True, blank=True)
    sale_ends_at = models.DateTimeField('پایان فروش ویژه', null=True, blank=True)

    is_virtual = models.BooleanField('مجازی', default=False)
    is_downloadable = models.BooleanField('دانلودی', default=False)

    manage_stock = models.BooleanField('مدیریت موجودی', default=False)
    stock_quantity = models.IntegerField('تعداد موجودی', null=True, blank=True)
    stock_status = models.CharField(
        'وضعیت موجودی', max_length=20, choices=StockStatus, default=StockStatus.IN_STOCK, db_index=True,
    )

    tax_status = models.CharField('وضعیت مالیات', max_length=20, choices=TaxStatus, default=TaxStatus.TAXABLE)
    tax_class = models.CharField('کلاس مالیاتی', max_length=100, blank=True)

    # Denormalized counters, kept in sync by orders/reviews rather than edited by hand.
    total_sales = models.PositiveIntegerField('تعداد فروش', default=0)
    rating_count = models.PositiveIntegerField('تعداد امتیازها', default=0)
    average_rating = models.DecimalField('میانگین امتیاز', max_digits=3, decimal_places=2, default=0)

    categories = models.ManyToManyField(
        ProductCategory, blank=True, related_name='products', verbose_name='دسته‌بندی‌ها',
    )
    # Empty means a universal part that fits any car.
    car_models = models.ManyToManyField(
        CarModel, blank=True, related_name='products', verbose_name='مدل‌های خودرو',
    )
    part_brand = models.ForeignKey(
        PartBrand, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='products', verbose_name='برند قطعه',
    )
    colors = models.ManyToManyField(Color, blank=True, related_name='products', verbose_name='رنگ‌ها')
    makes = models.ManyToManyField(Make, blank=True, related_name='products', verbose_name='سازنده‌ها')
    body_styles = models.ManyToManyField(
        BodyStyle, blank=True, related_name='products', verbose_name='انواع بدنه',
    )
    years = models.ManyToManyField(
        ManufactureYear, blank=True, related_name='products', verbose_name='سال‌های ساخت',
    )
    accessory = models.BooleanField('لوازم جانبی', default=False)
    sport = models.BooleanField('لوازم اسپرت', default=False)
    wp_post_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True, editable=False)
    created_at = models.DateTimeField('تاریخ ایجاد', default=timezone.now)
    updated_at = models.DateTimeField('آخرین ویرایش', auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'محصول'
        verbose_name_plural = 'محصولات'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Blank SKUs are stored as NULL so they don't collide on the unique index.
        if not self.sku:
            self.sku = None
        super().save(*args, **kwargs)

    @property
    def is_on_sale(self):
        if self.sale_price is None:
            return False
        if self.regular_price is not None and self.sale_price >= self.regular_price:
            return False
        now = timezone.now()
        if self.sale_starts_at and now < self.sale_starts_at:
            return False
        if self.sale_ends_at and now > self.sale_ends_at:
            return False
        return True

    def get_absolute_url(self):
        return reverse('catalog:product_detail', args=[self.slug])

    @property
    def price(self):
        return self.sale_price if self.is_on_sale else self.regular_price

    @property
    def discount_percent(self):
        if not self.is_on_sale or not self.regular_price:
            return 0
        return round((self.regular_price - self.sale_price) * 100 / self.regular_price)


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='gallery', verbose_name='محصول')
    image = models.ImageField('تصویر', upload_to='products/%Y/%m/')
    alt = models.CharField('متن جایگزین', max_length=255, blank=True)
    position = models.PositiveSmallIntegerField('ترتیب', default=0)

    class Meta:
        ordering = ['position', 'pk']
        verbose_name = 'تصویر گالری'
        verbose_name_plural = 'گالری تصاویر'


class ProductRatingQuerySet(models.QuerySet):
    def for_visitor(self, user, session_key):
        """The ratings made by this user, or by this browser session when not logged in."""
        if user.is_authenticated:
            return self.filter(user=user)
        if session_key:
            return self.filter(user__isnull=True, session_key=session_key)
        return self.none()


class ProductRating(models.Model):
    """A 1–5 star rating. One per product per user, or per browser session for
    visitors without an account; rating again replaces the earlier stars."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ratings', verbose_name='محصول')
    stars = models.PositiveSmallIntegerField('امتیاز', validators=[MinValueValidator(1), MaxValueValidator(5)])
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='product_ratings', verbose_name='کاربر',
    )
    session_key = models.CharField('نشست', max_length=40, blank=True, editable=False)
    ip_address = models.GenericIPAddressField('IP', null=True, blank=True, editable=False)
    created_at = models.DateTimeField('تاریخ ثبت', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین ویرایش', auto_now=True)

    objects = ProductRatingQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'امتیاز محصول'
        verbose_name_plural = 'امتیازهای محصول'
        constraints = [
            models.CheckConstraint(condition=Q(stars__gte=1, stars__lte=5), name='rating_stars_1_to_5'),
            models.UniqueConstraint(
                fields=['product', 'user'], condition=Q(user__isnull=False), name='unique_rating_per_user',
            ),
            models.UniqueConstraint(
                fields=['product', 'session_key'], condition=Q(user__isnull=True) & ~Q(session_key=''),
                name='unique_rating_per_session',
            ),
        ]

    def __str__(self):
        return f'{self.product} — {self.stars}★'


def refresh_product_rating(product_id):
    """Recompute `Product.rating_count` and `average_rating` from its ratings."""
    summary = ProductRating.objects.filter(product_id=product_id).aggregate(count=Count('pk'), average=Avg('stars'))
    average = Decimal(str(round(summary['average'] or 0, 2)))
    Product.objects.filter(pk=product_id).update(rating_count=summary['count'], average_rating=average)
