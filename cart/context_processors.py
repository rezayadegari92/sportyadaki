from .services import get_cart, item_count


def cart(request):
    return {'cart_count': item_count(get_cart(request))}
