from django.urls import path

from . import views

app_name = 'cart'

urlpatterns = [
    path('', views.cart_detail, name='detail'),
    path('add/<int:product_id>/', views.add_to_cart, name='add'),
    path('items/<int:pk>/update/', views.update_item, name='update'),
    path('items/<int:pk>/remove/', views.remove_item, name='remove'),
]
