from django.db import models


class SiteSettings(models.Model):
    """Single row (pk=1) with contact details shown across the site."""

    logo = models.ImageField(
        'لوگو', upload_to='site/', blank=True,
        help_text='PNG با پس‌زمینه واقعاً شفاف یا سفید (نه طرح شطرنجی)، حداقل ۱۲۰ پیکسل ارتفاع.',
    )
    phone = models.CharField('موبایل', max_length=20, default='09391098198')
    bale_username = models.CharField('نام کاربری بله', max_length=100, blank=True, default='Sportyadaki')
    eitaa_username = models.CharField('نام کاربری ایتا', max_length=100, blank=True, default='sportyadaki')

    class Meta:
        verbose_name = 'تنظیمات سایت'
        verbose_name_plural = 'تنظیمات سایت'

    def __str__(self):
        return 'تنظیمات سایت'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def bale_url(self):
        return f'https://ble.ir/{self.bale_username}' if self.bale_username else ''

    @property
    def eitaa_url(self):
        return f'https://eitaa.com/{self.eitaa_username}' if self.eitaa_username else ''


class HeroBanner(models.Model):
    """Homepage promotional banner with up to two call-to-action buttons."""

    class Placement(models.TextChoices):
        TOP = 'top', 'بالای صفحه اصلی'
        MIDDLE = 'middle', 'وسط صفحه اصلی'

    class ContentSide(models.TextChoices):
        RIGHT = 'right', 'راست'
        LEFT = 'left', 'چپ'

    placement = models.CharField('جایگاه', max_length=10, choices=Placement, default=Placement.TOP)
    content_side = models.CharField(
        'جای متن', max_length=5, choices=ContentSide, default=ContentSide.RIGHT,
        help_text='متن و دکمه‌ها روی این طرف بنر قرار می‌گیرند؛ طرف خالی تصویر را انتخاب کنید.',
    )
    title = models.CharField('عنوان', max_length=200)
    subtitle = models.CharField('زیرعنوان', max_length=300, blank=True)
    background_image = models.ImageField('تصویر پس‌زمینه', upload_to='banners/', blank=True)
    # CharField rather than URLField so relative paths like /sport/ are allowed.
    primary_cta_label = models.CharField('متن دکمه اول', max_length=50, blank=True)
    primary_cta_url = models.CharField('لینک دکمه اول', max_length=500, blank=True)
    secondary_cta_label = models.CharField('متن دکمه دوم', max_length=50, blank=True)
    secondary_cta_url = models.CharField('لینک دکمه دوم', max_length=500, blank=True)
    is_active = models.BooleanField('فعال', default=True)
    position = models.PositiveSmallIntegerField('ترتیب', default=0)

    class Meta:
        ordering = ['position', 'pk']
        verbose_name = 'بنر صفحه اصلی'
        verbose_name_plural = 'بنرهای صفحه اصلی'

    def __str__(self):
        return self.title


class Page(models.Model):
    """Simple static page (about us, terms, ...)."""

    title = models.CharField('عنوان', max_length=200)
    slug = models.SlugField('نامک', max_length=200, unique=True, allow_unicode=True)
    body = models.TextField('متن')
    is_published = models.BooleanField('منتشر شده', default=True)
    updated_at = models.DateTimeField('آخرین ویرایش', auto_now=True)

    class Meta:
        verbose_name = 'صفحه'
        verbose_name_plural = 'صفحات'

    def __str__(self):
        return self.title
