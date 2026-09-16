from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Cart(models.Model):
    """A shopping cart for a signed-in user or, before sign-in, a browser
    session. Signing in merges the session cart into the user's cart."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name='cart', verbose_name='کاربر',
    )
    session_key = models.CharField('نشست', max_length=40, blank=True, db_index=True)
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین تغییر', auto_now=True)

    class Meta:
        verbose_name = 'سبد خرید'
        verbose_name_plural = 'سبدهای خرید'
        constraints = [
            models.UniqueConstraint(
                fields=['session_key'], condition=Q(user__isnull=True) & ~Q(session_key=''),
                name='unique_cart_per_session',
            ),
        ]

    def __str__(self):
        return f'سبد {self.user or self.session_key[:8]}'


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items', verbose_name='سبد')
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.CASCADE, related_name='cart_items', verbose_name='محصول',
    )
    quantity = models.PositiveIntegerField('تعداد', default=1, validators=[MinValueValidator(1)])
    # Price when the item was last added or refreshed. Checkout always charges
    # the current price and refreshes this, telling the customer if it changed.
    unit_price = models.DecimalField('قیمت واحد', max_digits=15, decimal_places=2)
    added_at = models.DateTimeField('تاریخ افزودن', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین تغییر', auto_now=True)

    class Meta:
        ordering = ['added_at']
        verbose_name = 'کالای سبد'
        verbose_name_plural = 'کالاهای سبد'
        constraints = [
            models.UniqueConstraint(fields=['cart', 'product'], name='unique_product_per_cart'),
        ]

    def __str__(self):
        return f'{self.product} × {self.quantity}'

    @property
    def line_total(self):
        return self.unit_price * self.quantity
