from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse

from catalog.models import Product
from notifications.sms.console import ConsoleSMSService

from . import services
from .admin import OrderAdmin, OrderAdminForm
from .models import Carrier, Order, OrderAddress, OrderItem


def make_order(status=Order.Status.PENDING, phone='09391098198', **fields):
    order = Order.objects.create(status=status, total_amount=150_000, **fields)
    OrderAddress.objects.create(order=order, address_type='billing', phone=phone, first_name='علی')
    OrderAddress.objects.create(order=order, address_type='shipping', phone=phone, first_name='علی')
    return order


class OrderTrackingLookupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.order = Order.objects.create(status=Order.Status.PROCESSING, carrier=Carrier.TIPAX, tracking_code='TPX123')
        OrderAddress.objects.create(order=cls.order, address_type='billing', phone='0939 109 8198')
        OrderAddress.objects.create(order=cls.order, address_type='shipping', phone='09120000000')

    def test_matches_billing_phone_typed_differently(self):
        for phone in ('09391098198', '+98 939-109-8198', '۰۹۳۹۱۰۹۸۱۹۸', '9391098198'):
            with self.subTest(phone=phone):
                self.assertEqual(Order.objects.find_for_tracking(str(self.order.pk), phone), self.order)

    def test_matches_shipping_phone_and_persian_order_number(self):
        number = str(self.order.pk).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
        self.assertEqual(Order.objects.find_for_tracking(f'#{number}', '09120000000'), self.order)

    def test_wrong_phone_looks_like_missing_order(self):
        self.assertIsNone(Order.objects.find_for_tracking(str(self.order.pk), '09999999999'))
        self.assertIsNone(Order.objects.find_for_tracking('999999', '09391098198'))

    def test_rejects_garbage_input(self):
        self.assertIsNone(Order.objects.find_for_tracking('abc', '09391098198'))
        self.assertIsNone(Order.objects.find_for_tracking(str(self.order.pk), ''))

    def test_tracking_url_follows_carrier(self):
        self.assertTrue(self.order.tracking_url)
        self.assertEqual(Order(carrier=Carrier.COURIER).tracking_url, '')


class TrackOrderViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.order = make_order(Order.Status.SHIPPED, carrier=Carrier.POST, tracking_code='PST-778899')
        self.url = reverse('orders:track')

    def test_shows_status_and_shipment_for_matching_phone(self):
        response = self.client.post(self.url, {'order_number': self.order.pk, 'phone': '09391098198'})
        self.assertContains(response, 'ارسال شده')
        self.assertContains(response, 'PST-778899')
        self.assertContains(response, 'پست ایران')
        self.assertNotContains(response, 'علی')  # no personal details on the public page

    def test_homepage_sheet_gets_only_the_result_fragment(self):
        response = self.client.post(
            self.url, {'order_number': self.order.pk, 'phone': '09391098198'}, HTTP_X_REQUESTED_WITH='fetch',
        )
        self.assertContains(response, 'PST-778899')
        self.assertNotContains(response, '<html')

    def test_wrong_phone_and_attempt_limit(self):
        response = self.client.post(self.url, {'order_number': self.order.pk, 'phone': '09120000000'})
        self.assertContains(response, 'سفارشی با این شماره سفارش و موبایل پیدا نشد')
        self.assertNotContains(response, 'PST-778899')
        for _ in range(10):
            self.client.post(self.url, {'order_number': self.order.pk, 'phone': '09120000000'})
        response = self.client.post(self.url, {'order_number': self.order.pk, 'phone': '09391098198'})
        self.assertContains(response, 'تعداد تلاش‌ها زیاد بود')
        self.assertNotContains(response, 'PST-778899')

    def test_homepage_has_the_floating_tracking_button(self):
        response = self.client.get(reverse('core:home'))
        self.assertContains(response, 'class="fab"')
        self.assertContains(response, 'id="track-sheet"')


class StatusFlowTests(TestCase):
    def setUp(self):
        ConsoleSMSService.outbox.clear()
        self.product = Product.objects.create(
            name='دیسک', slug='disc', status=Product.Status.PUBLISHED, regular_price=50_000,
            manage_stock=True, stock_quantity=2,
        )
        self.order = make_order()
        OrderItem.objects.create(order=self.order, product=self.product, name='دیسک', quantity=2, unit_price=50_000, total=100_000)

    def test_paid_deducts_stock_once_and_marks_sold_out(self):
        services.mark_paid(self.order)
        services.mark_paid(self.order)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock_quantity, self.product.stock_status), (0, Product.StockStatus.OUT_OF_STOCK))
        self.assertTrue(Order.objects.get(pk=self.order.pk).stock_deducted)

    def test_only_allowed_transitions(self):
        order = services.mark_paid(self.order)
        with self.assertRaises(services.InvalidTransition):
            services.change_status(order, Order.Status.DELIVERED)  # must be prepared and shipped first
        order = services.change_status(order, Order.Status.PROCESSING)
        order = services.change_status(order, Order.Status.SHIPPED)
        order = services.change_status(order, Order.Status.DELIVERED)
        with self.assertRaises(services.InvalidTransition):
            services.change_status(order, Order.Status.CANCELLED)
        self.assertIsNotNone(order.completed_at)

    def test_cancelling_returns_stock_and_notifies(self):
        order = services.mark_paid(self.order)
        with self.captureOnCommitCallbacks(execute=True):
            services.change_status(order, Order.Status.CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock_quantity, self.product.stock_status), (2, Product.StockStatus.IN_STOCK))
        self.assertTrue(any('لغو شد' in text for _, text in ConsoleSMSService.outbox))


class OrderAdminTests(TestCase):
    def setUp(self):
        ConsoleSMSService.outbox.clear()
        self.superuser = get_user_model().objects.create_superuser('admin', 'a@example.com', 'x')
        self.order = services.mark_paid(make_order())
        self.order = services.change_status(self.order, Order.Status.PROCESSING)

    def test_status_choices_are_limited_to_the_flow(self):
        form = OrderAdminForm(instance=self.order)
        self.assertEqual({value for value, _ in form.fields['status'].choices}, {'processing', 'shipped', 'cancelled'})
        new_form = OrderAdminForm()
        self.assertEqual([value for value, _ in new_form.fields['status'].choices], ['pending'])

    def test_shipping_requires_a_carrier(self):
        form = OrderAdminForm(instance=self.order)
        form.cleaned_data = {'status': Order.Status.SHIPPED, 'carrier': ''}
        form._errors = {}
        form.clean()
        self.assertIn('carrier', form.errors)

    def test_saving_shipped_status_stores_tracking_first_and_texts_it(self):
        request = RequestFactory().post('/')
        request.user = self.superuser
        request.session = {}
        request._messages = FallbackStorage(request)
        obj = Order.objects.get(pk=self.order.pk)
        obj.carrier, obj.tracking_code, obj.status = Carrier.TIPAX, 'TPX-5555', Order.Status.SHIPPED
        with self.captureOnCommitCallbacks(execute=True):
            OrderAdmin(Order, admin.site).save_model(
                request, obj, SimpleNamespace(changed_data=['status', 'carrier', 'tracking_code']), change=True,
            )
        order = Order.objects.get(pk=self.order.pk)
        self.assertEqual((order.status, order.tracking_code), (Order.Status.SHIPPED, 'TPX-5555'))
        self.assertIsNotNone(order.shipped_at)
        self.assertTrue(any('TPX-5555' in text for _, text in ConsoleSMSService.outbox))
