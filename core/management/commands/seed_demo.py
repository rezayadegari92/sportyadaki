"""Fill the database with sample products, articles and banners for development.

Safe to run repeatedly. `--clear` removes the sample products, articles and
banners again; the brands, car models and categories it created are left in
place since they are real data.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from articles.models import Article, ArticleCategory
from catalog.models import (
    CarBrand, CarModel, PartBrand, Product, ProductCategory, ProductRating, refresh_product_rating,
)
from core.models import HeroBanner

DEMO_PREFIX = 'demo-'

CAR_BRANDS = {
    'iran-khodro': ('ایران خودرو', [
        ('peugeot-206', 'پژو ۲۰۶'), ('peugeot-405', 'پژو ۴۰۵'), ('peugeot-pars', 'پژو پارس'),
        ('samand', 'سمند'), ('dena', 'دنا'), ('rana', 'رانا'), ('tara', 'تارا'),
    ]),
    'saipa': ('سایپا', [
        ('pride', 'پراید'), ('tiba', 'تیبا'), ('quick', 'کوییک'), ('shahin', 'شاهین'), ('saina', 'ساینا'),
    ]),
    'chery': ('چری', [('tiggo-7', 'تیگو ۷'), ('arrizo-5', 'آریزو ۵')]),
    'renault': ('رنو', [('tondar-90', 'تندر ۹۰'), ('sandero', 'ساندرو')]),
    'mvm': ('ام‌وی‌ام', [('mvm-x22', 'X22'), ('mvm-x33', 'X33')]),
    'fownix': ('فونیکس', [('fownix-fx', 'FX'), ('fownix-f7', 'F7 پرو مکس')]),
    'geely': ('جیلی', [('emgrand-7', 'امگرند ۷')]),
    'lamari': ('لاماری', [('lamari-eama', 'ایما')]),
    'dignity': ('دیگنیتی', [('dignity-prime', 'پرایم')]),
    'jac': ('جک', [('jac-j4', 'J4'), ('jac-s5', 'S5')]),
    'lifan': ('لیفان', [('lifan-x60', 'X60')]),
    'haima': ('هایما', [('haima-s5', 'هایما S5'), ('haima-s7', 'هایما S7')]),
}

CATEGORIES = [
    ('brake-clutch', 'ترمز و کلاچ'),
    ('engine', 'قطعات موتوری'),
    ('suspension', 'جلوبندی و تعلیق'),
    ('electrical', 'برق و روشنایی'),
    ('filter-oil', 'فیلتر و روغن'),
    ('body', 'بدنه و تزئینات'),
]

PART_BRANDS = [
    ('bosch', 'بوش'), ('ngk', 'NGK'), ('monroe', 'مونرو'), ('continental', 'کانتیننتال'),
    ('valeo', 'ولئو'), ('sachs', 'ساکس'), ('kn', 'K&N'), ('mann', 'مان فیلتر'),
]


def item(name, categories, part_brand, car_models, price, sale=None,
         stock=Product.StockStatus.IN_STOCK, sport=False, accessory=False):
    return {
        'name': name, 'categories': categories, 'part_brand': part_brand, 'car_models': car_models,
        'price': price, 'sale': sale, 'stock': stock, 'sport': sport, 'accessory': accessory,
    }


# An empty car model list means a universal part.
PRODUCTS = [
    item('لنت ترمز جلو سرامیکی پژو ۲۰۶', ['brake-clutch'], 'bosch', ['peugeot-206'], 1_450_000, 1_190_000),
    item('دیسک ترمز اسپرت شیاردار پژو ۴۰۵', ['brake-clutch'], None, ['peugeot-405', 'peugeot-pars'], 3_200_000, 2_690_000, sport=True),
    item('شمع ایریدیوم NGK بسته ۴ عددی', ['engine'], 'ngk', [], 2_800_000),
    item('فیلتر هوای اسپرت K&N', ['filter-oil'], 'kn', ['peugeot-206', 'peugeot-405', 'samand'], 4_900_000, 4_150_000, sport=True),
    item('کمک فنر جلو گازی مونرو پراید', ['suspension'], 'monroe', ['pride', 'tiba'], 2_350_000),
    item('تسمه تایم کانتیننتال پژو ۴۰۵', ['engine'], 'continental', ['peugeot-405', 'peugeot-pars', 'samand'], 1_180_000),
    item('کیت کلاچ ولئو دنا', ['brake-clutch'], 'valeo', ['dena'], 6_700_000, 5_990_000),
    item('لامپ LED هدلایت H4', ['electrical'], None, [], 1_650_000, 1_290_000, accessory=True),
    item('روکش صندلی چرمی طرح اسپرت تیبا', ['body'], None, ['tiba'], 5_400_000, accessory=True),
    item('رینگ اسپرت ۱۵ اینچ طرح BBS', ['body'], None, [], 18_500_000, 16_900_000, sport=True),
    item('اگزوز اسپرت استیل دوقلو', ['engine'], None, [], 7_800_000, sport=True),
    item('پدال اسپرت آلومینیومی', ['body'], None, [], 890_000, 690_000, sport=True, accessory=True),
    item('سر دنده اسپرت چرمی', ['body'], None, [], 750_000, sport=True, accessory=True),
    item('فیلتر روغن مان پژو ۲۰۶', ['filter-oil'], 'mann', ['peugeot-206', 'rana'], 320_000),
    item('روغن موتور 10W40 چهار لیتری', ['filter-oil'], None, [], 1_950_000, 1_750_000),
    item('باتری ۶۰ آمپر ساعت', ['electrical'], 'bosch', [], 4_600_000, stock=Product.StockStatus.OUT_OF_STOCK),
    item('سنسور اکسیژن بوش سمند', ['electrical', 'engine'], 'bosch', ['samand', 'dena'], 2_100_000),
    item('واتر پمپ پژو پارس', ['engine'], None, ['peugeot-pars', 'peugeot-405'], 1_380_000),
    item('لنت ترمز عقب کوییک', ['brake-clutch'], None, ['quick'], 890_000),
    item('کمک فنر عقب ساکس تارا', ['suspension'], 'sachs', ['tara'], 3_250_000, 2_900_000),
    item('اسپویلر عقب تیبا', ['body'], None, ['tiba'], 2_200_000, sport=True, accessory=True),
    item('آینه بغل برقی شاهین', ['electrical'], None, ['shahin'], 3_700_000, stock=Product.StockStatus.ON_BACKORDER),
    item('فیلتر کابین جک J4', ['filter-oil'], 'mann', ['jac-j4'], 480_000),
    item('لنت ترمز جلو چری تیگو ۷', ['brake-clutch'], 'bosch', ['tiggo-7'], 2_650_000, 2_250_000),
    item('شمع موتور هایما S5', ['engine'], 'ngk', ['haima-s5', 'haima-s7'], 1_900_000),
    item('کفپوش سه‌بعدی ام‌وی‌ام X22', ['body'], None, ['mvm-x22', 'mvm-x33'], 2_400_000, accessory=True),
    item('چراغ مه‌شکن LED فونیکس FX', ['electrical'], None, ['fownix-fx'], 2_950_000, accessory=True),
    item('فیلتر هوای رنو تندر ۹۰', ['filter-oil'], 'mann', ['tondar-90', 'sandero'], 520_000, 450_000),
    item('مانیتور اندروید ۹ اینچ خودرو', ['electrical'], None, [], 8_900_000, 7_900_000, accessory=True),
    item('فنر کوتاه اسپرت پراید', ['suspension'], None, ['pride', 'saina'], 4_300_000, sport=True),
]

ARTICLE_CATEGORIES = [('iran-khodro', 'ایران خودرو'), ('saipa', 'سایپا'), ('chinese-cars', 'خودروهای چینی')]

ARTICLES = [
    ('راهنمای تعویض لنت ترمز پژو ۲۰۶', 'iran-khodro', 4),
    ('مقایسه شمع ایریدیوم و پلاتینیوم؛ کدام بهتر است؟', None, 6),
    ('تسمه تایم را چه زمانی باید عوض کنیم؟', 'iran-khodro', 5),
    ('آیا فیلتر هوای اسپرت قدرت موتور را بیشتر می‌کند؟', None, 7),
    ('علائم خرابی کمک فنر در پراید و تیبا', 'saipa', 3),
    ('نگهداری خودرو در فصل زمستان', None, 8),
    ('قطعات پرمصرف چری تیگو ۷ را بشناسید', 'chinese-cars', 5),
    ('راهنمای انتخاب رینگ اسپرت مناسب', None, 9),
]

PARAGRAPH = (
    'انتخاب قطعه مناسب تاثیر مستقیمی بر ایمنی و عمر خودرو دارد. پیش از خرید، مدل و سال ساخت خودرو را بررسی کنید '
    'و از اصالت کالا مطمئن شوید. استفاده از قطعات باکیفیت هزینه‌های تعمیرات بعدی را کاهش می‌دهد و رانندگی '
    'راحت‌تری را برای شما فراهم می‌کند. در صورت تردید، پیش از نصب با کارشناسان ما مشورت کنید.'
)


def banners():
    sport_url, accessories_url = reverse('catalog:sport'), reverse('catalog:accessories')
    return [
        {
            'placement': HeroBanner.Placement.TOP,
            # The top banner artwork has the car on the right, so the text goes left.
            'content_side': HeroBanner.ContentSide.LEFT,
            'title': 'لوازم اسپرت و اکسسوری خودرو',
            'subtitle': 'قطعات اسپرت اورجینال برای خودروهای ایرانی و چینی با ارسال به سراسر کشور',
            'primary_cta_label': 'مشاهده لوازم اسپرت', 'primary_cta_url': sport_url,
            'secondary_cta_label': 'برندهای خودرو', 'secondary_cta_url': '#brands',
        },
        {
            'placement': HeroBanner.Placement.MIDDLE,
            'title': 'لوازم اسپرت و اکسسوری مخصوص خودروی شما',
            'subtitle': 'برند و مدل خودرو را انتخاب کنید و قطعات مناسب آن را ببینید',
            'primary_cta_label': 'لوازم اسپرت', 'primary_cta_url': sport_url,
            'secondary_cta_label': 'اکسسوری', 'secondary_cta_url': accessories_url,
        },
    ]


class Command(BaseCommand):
    help = 'Create sample products, articles and banners for development.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete the sample products, articles and banners instead of creating them.',
        )

    @transaction.atomic
    def handle(self, *args, clear=False, **options):
        if clear:
            products, _ = Product.objects.filter(slug__startswith=DEMO_PREFIX).delete()
            articles, _ = Article.objects.filter(slug__startswith=DEMO_PREFIX).delete()
            banner_count, _ = HeroBanner.objects.filter(title__in=[b['title'] for b in banners()]).delete()
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {products} products/relations, {articles} articles, {banner_count} banners.'
            ))
            return

        categories = {
            slug: ProductCategory.objects.get_or_create(slug=slug, defaults={'name': name})[0]
            for slug, name in CATEGORIES
        }
        part_brands = {
            slug: PartBrand.objects.get_or_create(slug=slug, defaults={'name': name})[0]
            for slug, name in PART_BRANDS
        }
        car_models = {}
        for position, (brand_slug, (brand_name, models)) in enumerate(CAR_BRANDS.items()):
            brand, _ = CarBrand.objects.get_or_create(
                slug=brand_slug, defaults={'name': brand_name, 'position': position},
            )
            for model_slug, model_name in models:
                car_models[model_slug], _ = CarModel.objects.get_or_create(
                    slug=model_slug, defaults={'name': model_name, 'brand': brand},
                )

        now = timezone.now()
        for i, data in enumerate(PRODUCTS, start=1):
            product, _ = Product.objects.update_or_create(slug=f'{DEMO_PREFIX}{i:02d}', defaults={
                'name': data['name'],
                'status': Product.Status.PUBLISHED,
                'sku': f'DEMO-{i:04d}',
                'short_description': f'<p>{data["name"]} با کیفیت اصلی و ضمانت اصالت کالا.</p>',
                'description': f'<p>{PARAGRAPH}</p><p>{PARAGRAPH}</p>',
                'regular_price': data['price'],
                'sale_price': data['sale'],
                'stock_status': data['stock'],
                'sport': data['sport'],
                'accessory': data['accessory'],
                'part_brand': part_brands.get(data['part_brand']),
                'total_sales': (i * 37) % 180,
                'created_at': now - timedelta(days=i),
            })
            product.categories.set([categories[slug] for slug in data['categories']])
            product.car_models.set([car_models[slug] for slug in data['car_models']])
            # 0–8 anonymous ratings of 3–5 stars; the product's average follows from them.
            for k in range((i * 7) % 9):
                ProductRating.objects.update_or_create(
                    product=product, user=None, session_key=f'{DEMO_PREFIX}{k}',
                    defaults={'stars': 3 + (i + k) % 3},
                )
            refresh_product_rating(product.pk)

        article_categories = {
            slug: ArticleCategory.objects.get_or_create(slug=slug, defaults={'name': name})[0]
            for slug, name in ARTICLE_CATEGORIES
        }
        for i, (title, category, paragraphs) in enumerate(ARTICLES, start=1):
            Article.objects.update_or_create(slug=f'{DEMO_PREFIX}{i:02d}', defaults={
                'title': title,
                'category': article_categories.get(category),
                'excerpt': PARAGRAPH[:150],
                'body': ''.join(f'<p>{PARAGRAPH}</p>' for _ in range(paragraphs * 4)),
                'status': Article.Status.PUBLISHED,
                'published_at': now - timedelta(days=i * 3),
            })

        for position, banner in enumerate(banners()):
            HeroBanner.objects.update_or_create(title=banner['title'], defaults={**banner, 'position': position})

        self.stdout.write(self.style.SUCCESS(
            f'{len(PRODUCTS)} products, {len(ARTICLES)} articles, {len(banners())} banners, '
            f'{len(CAR_BRANDS)} car brands with {len(car_models)} models.'
        ))
