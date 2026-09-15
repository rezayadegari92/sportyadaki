from decimal import Decimal
from io import StringIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from articles.models import Article
from catalog.models import CarBrand, Product

from .models import HeroBanner, SiteSettings
from .templatetags.sporty import fa_number
from .text import normalize_iran_mobile, to_ascii_digits


class TextHelperTests(SimpleTestCase):
    def test_to_ascii_digits(self):
        self.assertEqual(to_ascii_digits('سفارش ۱۲۳ و ٤٥'), 'سفارش 123 و 45')

    def test_normalize_iran_mobile(self):
        cases = {
            '09391098198': '09391098198',
            '0939 109 8198': '09391098198',
            '+98 939-109-8198': '09391098198',
            '00989391098198': '09391098198',
            '989391098198': '09391098198',
            '9391098198': '09391098198',
            '۰۹۳۹۱۰۹۸۱۹۸': '09391098198',
            '': '',
            None: '',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_iran_mobile(raw), expected)

    def test_fa_number(self):
        self.assertEqual(fa_number(Decimal('1250000.00')), '۱٬۲۵۰٬۰۰۰')
        self.assertEqual(fa_number(None), '')


class SiteSettingsTests(TestCase):
    def test_always_a_single_row(self):
        SiteSettings.load()
        SiteSettings(phone='0912').save()
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.load().phone, '0912')
        self.assertEqual(SiteSettings.load().bale_url, 'https://ble.ir/Sportyadaki')


class HomePageTests(TestCase):
    def test_no_template_comment_leaks_into_the_page(self):
        # {# #} only works on one line; a multi-line one is printed as text, and a
        # tag name inside it (e.g. <dialog>) gets parsed and swallows what follows.
        self.assertNotContains(self.client.get(reverse('core:home')), '{#')

    def test_tab_bar_marks_the_current_page(self):
        home = self.client.get(reverse('core:home'))
        self.assertContains(home, 'tabbar__item is-active', count=1)
        self.assertContains(home, f'class="tabbar__item is-active" href="{reverse("core:home")}"')
        sport = self.client.get(reverse('catalog:sport'))
        self.assertContains(sport, f'class="tabbar__item is-active" href="{reverse("catalog:sport")}"')
        self.assertContains(sport, 'id="contact-sheet"')

    def test_empty_site_hides_empty_sections(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="hero')
        self.assertNotContains(response, 'id="offers"')
        self.assertNotContains(response, 'id="brands"')
        # The highlights strip doesn't depend on content; screen readers get each item once.
        self.assertContains(response, '<li>خرید قسطی از اسنپ پی</li>', count=1, html=True)

    def test_sections_get_the_right_content(self):
        HeroBanner.objects.create(title='بنر بالا', background_image='banners/top.jpg')
        HeroBanner.objects.create(title='بنر وسط', background_image='banners/mid.jpg', placement='middle')
        HeroBanner.objects.create(title='بنر خاموش', background_image='banners/off.jpg', is_active=False)
        brand = CarBrand.objects.create(name='سایپا', slug='سایپا')
        sale = Product.objects.create(
            name='محصول حراج', slug='sale', status='publish', regular_price=1000, sale_price=800,
        )
        best = Product.objects.create(
            name='محصول پرفروش', slug='best', status='publish', regular_price=500, total_sales=50,
        )
        Product.objects.create(
            name='محصول تمام‌شده', slug='out', status='publish', regular_price=1000, sale_price=500,
            stock_status='outofstock',
        )
        Product.objects.create(name='محصول پیش‌نویس', slug='draft', regular_price=1000, sale_price=500)
        Article.objects.create(
            title='مقاله منتشر شده', slug='a', body='متن', status='publish', published_at=timezone.now(),
        )

        response = self.client.get(reverse('core:home'))

        self.assertEqual(response.context['top_banner'].title, 'بنر بالا')
        self.assertEqual(response.context['middle_banner'].title, 'بنر وسط')
        self.assertEqual(list(response.context['sale_products']), [sale])
        self.assertEqual(list(response.context['popular_products']), [best, sale])
        self.assertContains(response, brand.get_absolute_url())
        self.assertContains(response, '۲۰٪')
        self.assertContains(response, '۸۰۰')
        self.assertContains(response, 'مقاله منتشر شده')
        self.assertNotContains(response, 'بنر خاموش')
        self.assertNotContains(response, 'محصول تمام‌شده')
        self.assertNotContains(response, 'محصول پیش‌نویس')


class SeedDemoCommandTests(TestCase):
    def test_seed_is_repeatable_and_clearable(self):
        call_command('seed_demo', stdout=StringIO())
        call_command('seed_demo', stdout=StringIO())
        self.assertEqual(Product.objects.count(), 30)
        self.assertEqual(Article.objects.count(), 8)
        self.assertEqual(self.client.get(reverse('core:home')).status_code, 200)

        call_command('seed_demo', clear=True, stdout=StringIO())
        self.assertFalse(Product.objects.exists())
        self.assertFalse(Article.objects.exists())
        self.assertFalse(HeroBanner.objects.exists())


class AdminPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from orders.models import Order, OrderAddress

        call_command('seed_demo', stdout=StringIO())
        order = Order.objects.create(status=Order.Status.PROCESSING, total_amount=1_500_000)
        OrderAddress.objects.create(order=order, address_type='billing', first_name='علی', last_name='رضایی')
        cls.admin_user = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'x')

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_dashboard_shows_store_summary_and_orders_first(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'پنل مدیریت اسپرت یدکی')
        self.assertContains(response, 'محصولات منتشرشده')
        self.assertContains(response, 'علی رضایی')
        self.assertContains(response, '۱٬۵۰۰٬۰۰۰')
        self.assertEqual(
            [app['app_label'] for app in response.context['app_list']][:4], ['orders', 'payments', 'cart', 'catalog'],
        )

    def test_dashboard_respects_permissions(self):
        staff = get_user_model().objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.context['dashboard']['cards'], [])
        self.assertIsNone(response.context['dashboard']['recent_orders'])

    def test_every_admin_list_and_form_renders(self):
        for model in admin.site._registry:
            opts = model._meta
            for view in ('changelist', 'add'):
                url = reverse(f'admin:{opts.app_label}_{opts.model_name}_{view}')
                with self.subTest(url=url):
                    self.assertIn(self.client.get(url).status_code, (200, 403))
        product = Product.objects.first()
        self.assertEqual(self.client.get(reverse('admin:catalog_product_change', args=[product.pk])).status_code, 200)
