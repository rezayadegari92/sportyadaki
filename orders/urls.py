from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),
    path('checkout/result/<int:pk>/', views.checkout_result, name='checkout_result'),
    path('track/', views.track_order, name='track'),
]
