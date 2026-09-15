from django.contrib import admin

from .admin_display import thumbnail
from .models import HeroBanner, Page, SiteSettings


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


@admin.register(HeroBanner)
class HeroBannerAdmin(admin.ModelAdmin):
    list_display = ('thumb', 'title', 'placement', 'content_side', 'is_active', 'position')
    list_display_links = ('thumb', 'title')
    list_editable = ('is_active', 'position')
    list_filter = ('placement', 'is_active')

    @admin.display(description='تصویر')
    def thumb(self, obj):
        return thumbnail(obj.background_image, wide=True)


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'updated_at')
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title',)
