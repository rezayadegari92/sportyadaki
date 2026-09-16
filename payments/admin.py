from django.contrib import admin

from core.admin_display import badge, toman

from .models import Payment

PAYMENT_TONES = {'initiated': 'gray', 'succeeded': 'green', 'failed': 'red'}


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('pk', 'order', 'gateway', 'amount_display', 'status_badge', 'reference_id', 'created_at')
    list_filter = ('status', 'gateway')
    search_fields = ('=order__id', 'reference_id', 'authority')
    date_hierarchy = 'created_at'

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in Payment._meta.fields]

    def has_add_permission(self, request):
        return False  # created by checkout; records of real money movements

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='مبلغ', ordering='amount')
    def amount_display(self, obj):
        return toman(obj.amount)

    @admin.display(description='وضعیت', ordering='status')
    def status_badge(self, obj):
        return badge(obj.get_status_display(), PAYMENT_TONES.get(obj.status, 'gray'))
