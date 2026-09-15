from django.contrib import admin
from django.db.models import Count, Sum

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ('product', 'quantity', 'unit_price', 'updated_at')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Read-only view of open carts, e.g. to follow up on abandoned ones."""

    list_display = ('__str__', 'user', 'line_count', 'unit_count', 'updated_at')
    list_filter = ('updated_at',)
    search_fields = ('user__phone', 'user__last_name')
    readonly_fields = ('user', 'session_key', 'created_at', 'updated_at')
    inlines = [CartItemInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(lines=Count('items'), units=Sum('items__quantity'))

    def has_add_permission(self, request):
        return False

    @admin.display(description='تعداد اقلام', ordering='lines')
    def line_count(self, obj):
        return obj.lines

    @admin.display(description='تعداد کالا', ordering='units')
    def unit_count(self, obj):
        return obj.units or 0
