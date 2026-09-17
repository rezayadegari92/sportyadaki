from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from catalog.models import Product
from core.models import CheckoutSuggestion, SiteSettings

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

    def test_free_shipping_progress_tracks_the_amount_threshold(self):
        self.settings.free_shipping_min_amount = Decimal('1000000')
        self.settings.save()

        quarter_way = self.totals_for((250_000, 1))
        self.assertEqual(quarter_way.free_shipping_percent, 25)

        self.cart.items.all().delete()
        self.assertEqual(self.totals_for((1_200_000, 1)).free_shipping_percent, 100)

    def test_progress_is_zero_while_the_amount_rule_is_off(self):
        self.assertEqual(self.totals_for((250_000, 1)).free_shipping_percent, 0)

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

    def test_checkout_suggestions_skip_what_is_in_the_cart_or_unbuyable(self):
        offered = make_product('offered')
        CheckoutSuggestion.objects.create(product=offered, position=1)
        CheckoutSuggestion.objects.create(product=self.sold_out, position=2)
        CheckoutSuggestion.objects.create(product=self.limited, position=3)
        CheckoutSuggestion.objects.create(product=make_product('paused'), position=4, is_active=False)
        self.add(self.limited, 1)  # already in the cart, so it drops off the rail

        suggestions = self.client.get(reverse('cart:detail')).context['suggestions']
        self.assertEqual(suggestions, [offered])

    def test_suggestion_can_be_added_without_leaving_the_cart(self):
        offered = make_product('offered')
        CheckoutSuggestion.objects.create(product=offered)
        reopened = reverse('cart:detail') + '?suggest=1'

        response = self.client.post(reverse('cart:add', args=[offered.pk]), {'quantity': 1, 'next': reopened})
        self.assertRedirects(response, reopened)
        self.assertTrue(CartItem.objects.filter(product=offered).exists())

    def test_checkout_button_opens_the_suggestion_sheet_only_when_there_is_one(self):
        self.add(self.limited, 1)
        without = self.client.get(reverse('cart:detail'))
        self.assertNotContains(without, 'suggest-sheet')

        CheckoutSuggestion.objects.create(product=make_product('offered'))
        with_sheet = self.client.get(reverse('cart:detail'))
        self.assertContains(with_sheet, 'data-sheet-open="suggest-sheet"')
        # The trigger stays a real link, so checkout is still reachable without JS.
        self.assertContains(with_sheet, f'href="{reverse("orders:checkout")}"')

    def test_sheet_reopens_after_adding_from_it(self):
        self.add(self.limited, 1)
        CheckoutSuggestion.objects.create(product=make_product('offered'))

        self.assertNotContains(self.client.get(reverse('cart:detail')), 'data-sheet-autoopen')
        self.assertContains(self.client.get(reverse('cart:detail'), {'suggest': '1'}), 'data-sheet-autoopen')

    def test_items_of_another_cart_are_not_reachable(self):
        self.add(self.limited, 1)
        item = CartItem.objects.get()
        stranger = Client()
        self.assertEqual(stranger.post(reverse('cart:remove', args=[item.pk])).status_code, 404)
        self.assertEqual(stranger.post(reverse('cart:update', args=[item.pk]), {'quantity': 2}).status_code, 404)
        self.assertTrue(CartItem.objects.filter(pk=item.pk).exists())
