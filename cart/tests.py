from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from catalog.models import Product
from core.models import SiteSettings

from .models import Cart, CartItem
from .services import calculate_totals


def make_product(slug, price=100_000, **fields):
    return Product.objects.create(name=slug, slug=slug, status=Product.Status.PUBLISHED, regular_price=price, **fields)


class ShippingAndTotalsTests(TestCase):
    def setUp(self):
        self.settings = SiteSettings.load()
        self.settings.shipping_cost = Decimal('50000')
        self.settings.save()
        self.cart = Cart.objects.create(session_key='s')

    def totals_for(self, *lines):
        for index, (price, quantity) in enumerate(lines):
            product = make_product(f'p{index}-{price}-{quantity}', price=price)
            CartItem.objects.create(cart=self.cart, product=product, quantity=quantity, unit_price=price)
        items = list(self.cart.items.select_related('product'))
        return calculate_totals(items, SiteSettings.load())

    def test_fixed_shipping_when_no_threshold_is_set(self):
        totals = self.totals_for((5_000_000, 10))
        self.assertEqual((totals.shipping, totals.total), (Decimal('50000'), Decimal('50050000')))

    def test_free_shipping_by_item_count_or_amount(self):
        self.settings.free_shipping_min_items = 3
        self.settings.free_shipping_min_amount = Decimal('1000000')
        self.settings.save()

        one_cheap = self.totals_for((200_000, 1))
        self.assertEqual(one_cheap.shipping, Decimal('50000'))
        self.assertEqual((one_cheap.items_to_free_shipping, one_cheap.amount_to_free_shipping), (2, Decimal('800000')))

        self.cart.items.all().delete()
        self.assertEqual(self.totals_for((100_000, 3)).shipping, 0)  # item count met
        self.cart.items.all().delete()
        expensive = self.totals_for((1_200_000, 1))  # amount met
        self.assertEqual(expensive.shipping, 0)
        self.assertTrue(expensive.free_shipping)

    def test_tax_rate_applies_to_subtotal(self):
        self.settings.tax_rate = Decimal('10')
        self.settings.save()
        totals = self.totals_for((100_000, 2))
        self.assertEqual((totals.tax, totals.total), (Decimal('20000'), Decimal('270000')))


class CartViewTests(TestCase):
    def setUp(self):
        self.limited = make_product('limited', manage_stock=True, stock_quantity=2)
        self.sold_out = make_product('sold-out', stock_status=Product.StockStatus.OUT_OF_STOCK)

    def add(self, product, quantity=1, client=None):
        return (client or self.client).post(reverse('cart:add', args=[product.pk]), {'quantity': quantity})

    def test_adding_is_capped_at_available_stock(self):
        self.add(self.limited, 5)
        item = CartItem.objects.get()
        self.assertEqual((item.quantity, item.unit_price), (2, Decimal('100000')))
        response = self.client.get(reverse('cart:detail'))
        self.assertContains(response, 'limited')

    def test_out_of_stock_products_cannot_be_added(self):
        response = self.add(self.sold_out)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CartItem.objects.exists())

    def test_session_cart_merges_into_user_cart_on_login(self):
        self.add(self.limited, 1)
        user = get_user_model().objects.create_user('09121234567', phone='09121234567', password='Str0ng-pass!')
        self.assertTrue(self.client.login(username='+98 912 123 4567', password='Str0ng-pass!'))
        cart = Cart.objects.get(user=user)
        self.assertEqual(list(cart.items.values_list('product__slug', 'quantity')), [('limited', 1)])
        self.assertFalse(Cart.objects.filter(user__isnull=True).exists())

    def test_items_of_another_cart_are_not_reachable(self):
        self.add(self.limited, 1)
        item = CartItem.objects.get()
        stranger = Client()
        self.assertEqual(stranger.post(reverse('cart:remove', args=[item.pk])).status_code, 404)
        self.assertEqual(stranger.post(reverse('cart:update', args=[item.pk]), {'quantity': 2}).status_code, 404)
        self.assertTrue(CartItem.objects.filter(pk=item.pk).exists())
