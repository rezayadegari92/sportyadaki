from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    """Customers sign in with their mobile number, stored normalized (e.g.
    09121234567). `username` mirrors it so Django's auth tooling keeps working;
    staff created with createsuperuser may have no phone."""

    phone = models.CharField('موبایل', max_length=20, blank=True, db_index=True)
    wp_user_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True, editable=False)

    class Meta(AbstractUser.Meta):
        swappable = 'AUTH_USER_MODEL'
        constraints = [
            models.UniqueConstraint(fields=['phone'], condition=~Q(phone=''), name='unique_user_phone'),
        ]

    @property
    def display_name(self):
        return self.get_full_name() or self.phone or self.username


class Address(models.Model):
    """A saved shipping address. At checkout it is copied onto the order, so
    editing or deleting it later doesn't change past orders."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses', verbose_name='کاربر',
    )
    title = models.CharField('عنوان', max_length=50, help_text='مثلاً خانه یا محل کار')
    recipient_name = models.CharField('نام و نام خانوادگی گیرنده', max_length=150)
    recipient_phone = models.CharField('موبایل گیرنده', max_length=20)
    province = models.CharField('استان', max_length=100)
    city = models.CharField('شهر', max_length=100)
    street = models.CharField('نشانی', max_length=500)
    plaque = models.CharField('پلاک', max_length=20, blank=True)
    unit = models.CharField('واحد', max_length=20, blank=True)
    postal_code = models.CharField('کد پستی', max_length=10)
    is_default = models.BooleanField('آدرس پیش‌فرض', default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-updated_at']
        verbose_name = 'آدرس'
        verbose_name_plural = 'آدرس‌ها'
        constraints = [
            models.UniqueConstraint(fields=['user'], condition=Q(is_default=True), name='one_default_address_per_user'),
        ]

    def __str__(self):
        return f'{self.title} — {self.city}'

    def save(self, *args, **kwargs):
        # The first address becomes the default; a new default replaces the old one.
        if not self.is_default and not Address.objects.filter(user=self.user_id).exclude(pk=self.pk).exists():
            self.is_default = True
        if self.is_default:
            Address.objects.filter(user=self.user_id, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def full_address(self):
        parts = [self.province, self.city, self.street]
        if self.plaque:
            parts.append(f'پلاک {self.plaque}')
        if self.unit:
            parts.append(f'واحد {self.unit}')
        return '، '.join(parts)
