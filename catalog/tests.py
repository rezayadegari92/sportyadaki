from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CarBrand, CarModel, Product, ProductRating


def make_product(slug, *car_models, status=Product.Status.PUBLISHED, **fields):
    product = Product.objects.create(name=fields.pop('name', slug), slug=slug, status=status, **fields)
    product.car_models.add(*car_models)
    return product


class ProductKindQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        saipa = CarBrand.objects.create(name='سایپا', slug='saipa')
        cls.pride = CarModel.objects.create(name='پراید', slug='pride', brand=saipa)
        cls.tiba = CarModel.objects.create(name='تیبا', slug='tiba', brand=saipa)

        cls.universal = make_product('universal', sport=True)
        cls.pride_only = make_product('pride-only', cls.pride, sport=True)
        cls.both = make_product('both', cls.pride, cls.tiba, sport=True)
        cls.accessory = make_product('accessory', cls.pride, accessory=True)
        cls.draft = make_product('draft', sport=True, status=Product.Status.DRAFT)

    def sport(self):
        return Product.objects.published().of_kind('sport')

    def test_kind_is_independent_of_car_models(self):
        self.assertCountEqual(self.sport(), [self.universal, self.pride_only, self.both])
        self.assertQuerySetEqual(Product.objects.published().of_kind('accessory'), [self.accessory])

    def test_universal_parts_have_no_car_model(self):
        self.assertQuerySetEqual(self.sport().universal(), [self.universal])

    def test_model_filter_includes_multi_model_parts_once(self):
        self.assertCountEqual(self.sport().for_car_model(self.pride), [self.pride_only, self.both])
        self.assertCountEqual(self.sport().for_car_model(self.tiba), [self.both])

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            Product.objects.of_kind('status')

    def test_blank_skus_do_not_collide(self):
        Product.objects.create(name='a', slug='a', sku='')
        Product.objects.create(name='b', slug='b', sku='')


class ProductPriceTests(TestCase):
    def test_sale_price_applies_only_inside_window(self):
        now = timezone.now()
        product = Product(regular_price=Decimal('1000'), sale_price=Decimal('800'))
        self.assertEqual(product.price, Decimal('800'))

        product.sale_starts_at = now + timedelta(days=1)
        self.assertFalse(product.is_on_sale)
        self.assertEqual(product.price, Decimal('1000'))

        product.sale_starts_at, product.sale_ends_at = None, now - timedelta(days=1)
        self.assertFalse(product.is_on_sale)

    def test_sale_price_not_below_regular_is_ignored(self):
        product = Product(regular_price=Decimal('1000'), sale_price=Decimal('1000'))
        self.assertFalse(product.is_on_sale)

    def test_discount_percent(self):
        self.assertEqual(Product(regular_price=Decimal('1000'), sale_price=Decimal('750')).discount_percent, 25)
        self.assertEqual(Product(regular_price=Decimal('1000')).discount_percent, 0)
        self.assertEqual(Product(sale_price=Decimal('750')).discount_percent, 0)

    def test_on_sale_queryset_and_effective_price_agree_with_properties(self):
        now = timezone.now()
        cases = {
            'plain': {'regular_price': 1000},
            'sale': {'regular_price': 1000, 'sale_price': 800},
            'no-regular': {'sale_price': 800},
            'not-cheaper': {'regular_price': 1000, 'sale_price': 1000},
            'future': {'regular_price': 1000, 'sale_price': 800, 'sale_starts_at': now + timedelta(days=1)},
            'expired': {'regular_price': 1000, 'sale_price': 800, 'sale_ends_at': now - timedelta(days=1)},
            'running': {
                'regular_price': 1000, 'sale_price': 800,
                'sale_starts_at': now - timedelta(days=1), 'sale_ends_at': now + timedelta(days=1),
            },
        }
        for slug, fields in cases.items():
            Product.objects.create(name=slug, slug=slug, **fields)

        expected = {p.slug for p in Product.objects.all() if p.is_on_sale}
        self.assertEqual(expected, {'sale', 'no-regular', 'running'})
        self.assertEqual(set(Product.objects.on_sale().values_list('slug', flat=True)), expected)
        for product in Product.objects.with_effective_price():
            self.assertEqual(product.effective_price, product.price, product.slug)


class CatalogPageTests(TestCase):
    def test_product_page_hides_drafts(self):
        live = Product.objects.create(name='فیلتر هوا', slug='فیلتر-هوا', status='publish')
        draft = Product.objects.create(name='پیش‌نویس', slug='draft')
        response = self.client.get(live.get_absolute_url())
        self.assertContains(response, 'فیلتر هوا')
        self.assertContains(response, 'مناسب همه خودروها')
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)

    def test_car_brand_page_shows_its_car_models_not_products(self):
        brand = CarBrand.objects.create(name='سایپا', slug='سایپا')
        pride = CarModel.objects.create(name='پراید', slug='پراید', brand=brand)
        CarModel.objects.create(name='تیبا', slug='تیبا', brand=brand)
        other_brand = CarBrand.objects.create(name='ایران خودرو', slug='ikco')
        CarModel.objects.create(name='دنا', slug='dena', brand=other_brand)
        make_product('lent', pride, name='لنت پراید')
        make_product('draft', pride, status=Product.Status.DRAFT)

        response = self.client.get(brand.get_absolute_url())
        counts = {car_model.name: car_model.product_count for car_model in response.context['car_models']}
        self.assertEqual(counts, {'پراید': 1, 'تیبا': 0})
        self.assertContains(response, pride.get_absolute_url())
        self.assertNotContains(response, 'لنت پراید')
        self.assertNotContains(response, 'دنا')

    def test_car_model_page_lists_its_products(self):
        brand = CarBrand.objects.create(name='سایپا', slug='سایپا')
        pride = CarModel.objects.create(name='پراید', slug='پراید', brand=brand)
        make_product('lent', pride, name='لنت پراید', sport=True)
        make_product('universal', name='خوشبوکننده عمومی', sport=True)

        response = self.client.get(pride.get_absolute_url())
        self.assertContains(response, 'لنت پراید')
        self.assertNotContains(response, 'خوشبوکننده عمومی')
        self.assertEqual((response.context['sport_count'], response.context['accessory_count']), (1, 0))

        CarBrand.objects.create(name='چری', slug='chery')
        self.assertEqual(self.client.get(reverse('catalog:car_model', args=['chery', 'پراید'])).status_code, 404)


class PartsBrowserPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        saipa = CarBrand.objects.create(name='سایپا', slug='saipa')
        cls.pride = CarModel.objects.create(name='پراید', slug='پراید', brand=saipa)
        make_product('p1', name='اسپویلر عمومی', sport=True, regular_price=500)
        make_product('p2', cls.pride, name='فنر اسپرت مخصوص', sport=True, regular_price=900, sale_price=300)
        make_product('p3', cls.pride, name='روکش صندلی مخصوص', accessory=True)
        make_product('p4', name='اگزوز پیش‌نویس', sport=True, status=Product.Status.DRAFT)

    def names(self, response):
        return [product.name for product in response.context['page'].object_list]

    def test_universal_products_are_shown_before_a_car_is_picked(self):
        response = self.client.get(reverse('catalog:sport'))
        self.assertEqual(self.names(response), ['اسپویلر عمومی'])
        self.assertContains(response, 'پراید')  # the car picker lists the model

    def test_picking_a_car_model_shows_its_products_of_that_kind(self):
        response = self.client.get(reverse('catalog:sport'), {'model': 'پراید'})
        self.assertEqual(self.names(response), ['فنر اسپرت مخصوص'])
        response = self.client.get(reverse('catalog:accessories'), {'model': 'پراید'})
        self.assertEqual(self.names(response), ['روکش صندلی مخصوص'])

    def test_all_search_and_sort(self):
        url = reverse('catalog:sport')
        self.assertCountEqual(
            self.names(self.client.get(url, {'all': '1'})), ['اسپویلر عمومی', 'فنر اسپرت مخصوص'],
        )
        self.assertEqual(self.names(self.client.get(url, {'all': '1', 'q': 'فنر'})), ['فنر اسپرت مخصوص'])
        # Sorting uses the sale price while a sale runs: 300 before 500.
        self.assertEqual(
            self.names(self.client.get(url, {'all': '1', 'sort': 'cheapest'})),
            ['فنر اسپرت مخصوص', 'اسپویلر عمومی'],
        )
        self.assertEqual(self.names(self.client.get(url, {'all': '1', 'on_sale': '1'})), ['فنر اسپرت مخصوص'])

    def test_unknown_car_model_is_404(self):
        self.assertEqual(self.client.get(reverse('catalog:sport'), {'model': 'nope'}).status_code, 404)


class ProductRatingTests(TestCase):
    def setUp(self):
        self.product = make_product('filter', name='فیلتر روغن', regular_price=100)
        self.url = reverse('catalog:rate_product', args=[self.product.slug])

    def summary(self):
        self.product.refresh_from_db()
        return self.product.rating_count, self.product.average_rating

    def test_each_visitor_has_one_rating_they_can_change(self):
        self.client.post(self.url, {'stars': 4})
        self.assertEqual(self.summary(), (1, Decimal('4.00')))
        self.client.post(self.url, {'stars': 2})
        self.assertEqual(self.summary(), (1, Decimal('2.00')))
        Client().post(self.url, {'stars': 5})
        self.assertEqual(self.summary(), (2, Decimal('3.50')))

    def test_logged_in_rating_belongs_to_the_user(self):
        user = get_user_model().objects.create_user('ali', password='x')
        self.client.force_login(user)
        self.client.post(self.url, {'stars': 5})
        self.client.post(self.url, {'stars': 3})
        rating = ProductRating.objects.get()
        self.assertEqual((rating.user, rating.stars), (user, 3))

    def test_invalid_requests_change_nothing(self):
        for data in ({'stars': 0}, {'stars': 6}, {'stars': 'abc'}, {}):
            response = self.client.post(self.url, data)
            self.assertRedirects(response, f'{self.product.get_absolute_url()}#rating', fetch_redirect_response=False)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        draft = make_product('draft', status=Product.Status.DRAFT)
        self.assertEqual(self.client.post(reverse('catalog:rate_product', args=['draft']), {'stars': 5}).status_code, 404)
        self.assertFalse(ProductRating.objects.exists())
        self.assertEqual(draft.rating_count, 0)

    def test_deleting_ratings_updates_the_average(self):
        ProductRating.objects.create(product=self.product, stars=5, session_key='a')
        ProductRating.objects.create(product=self.product, stars=1, session_key='b')
        self.assertEqual(self.summary(), (2, Decimal('3.00')))
        ProductRating.objects.filter(stars=5).delete()  # like the admin's bulk delete
        self.assertEqual(self.summary(), (1, Decimal('1.00')))

    def test_average_is_shown_on_cards_and_product_page(self):
        self.client.post(self.url, {'stars': 4})
        Client().post(self.url, {'stars': 3})

        detail = self.client.get(self.product.get_absolute_url())
        self.assertEqual(detail.context['user_rating'], 4)
        self.assertContains(detail, 'aria-label="امتیاز ۳٫۵ از ۵"')
        self.assertContains(detail, 'width: 70.0%')
        self.assertContains(self.client.get(reverse('core:home')), 'aria-label="امتیاز ۳٫۵ از ۵"')
