from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Address
from cart.models import CartItem
from catalog.models import Product
from core.models import SiteSettings
from notifications.sms.console import ConsoleSMSService
from orders.models import Invoice, Order

from .models import Payment


@override_settings(PAYMENT_PLACEHOLDER_ALLOWED=True)
class CheckoutFlowTests(TestCase):
    def setUp(self):
        ConsoleSMSService.outbox.clear()
        site = SiteSettings.load()
        site.shipping_cost = Decimal('30000')
        site.save()
        self.user = get_user_model().objects.create_user(
            '09121234567', phone='09121234567', password='x', first_name='علی', last_name='رضایی',
        )
        self.address = Address.objects.create(
            user=self.user, title='خانه', recipient_name='علی رضایی', recipient_phone='09121234567',
            province='تهران', city='تهران', street='خیابان آزادی', postal_code='1234567890',
        )
        self.product = Product.objects.create(
            name='لنت ترمز', slug='lent', status=Product.Status.PUBLISHED, regular_price=100_000,
            manage_stock=True, stock_quantity=5,
        )
        self.client.force_login(self.user)
        self.client.post(reverse('cart:add', args=[self.product.pk]), {'quantity': 2})

    def checkout(self):
        return self.client.post(reverse('orders:checkout'), {'address': self.address.pk})

    def pay(self, result):
        payment = Payment.objects.filter(status=Payment.Status.INITIATED).latest('created_at')
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.get(reverse('payments:callback'), {'authority': payment.authority, 'result': result})

    def test_successful_payment_completes_the_order(self):
        response = self.checkout()
        self.assertEqual(response.status_code, 302)
        self.assertIn('/payment/simulator/', response.url)
        self.assertEqual(self.client.get(response.url).status_code, 200)

        order = Order.objects.get()
        self.assertEqual((order.status, order.total_amount), (Order.Status.PENDING, Decimal('230000')))
        self.assertEqual(order.items.get().unit_price, Decimal('100000'))

        response = self.pay('success')
        self.assertRedirects(response, reverse('orders:checkout_result', args=[order.pk]), fetch_redirect_response=False)
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual((self.product.stock_quantity, self.product.total_sales), (3, 2))
        invoice = Invoice.objects.get(order=order)
        self.assertEqual((invoice.total, invoice.shipping, invoice.customer_name), (Decimal('230000'), Decimal('30000'), 'علی رضایی'))
        self.assertTrue(invoice.number.startswith('INV-'))
        self.assertFalse(CartItem.objects.exists())
        self.assertTrue(any(phone == '09121234567' and 'پرداخت شد' in text for phone, text in ConsoleSMSService.outbox))
        self.assertContains(self.client.get(reverse('orders:checkout_result', args=[order.pk])), 'پرداخت با موفقیت انجام شد')

        # A repeated callback (refresh) doesn't deduct stock twice.
        payment = Payment.objects.get()
        self.client.get(reverse('payments:callback'), {'authority': payment.authority, 'result': 'success'})
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)

    def test_failed_payment_keeps_stock_and_cart_and_can_be_retried(self):
        self.checkout()
        self.pay('failed')
        order = Order.objects.get()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.FAILED)
        self.assertEqual(self.product.stock_quantity, 5)
        self.assertTrue(CartItem.objects.exists())
        self.assertFalse(Invoice.objects.exists())

        response = self.client.post(reverse('payments:pay_order', args=[order.pk]))
        self.assertIn('/payment/simulator/', response.url)
        self.pay('success')
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payments.count(), 2)

    def test_checkout_is_blocked_when_stock_ran_out(self):
        Product.objects.filter(pk=self.product.pk).update(stock_quantity=1)
        response = self.checkout()
        self.assertRedirects(response, reverse('cart:detail'), fetch_redirect_response=False)
        self.assertFalse(Order.objects.exists())

    def test_checkout_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('orders:checkout'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_other_customers_orders_cannot_be_paid_or_viewed(self):
        self.checkout()
        order = Order.objects.get()
        other = get_user_model().objects.create_user('09350000000', phone='09350000000', password='x')
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse('payments:pay_order', args=[order.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('orders:checkout_result', args=[order.pk])).status_code, 404)


@override_settings(DEBUG=False, PAYMENT_PLACEHOLDER_ALLOWED=False)
class PlaceholderGatewaySafetyTests(TestCase):
    def test_placeholder_gateway_refuses_to_take_payments_in_production(self):
        user = get_user_model().objects.create_user('09121234567', phone='09121234567', password='x')
        address = Address.objects.create(
            user=user, title='خانه', recipient_name='علی', recipient_phone='09121234567',
            province='تهران', city='تهران', street='آزادی', postal_code='1234567890',
        )
        product = Product.objects.create(name='p', slug='p', status=Product.Status.PUBLISHED, regular_price=1000)
        self.client.force_login(user)
        self.client.post(reverse('cart:add', args=[product.pk]))

        response = self.client.post(reverse('orders:checkout'), {'address': address.pk})
        order = Order.objects.get()
        self.assertRedirects(response, reverse('accounts:order_detail', args=[order.pk]), fetch_redirect_response=False)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(Payment.objects.filter(status=Payment.Status.SUCCEEDED).exists())
        self.assertEqual(self.client.get(reverse('payments:simulator', args=['anything'])).status_code, 404)
