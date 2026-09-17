from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, F, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cart.services import available_quantity

from .models import CarBrand, CarModel, PartBrand, Product, ProductRating
from .services import related_products

PAGE_SIZE = 24

KIND_TITLES = {'sport': 'لوازم اسپرت', 'accessory': 'اکسسوری و لوازم جانبی'}

SORTS = {
    'newest': ('جدیدترین', ['-created_at']),
    'popular': ('محبوب‌ترین', ['-total_sales', '-average_rating']),
    'cheapest': ('ارزان‌ترین', [F('effective_price').asc(nulls_last=True)]),
    'expensive': ('گران‌ترین', [F('effective_price').desc(nulls_last=True)]),
}


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.published().select_related('part_brand'), slug=slug)
    user_rating = (
        product.ratings.for_visitor(request.user, request.session.session_key)
        .values_list('stars', flat=True)
        .first()
    )
    available = available_quantity(product)
    return render(request, 'catalog/product_detail.html', {
        'product': product,
        'can_buy': available != 0,
        'max_quantity': available,  # None: no stock limit
        'car_models': product.car_models.select_related('brand'),
        'related_products': related_products(product),
        'user_rating': user_rating,
        # Highest first: the star widget lays them out with row-reverse.
        'star_choices': [5, 4, 3, 2, 1],
    })


@require_POST
def rate_product(request, slug):
    product = get_object_or_404(Product.objects.published(), slug=slug)
    back = f'{product.get_absolute_url()}#rating'
    try:
        stars = int(request.POST.get('stars', ''))
    except ValueError:
        stars = 0
    if not 1 <= stars <= 5:
        messages.error(request, 'لطفاً امتیازی بین ۱ تا ۵ انتخاب کنید.')
        return redirect(back)

    if request.user.is_authenticated:
        visitor = {'user': request.user}
    else:
        # Visitors without an account are told apart by their session. An empty
        # session is never saved or sent as a cookie, so put something in it.
        request.session['has_rated'] = True
        if not request.session.session_key:
            request.session.save()
        visitor = {'user': None, 'session_key': request.session.session_key}

    ProductRating.objects.update_or_create(
        product=product, **visitor,
        defaults={'stars': stars, 'ip_address': request.META.get('REMOTE_ADDR') or None},
    )
    messages.success(request, 'امتیاز شما ثبت شد. ممنون!')
    return redirect(back)


def car_brand_detail(request, slug):
    """A brand's car models; picking one leads to that model's products."""
    brand = get_object_or_404(CarBrand, slug=slug)
    published = Q(products__status=Product.Status.PUBLISHED)
    return render(request, 'catalog/car_brand_detail.html', {
        'brand': brand,
        'car_models': brand.car_models.annotate(product_count=Count('products', filter=published)).order_by('name'),
    })


def car_model_detail(request, brand_slug, slug):
    car_model = get_object_or_404(CarModel.objects.select_related('brand'), slug=slug, brand__slug=brand_slug)
    products = Product.objects.published().for_car_model(car_model).select_related('part_brand')
    counts = products.aggregate(sport=Count('pk', filter=Q(sport=True)), accessory=Count('pk', filter=Q(accessory=True)))
    return render(request, 'catalog/car_model_detail.html', {
        'car_model': car_model,
        'brand': car_model.brand,
        'page': Paginator(products, PAGE_SIZE).get_page(request.GET.get('page')),
        'sport_count': counts['sport'],
        'accessory_count': counts['accessory'],
    })


def parts_browser(request, kind):
    """Sport or accessory products, narrowed by car model, search and filters.

    Until a car model is picked, universal parts (no car model) are listed, as
    on the WordPress site; `?all=1` lists every product of the kind.
    """
    of_kind = Product.objects.published().of_kind(kind)
    products = of_kind.select_related('part_brand')

    selected_model = None
    show_all = False
    if model_slug := request.GET.get('model'):
        selected_model = get_object_or_404(CarModel.objects.select_related('brand'), slug=model_slug)
        products = products.for_car_model(selected_model)
        fit_query = urlencode({'model': selected_model.slug})
    elif request.GET.get('all') == '1':
        show_all = True
        fit_query = 'all=1'
    else:
        products = products.universal()
        fit_query = ''

    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    part_brand = request.GET.get('brand', '')
    if part_brand:
        products = products.filter(part_brand__slug=part_brand)
    in_stock = request.GET.get('in_stock') == '1'
    if in_stock:
        products = products.exclude(stock_status=Product.StockStatus.OUT_OF_STOCK)
    on_sale = request.GET.get('on_sale') == '1'
    if on_sale:
        products = products.on_sale()
    sort = request.GET.get('sort')
    if sort not in SORTS:
        sort = 'newest'
    products = products.with_effective_price().order_by(*SORTS[sort][1], '-pk')

    in_kind = Q(products__status=Product.Status.PUBLISHED, **{f'products__{kind}': True})
    car_models = CarModel.objects.annotate(product_count=Count('products', filter=in_kind)).order_by('name')
    query = request.GET.copy()
    query.pop('page', None)

    return render(request, 'catalog/parts_browser.html', {
        'kind': kind,
        'title': KIND_TITLES[kind],
        'page': Paginator(products, PAGE_SIZE).get_page(request.GET.get('page')),
        'query_string': query.urlencode(),
        'brands': CarBrand.objects.prefetch_related(Prefetch('car_models', queryset=car_models)),
        'unbranded_models': car_models.filter(brand__isnull=True),
        'universal_count': of_kind.universal().count(),
        'all_count': of_kind.count(),
        'part_brands': PartBrand.objects.filter(products__in=of_kind).distinct(),
        'selected_model': selected_model,
        'show_all': show_all,
        'fit_query': fit_query,
        'q': q,
        'selected_part_brand': part_brand,
        'in_stock': in_stock,
        'on_sale': on_sale,
        'sort': sort,
        'sorts': [(key, label) for key, (label, _) in SORTS.items()],
        'has_filters': bool(q or part_brand or in_stock or on_sale or sort != 'newest'),
    })
