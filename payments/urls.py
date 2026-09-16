from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('orders/<int:pk>/pay/', views.pay_order, name='pay_order'),
    path('callback/', views.payment_callback, name='callback'),
    path('simulator/<str:authority>/', views.payment_simulator, name='simulator'),
]
