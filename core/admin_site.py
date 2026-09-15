"""The project's admin site: Persian branding, app ordering and a dashboard.

Installed in place of `django.contrib.admin` (see INSTALLED_APPS), so every
`admin.site.register` / `@admin.register` in the project uses this site.
"""
from datetime import timedelta

from django.contrib import admin
from django.contrib.admin.apps import AdminConfig
from django.urls import reverse
from django.utils import timezone

APP_ORDER = ['orders', 'payments', 'cart', 'catalog', 'articles', 'core', 'accounts', 'auth']
MODEL_ORDER = [
    'Order', 'Invoice', 'Payment', 'Cart',
    'Product', 'ProductRating', 'CarBrand', 'CarModel', 'PartBrand', 'ProductCategory',
    'Article', 'ArticleCategory', 'HeroBanner', 'SiteSettings', 'Page',
]


def _rank(order, value):
    return order.index(value) if value in order else len(order)


class SportyAdminSite(admin.AdminSite):
    site_header = 'پنل مدیریت اسپرت یدکی'
    site_title = 'مدیریت اسپرت یدکی'
    index_title = 'داشبورد'

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        for app in app_list:
            # Stable sort: models not listed keep Django's alphabetical order.
            app['models'].sort(key=lambda model: _rank(MODEL_ORDER, model['object_name']))
        return sorted(app_list, key=lambda app: _rank(APP_ORDER, app['app_label']))

    def index(self, request, extra_context=None):
        return super().index(request, {'dashboard': dashboard(request), **(extra_context or {})})


class SportyAdminConfig(AdminConfig):
    default_site = 'core.admin_site.SportyAdminSite'


def dashboard(request):
    """Summary cards, quick actions and recent orders, limited to what the user may view."""
    # Imported here: this module is loaded from INSTALLED_APPS before models are ready.
    from articles.models import Article
    from catalog.models import Product, ProductRating
    from orders.models import Order

    from .admin_display import ORDER_STATUS_TONES, order_customer_name

    def changelist(model):
        return reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist')

    user = request.user
    cards = []
    if user.has_perm('catalog.view_product'):
        published = Product.objects.published()
        url = changelist(Product)
        cards += [
            {'label': 'محصولات منتشرشده', 'value': published.count(),
             'url': f'{url}?status__exact=publish', 'tone': 'navy', 'icon': 'box'},
            {'label': 'در حراج', 'value': published.on_sale().count(), 'url': url, 'tone': 'orange', 'icon': 'tag'},
            {'label': 'ناموجود', 'value': published.filter(stock_status=Product.StockStatus.OUT_OF_STOCK).count(),
             'url': f'{url}?stock_status__exact=outofstock', 'tone': 'red', 'icon': 'alert'},
        ]

    recent_orders = None
    if user.has_perm('orders.view_order'):
        # Paid orders are waiting to be prepared: the queue staff should act on.
        cards.append({
            'label': 'سفارش‌های پرداخت‌شده (در انتظار آماده‌سازی)',
            'value': Order.objects.filter(status=Order.Status.PAID).count(),
            'url': f'{changelist(Order)}?status__exact=paid', 'tone': 'green', 'icon': 'cart',
        })
        orders = Order.objects.prefetch_related('addresses')[:6]
        recent_orders = [
            {'order': order, 'name': order_customer_name(order),
             'tone': ORDER_STATUS_TONES.get(order.status, 'gray'),
             'url': reverse('admin:orders_order_change', args=[order.pk])}
            for order in orders
        ]

    if user.has_perm('catalog.view_productrating'):
        week_ago = timezone.now() - timedelta(days=7)
        cards.append({
            'label': 'امتیازهای ۷ روز اخیر', 'value': ProductRating.objects.filter(created_at__gte=week_ago).count(),
            'url': changelist(ProductRating), 'tone': 'gold', 'icon': 'star',
        })
    if user.has_perm('articles.view_article'):
        cards.append({
            'label': 'مقالات منتشرشده', 'value': Article.objects.published().count(),
            'url': changelist(Article), 'tone': 'blue', 'icon': 'doc',
        })

    actions = [
        {'label': label, 'url': reverse(url_name), 'icon': icon}
        for perm, label, url_name, icon in [
            ('catalog.add_product', 'افزودن محصول', 'admin:catalog_product_add', 'plus'),
            ('articles.add_article', 'افزودن مقاله', 'admin:articles_article_add', 'plus'),
            ('core.view_herobanner', 'بنرهای صفحه اصلی', 'admin:core_herobanner_changelist', 'image'),
            ('core.view_sitesettings', 'تنظیمات سایت', 'admin:core_sitesettings_changelist', 'gear'),
        ]
        if user.has_perm(perm)
    ]
    return {'cards': cards, 'actions': actions, 'recent_orders': recent_orders}
