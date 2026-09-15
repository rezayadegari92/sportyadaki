from django.db import models
from django.db.models import Q


class Payment(models.Model):
    """One attempt to pay an order through the payment gateway. A failed
    attempt stays on record; retrying creates a new Payment for the same order."""

    class Status(models.TextChoices):
        INITIATED = 'initiated', 'در انتظار پرداخت'
        SUCCEEDED = 'succeeded', 'موفق'
        FAILED = 'failed', 'ناموفق'

    order = models.ForeignKey('orders.Order', on_delete=models.PROTECT, related_name='payments', verbose_name='سفارش')
    gateway = models.CharField('درگاه', max_length=50)
    amount = models.DecimalField('مبلغ (تومان)', max_digits=15, decimal_places=0)
    status = models.CharField('وضعیت', max_length=20, choices=Status, default=Status.INITIATED, db_index=True)
    # Token the gateway returns when the payment is requested (e.g. "Authority").
    authority = models.CharField('شناسه درخواست', max_length=100, blank=True, db_index=True)
    # Reference number the gateway returns after a successful verification.
    reference_id = models.CharField('شماره پیگیری پرداخت', max_length=100, blank=True)
    card_pan = models.CharField('شماره کارت (ماسک‌شده)', max_length=32, blank=True)
    raw_response = models.JSONField('پاسخ درگاه', default=dict, blank=True)
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)
    verified_at = models.DateTimeField('تاریخ تایید', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'پرداخت'
        verbose_name_plural = 'پرداخت‌ها'
        constraints = [
            models.UniqueConstraint(
                fields=['gateway', 'authority'], condition=~Q(authority=''), name='unique_gateway_authority',
            ),
        ]

    def __str__(self):
        return f'پرداخت {self.pk} — {self.order}'
