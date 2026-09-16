from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from core.admin_display import badge, stars, thumbnail, toman
from core.templatetags.sporty import fa_number

from .models import (
    BodyStyle, CarBrand, CarModel, Color, Make, ManufactureYear, PartBrand, Product,
    ProductCategory, ProductImage, ProductRating,
)

STOCK_TONES = {'instock': 'green', 'outofstock': 'red', 'onbackorder': 'orange'}
PRODUCT_STATUS_TONES = {'publish': 'green', 'draft': 'gray', 'private': 'navy'}


class TermAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


for model in (PartBrand, Color, Make, BodyStyle, ManufactureYear):
    admin.site.register(model, TermAdmin)


@admin.register(CarBrand)
class CarBrandAdmin(TermAdmin):
    list_display = ('logo', 'name', 'slug', 'position')
    list_display_links = ('logo', 'name')
    list_editable = ('position',)

    @admin.display(description='لوگو')
    def logo(self, obj):
        return thumbnail(obj.image, contain=True)


@admin.register(ProductCategory)
class ProductCategoryAdmin(TermAdmin):
    list_display = ('name', 'slug', 'parent')


@admin.register(CarModel)
class CarModelAdmin(TermAdmin):
    list_display = ('name', 'slug', 'brand')
    list_filter = ('brand',)
    autocomplete_fields = ('brand',)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class ProductRatingInline(admin.TabularInline):
    model = ProductRating
    extra = 0
    fields = ('stars', 'user', 'ip_address', 'created_at')
    readonly_fields = ('user', 'ip_address', 'created_at')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('thumb', 'name', 'sku', 'price', 'kinds', 'rating', 'stock', 'status_badge')
    list_display_links = ('thumb', 'name')
    list_filter = ('status', 'sport', 'accessory', 'stock_status', 'categories', 'part_brand')
    list_per_page = 30
    save_on_top = True
    search_fields = ('name', 'sku')
    prepopulated_fields = {'slug': ('name',)}
    autocomplete_fields = ('categories', 'car_models', 'part_brand', 'colors', 'makes', 'body_styles', 'years')
    readonly_fields = ('total_sales', 'rating_count', 'average_rating', 'created_at', 'updated_at')
    inlines = [ProductImageInline, ProductRatingInline]
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'status', 'image', 'short_description', 'description')}),
        ('قیمت', {'fields': ('regular_price', 'sale_price', 'sale_starts_at', 'sale_ends_at')}),
        ('موجودی', {'fields': ('sku', 'global_unique_id', 'manage_stock', 'stock_quantity', 'stock_status')}),
        ('طبقه‌بندی', {
            'description': (
                'اسپرت و اکسسوری مستقل از مدل خودرو هستند. اگر هیچ مدل خودرویی انتخاب نشود، '
                'محصول «عمومی» (مناسب همه خودروها) است.'
            ),
            'fields': (
                ('sport', 'accessory'), 'categories', 'car_models', 'part_brand',
                'colors', 'makes', 'body_styles', 'years',
            ),
        }),
        ('سایر', {
            'classes': ('collapse',),
            'fields': ('is_virtual', 'is_downloadable', 'tax_status', 'tax_class', *readonly_fields),
        }),
    )

    @admin.display(description='تصویر')
    def thumb(self, obj):
        return thumbnail(obj.image, contain=True)

    @admin.display(description='قیمت', ordering='regular_price')
    def price(self, obj):
        if obj.is_on_sale and obj.regular_price:
            return format_html('<del class="sy-muted">{}</del><br>{}', fa_number(obj.regular_price), toman(obj.sale_price))
        return toman(obj.price)

    @admin.display(description='نوع')
    def kinds(self, obj):
        labels = [badge('اسپرت', 'orange') if obj.sport else '', badge('اکسسوری', 'blue') if obj.accessory else '']
        return mark_safe(' '.join(label for label in labels if label)) or '—'

    @admin.display(description='امتیاز', ordering='average_rating')
    def rating(self, obj):
        return stars(obj.average_rating, obj.rating_count)

    @admin.display(description='موجودی', ordering='stock_status')
    def stock(self, obj):
        return badge(obj.get_stock_status_display(), STOCK_TONES.get(obj.stock_status, 'gray'))

    @admin.display(description='وضعیت', ordering='status')
    def status_badge(self, obj):
        return badge(obj.get_status_display(), PRODUCT_STATUS_TONES.get(obj.status, 'gray'))


@admin.register(ProductRating)
class ProductRatingAdmin(admin.ModelAdmin):
    list_display = ('product', 'star_count', 'user', 'ip_address', 'created_at')
    list_filter = ('stars',)
    search_fields = ('product__name', 'user__username', 'ip_address')
    autocomplete_fields = ('product',)
    readonly_fields = ('user', 'ip_address', 'created_at', 'updated_at')

    @admin.display(description='امتیاز', ordering='stars')
    def star_count(self, obj):
        return format_html('<span class="sy-stars">{}</span><span class="sy-muted">{}</span>', '★' * obj.stars, '★' * (5 - obj.stars))
