from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from orders.models import Carrier, Order

from .models import Address

User = get_user_model()
ADDRESS = {
    'title': 'خانه', 'recipient_name': 'علی رضایی', 'recipient_phone': '09121234567', 'province': 'تهران',
    'city': 'تهران', 'street': 'خیابان آزادی', 'plaque': '12', 'unit': '3', 'postal_code': '۱۲۳۴۵۶۷۸۹۰',
}


class RegistrationAndLoginTests(TestCase):
    def register(self, **overrides):
        data = {'phone': '۰۹۱۲ ۱۲۳ ۴۵۶۷', 'first_name': 'علی', 'last_name': 'رضایی',
                'password1': 'Kh0dro-Sport!', 'password2': 'Kh0dro-Sport!', **overrides}
        return self.client.post(reverse('accounts:register'), data)

    def test_register_normalizes_phone_and_signs_in(self):
        response = self.register()
        self.assertRedirects(response, reverse('accounts:dashboard'))
        user = User.objects.get()
        self.assertEqual((user.phone, user.username, user.get_full_name()), ('09121234567', '09121234567', 'علی رضایی'))
        self.assertContains(self.client.get(reverse('accounts:dashboard')), 'علی رضایی')

    def test_duplicate_phone_and_mismatched_passwords_are_rejected(self):
        self.register()
        self.client.logout()
        self.assertContains(self.register(phone='+989121234567'), 'قبلاً ثبت‌نام شده است')
        self.assertContains(self.register(phone='09350000000', password2='other'), 'رمزهای عبور یکسان نیستند')
        self.assertEqual(User.objects.count(), 1)

    def test_login_with_phone_in_any_format(self):
        User.objects.create_user('09121234567', phone='09121234567', password='Kh0dro-Sport!')
        response = self.client.post(reverse('accounts:login'), {'username': '+98 912 123 4567', 'password': 'Kh0dro-Sport!'})
        self.assertRedirects(response, reverse('accounts:dashboard'), fetch_redirect_response=False)
        self.client.logout()
        response = self.client.post(reverse('accounts:login'), {'username': '09121234567', 'password': 'wrong'})
        self.assertContains(response, 'شماره موبایل یا رمز عبور اشتباه است')

    def test_account_pages_require_login(self):
        for name in ('accounts:dashboard', 'accounts:addresses', 'accounts:orders'):
            response = self.client.get(reverse(name))
            self.assertIn(reverse('accounts:login'), response.url)


class AddressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('09121234567', phone='09121234567', password='x')
        self.client.force_login(self.user)

    def test_first_address_is_default_and_a_new_default_replaces_it(self):
        self.client.post(reverse('accounts:address_create'), ADDRESS)
        home = Address.objects.get()
        self.assertTrue(home.is_default)
        self.assertEqual(home.postal_code, '1234567890')
        self.client.post(reverse('accounts:address_create'), {**ADDRESS, 'title': 'محل کار', 'is_default': 'on'})
        self.assertEqual(list(Address.objects.filter(is_default=True).values_list('title', flat=True)), ['محل کار'])

        work = Address.objects.get(title='محل کار')
        self.client.post(reverse('accounts:address_delete', args=[work.pk]))
        home.refresh_from_db()
        self.assertTrue(home.is_default)

    def test_invalid_postcode_and_other_users_addresses(self):
        response = self.client.post(reverse('accounts:address_create'), {**ADDRESS, 'postal_code': '123'})
        self.assertContains(response, 'کد پستی باید ۱۰ رقم باشد')
        other = User.objects.create_user('09350000000', phone='09350000000', password='x')
        foreign = Address.objects.create(user=other, **{**ADDRESS, 'postal_code': '1234567890'})
        self.assertEqual(self.client.get(reverse('accounts:address_edit', args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('accounts:address_delete', args=[foreign.pk])).status_code, 404)


class OrderHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('09121234567', phone='09121234567', password='x')
        self.client.force_login(self.user)

    def test_customer_sees_own_orders_with_shipping_info(self):
        shipped = Order.objects.create(customer=self.user, status=Order.Status.SHIPPED, carrier=Carrier.TIPAX, tracking_code='TPX-42')
        pending = Order.objects.create(customer=self.user, status=Order.Status.PENDING)
        other = Order.objects.create(customer=User.objects.create_user('09350000000', phone='09350000000'))

        listing = self.client.get(reverse('accounts:orders'))
        self.assertEqual({order.pk for order in listing.context['page'].object_list}, {shipped.pk, pending.pk})
        self.assertContains(listing, 'TPX-42')

        detail = self.client.get(reverse('accounts:order_detail', args=[shipped.pk]))
        self.assertContains(detail, 'تیپاکس')
        self.assertContains(detail, 'TPX-42')
        self.assertNotContains(detail, reverse('payments:pay_order', args=[shipped.pk]))
        self.assertContains(self.client.get(reverse('accounts:order_detail', args=[pending.pk])), reverse('payments:pay_order', args=[pending.pk]))
        self.assertEqual(self.client.get(reverse('accounts:order_detail', args=[other.pk])).status_code, 404)

    def test_customers_have_no_way_to_cancel(self):
        order = Order.objects.create(customer=self.user, status=Order.Status.PAID)
        detail = self.client.get(reverse('accounts:order_detail', args=[order.pk]))
        self.assertNotContains(detail, 'cancel')
        self.assertContains(detail, 'برای لغو یا تغییر سفارش با پشتیبانی تماس بگیرید')
