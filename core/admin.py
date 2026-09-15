from django.contrib import admin

from .admin_display import thumbnail
from .models import HeroBanner, HeroBannerImage, Page, SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ('عمومی', {'fields': ('logo', 'phone', 'bale_username', 'eitaa_username')}),
        ('ارسال و مالیات', {
            'description': (
                'هزینه ارسال برای همه سفارش‌ها یکسان است. اگر هر یک از شرط‌های ارسال رایگان برقرار باشد، '
                'ارسال رایگان می‌شود. تغییرات روی سفارش‌هایی که از این پس ثبت می‌شوند اعمال می‌شود.'
            ),
            'fields': ('shipping_cost', 'free_shipping_min_items', 'free_shipping_min_amount', 'tax_rate'),
        }),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class HeroBannerImageInline(admin.TabularInline):
    model = HeroBannerImage
    extra = 1
    fields = ('thumb', 'image', 'position')
    readonly_fields = ('thumb',)

    @admin.display(description='پیش‌نمایش')
    def thumb(self, obj):
        return thumbnail(obj.image, wide=True) if obj.pk else '—'


@admin.register(HeroBanner)
class HeroBannerAdmin(admin.ModelAdmin):
    list_display = ('thumb', 'title', 'placement', 'content_side', 'slide_count', 'is_active', 'position')
    list_display_links = ('thumb', 'title')
    list_editable = ('is_active', 'position')
    list_filter = ('placement', 'is_active')
    inlines = [HeroBannerImageInline]
    fieldsets = (
        (None, {'fields': ('title', 'subtitle', 'placement', 'content_side', 'is_active', 'position')}),
        ('تصویر پس‌زمینه', {
            'fields': ('background_image',),
            'description': (
                'این تصویر اولین قاب بنر است. برای نمایش اسلایدشو (تغییر خودکار تصویر)، '
                'یک یا چند تصویر دیگر هم در پایین این صفحه اضافه کنید.'
            ),
        }),
        ('دکمه‌ها', {'fields': ('primary_cta_label', 'primary_cta_url', 'secondary_cta_label', 'secondary_cta_url')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('extra_images')

    @admin.display(description='تصویر')
    def thumb(self, obj):
        return thumbnail(obj.background_image, wide=True)

    @admin.display(description='تعداد قاب‌ها')
    def slide_count(self, obj):
        return len(obj.slideshow_images)


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'updated_at')
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title',)
