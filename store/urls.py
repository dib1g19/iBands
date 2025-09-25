from django.urls import path
from store import views

app_name = "store"

urlpatterns = [
    path("", views.index, name="index"),
    path("band-of-the-week/", views.band_of_the_week, name="band_of_the_week"),
    path("band-of-the-week/history", views.band_of_the_week_history, name="band_of_the_week_history"),
    path("shop/", views.shop, name="shop"),
    path("sale/", views.sale, name="sale"),
    path("categories/<path:category_path>/all/", views.category_all_sub, name="category_all_sub"),
    path("categories/<path:category_path>/", views.category, name="category"),
    path("products/<path:category_path>/<slug:product_slug>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart, name="cart"),
    path("create-order/", views.create_order, name="create_order"),
    path("checkout/<order_id>/", views.checkout, name="checkout"),
    path("coupon-apply/<order_id>/", views.coupon_apply, name="coupon_apply"),
    path("payment-status/<order_id>/", views.payment_status, name="payment_status"),
    path("cod-payment/<order_id>/", views.cod_payment, name="cod_payment"),
    path("save-econt-address/<order_id>/", views.save_econt_address, name="save_econt_address"),
    path("save-speedy-address/<order_id>/", views.save_speedy_address, name="save_speedy_address"),
    path("speedy/find-sites/", views.speedy_find_sites, name="speedy_find_sites"),
    path("speedy/find-offices/", views.speedy_find_offices, name="speedy_find_offices"),
    path("speedy/quote/<order_id>/", views.speedy_quote, name="speedy_quote"),
    path("filter-products/", views.filter_products, name="filter_products"),
    path("add-to-cart/", views.add_to_cart, name="add_to_cart"),
    path("delete-cart-item/", views.delete_cart_item, name="delete_cart_item"),
    path("stripe-payment/<order_id>/", views.stripe_payment, name="stripe_payment"),
    path("stripe-payment-verify/<order_id>/", views.stripe_payment_verify, name="stripe_payment_verify"),
    path("order-tracker-page/", views.order_tracker_page, name="order_tracker_page"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("faqs/", views.faqs, name="faqs"),
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
    path("terms-conditions/", views.terms_conditions, name="terms_conditions"),
    path("returns-and-exchanges/", views.returns_and_exchanges, name="returns_and_exchanges"),
    path('subscribe-newsletter/', views.subscribe_newsletter, name='subscribe_newsletter'),
]
