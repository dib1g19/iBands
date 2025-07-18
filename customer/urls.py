from django.urls import path
from customer import views

app_name = "customer"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("order-detail/<order_id>/", views.order_detail, name="order_detail"),
    path("wishlist/", views.wishlist, name="wishlist"),
    path("remove-from-wishlist/<id>/", views.remove_from_wishlist, name="remove_from_wishlist"),
    path("toggle-wishlist/<int:id>/", views.toggle_wishlist, name="toggle_wishlist"),
    path("addresses/", views.addresses, name="addresses"),
    path("notis/", views.notis, name="notis"),
    path("mark-noti-seen/<id>/", views.mark_noti_seen, name="mark_noti_seen"),
    path("address-detail/<id>/", views.address_detail, name="address_detail"),
    path("address-create/", views.address_create, name="address_create"),
    path("set-main-address/<int:id>/", views.set_main_address, name="set_main_address"),
    path("delete-address/<id>/", views.delete_address, name="delete_address"),
    path("profile/", views.profile, name="profile"),
    path("change-password/", views.change_password, name="change_password"),
]
