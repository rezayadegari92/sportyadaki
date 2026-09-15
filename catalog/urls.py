from django.urls import path

from . import views

app_name = 'catalog'

# `str` rather than `slug` converters: slugs are Persian. The /product/ and
# /brand/ prefixes match WooCommerce's defaults, so old links keep working.
urlpatterns = [
    path('product/<str:slug>/', views.product_detail, name='product_detail'),
    path('product/<str:slug>/rate/', views.rate_product, name='rate_product'),
    path('brand/<str:slug>/', views.car_brand_detail, name='car_brand'),
    path('brand/<str:brand_slug>/<str:slug>/', views.car_model_detail, name='car_model'),
    path('sport/', views.parts_browser, {'kind': 'sport'}, name='sport'),
    path('accessories/', views.parts_browser, {'kind': 'accessory'}, name='accessories'),
]
