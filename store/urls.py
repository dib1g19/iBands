from django.urls import path
from store import views

app_name = "store"

urlpatterns = [
    path("", views.index, name="index"),
    path("shop/", views.shop, name="shop"),
    path("categories/<slug:parent_slug>/<slug:slug>/all/", views.category_all_sub, name="category_all_sub"),
    path("categories/<slug:slug>/all/", views.category_all_sub_root, name="category_all_sub_root"),
    path("categories/<slug:parent_slug>/<slug:slug>/", views.category, name="category"),
    path("categories/<slug:slug>/", views.category, name="category_root"),
    path("products/<slug:category_slug>/<slug:product_slug>/", views.product_detail, name="product_detail_root"),
    path("products/<slug:parent_slug>/<slug:category_slug>/<slug:product_slug>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart, name="cart"),
    path("create_order/", views.create_order, name="create_order"),
    path("checkout/<order_id>/", views.checkout, name="checkout"),
    path("coupon_apply/<order_id>/", views.coupon_apply, name="coupon_apply"),
    path("payment_status/<order_id>/", views.payment_status, name="payment_status"),
    path("cod_payment/<order_id>/", views.cod_payment, name="cod_payment"),

    path("filter_products/", views.filter_products, name="filter_products"),
    path("add_to_cart/", views.add_to_cart, name="add_to_cart"),
    path("delete_cart_item/", views.delete_cart_item, name="delete_cart_item"),

    path('stripe_payment/<order_id>/', views.stripe_payment, name='stripe_payment'),
    path('stripe_payment_verify/<order_id>/', views.stripe_payment_verify, name='stripe_payment_verify'),
    path('paypal_payment_verify/<order_id>/', views.paypal_payment_verify, name='paypal_payment_verify'),
    path('razorpay_payment_verify/<order_id>/', views.razorpay_payment_verify, name='razorpay_payment_verify'),
    path('paystack_payment_verify/<order_id>/', views.paystack_payment_verify, name='paystack_payment_verify'),
    path('flutterwave_payment_callback/<order_id>/', views.flutterwave_payment_callback, name='flutterwave_payment_callback'),

    path("order_tracker_page/", views.order_tracker_page, name="order_tracker_page"),

    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("faqs/", views.faqs, name="faqs"),
    path("privacy_policy/", views.privacy_policy, name="privacy_policy"),
    path("terms_conditions/", views.terms_conditions, name="terms_conditions"),
    path('returns-and-exchanges/', views.returns_and_exchanges, name='returns_and_exchanges'),
]