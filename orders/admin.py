from django.contrib import admin
from django.utils.html import format_html

from core.admin_display import ORDER_STATUS_TONES, badge, order_customer_name, toman
from core.text import to_persian_digits

from .models import Order, OrderAddress, OrderItem


class OrderAddressInline(admin.StackedInline):
    model = OrderAddress
    extra = 0
    max_num = 2


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ('product',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'customer_name', 'status_badge', 'total', 'carrier', 'tracking_code', 'created_at')
    list_display_links = ('number', 'customer_name')
    list_filter = ('status', 'carrier', 'payment_method')
    search_fields = ('billing_email', 'addresses__phone', 'addresses__last_name', 'tracking_code')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('customer',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [OrderItemInline, OrderAddressInline]
    fieldsets = (
        (None, {'fields': ('status', 'customer', 'billing_email', 'customer_note')}),
        ('ارسال', {'fields': ('carrier', 'tracking_code')}),
        ('مبالغ', {'fields': (
            'currency', 'total_amount', 'tax_amount', 'shipping_total', 'shipping_tax',
            'discount_total', 'discount_tax',
        )}),
        ('پرداخت', {'fields': ('payment_method', 'payment_method_title', 'transaction_id', 'paid_at')}),
        ('سایر', {
            'classes': ('collapse',),
            'fields': ('created_via', 'order_key', 'ip_address', 'user_agent', 'completed_at', *readonly_fields),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('addresses')

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
