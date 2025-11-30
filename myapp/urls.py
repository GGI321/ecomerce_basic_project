from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
  path('', views.home, name='home'),
    path('add_product/', views.add_product, name='add_product'),
    path('product_list/', views.product_list, name='product_list'),
    path('base/', views.base, name='base'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('product/<int:pk>/edit/', views.edit_product, name='edit_product'),
    path('product/<int:pk>/delete/', views.delete_product, name='delete_product'),
    path("search_suggest/", views.search_suggest, name="search_suggest"),
    path("cart/add/<int:pk>/", views.cart_add, name="cart_add"),
    path("cart/reduce/<int:pk>/", views.cart_reduce, name="cart_reduce"),
    path("cart/remove/<int:pk>/", views.cart_remove, name="cart_remove"),
    path("cart_count/", views.cart_count, name="cart_count"),
    path('product_detail/<int:pk>/', views.product_detail, name='product_detail'),
     path("checkout/", views.checkout, name="checkout"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    path("checkout/empty/", views.checkout_empty, name="checkout_empty"),
    
]