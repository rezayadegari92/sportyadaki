from django.test import TestCase

from .models import Carrier, Order, OrderAddress


class OrderTrackingLookupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.order = Order.objects.create(
            status=Order.Status.PROCESSING, carrier=Carrier.TIPAX, tracking_code='TPX123',
        )
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

    def test_checkout_drafts_are_not_trackable(self):
        self.order.status = Order.Status.CHECKOUT_DRAFT
        self.order.save()
        self.assertIsNone(Order.objects.find_for_tracking(str(self.order.pk), '09391098198'))

    def test_tracking_url_follows_carrier(self):
        self.assertTrue(self.order.tracking_url)
        self.assertEqual(Order(carrier='').tracking_url, '')
