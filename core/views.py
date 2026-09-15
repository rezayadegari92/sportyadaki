from django.shortcuts import render

from articles.models import Article
from catalog.models import CarBrand, Product

from .models import HeroBanner

HOME_PRODUCT_LIMIT = 12
HOME_ARTICLE_LIMIT = 8

# Shown in the scrolling strip under the car brands. `icon` names an SVG in
# templates/includes/highlight_icon.html.
HOME_HIGHLIGHTS = [
    {'icon': 'truck', 'text': 'ارسال سریع'},
    {'icon': 'shield', 'text': 'اصالت کالا'},
    {'icon': 'installments', 'text': 'خرید قسطی از اسنپ پی'},
    {'icon': 'gift', 'text': 'همراه با اشانتیون'},
]


def home(request):
    banners = HeroBanner.objects.filter(is_active=True)
    products = (
        Product.objects.published()
        .exclude(stock_status=Product.StockStatus.OUT_OF_STOCK)
        .select_related('part_brand')
    )
    return render(request, 'core/home.html', {
        'top_banner': banners.filter(placement=HeroBanner.Placement.TOP).first(),
        'middle_banner': banners.filter(placement=HeroBanner.Placement.MIDDLE).first(),
        'car_brands': CarBrand.objects.all(),
        'highlights': HOME_HIGHLIGHTS,
        # Two identical groups make the loop seamless; each repeats the items
        # so a group is wider than the screen.
        'marquee_groups': [HOME_HIGHLIGHTS * 2] * 2,
        'sale_products': products.on_sale()[:HOME_PRODUCT_LIMIT],
        'popular_products': products.popular()[:HOME_PRODUCT_LIMIT],
        'articles': Article.objects.published().select_related('category')[:HOME_ARTICLE_LIMIT],
    })
