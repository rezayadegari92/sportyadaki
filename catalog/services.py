"""Picking products to offer alongside another one."""
from .models import Product

RELATED_LIMIT = 12


def related_products(product, limit=RELATED_LIMIT):
    """Published products to show next to `product`, closest match first.

    Matches are looked up in tiers — same category *and* car model, then same
    category, then same car model — and each tier only fills the slots the ones
    above it left empty, so a product whose category has few siblings still gets
    a full rail from its car model.
    """
    category_ids = list(product.categories.values_list('pk', flat=True))
    car_model_ids = list(product.car_models.values_list('pk', flat=True))

    tiers = []
    if category_ids and car_model_ids:
        tiers.append({'categories__in': category_ids, 'car_models__in': car_model_ids})
    if category_ids:
        tiers.append({'categories__in': category_ids})
    if car_model_ids:
        tiers.append({'car_models__in': car_model_ids})

    others = Product.objects.published().exclude(pk=product.pk).select_related('part_brand')
    found = {}
    for filters in tiers:
        for match in others.filter(**filters).distinct().popular()[:limit]:
            found.setdefault(match.pk, match)
        if len(found) >= limit:
            break
    return list(found.values())[:limit]
