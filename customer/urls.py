from django.urls import path
from customer import views

app_name = "customer"

urlpatterns = [
    path("quick_add_address/", views.quick_add_address, name="quick_add_address"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("order_detail/<order_id>/", views.order_detail, name="order_detail"),
    path("wishlist/", views.wishlist, name="wishlist"),
    path(
        "remove_from_wishlist/<id>/",
        views.remove_from_wishlist,
        name="remove_from_wishlist",
    ),
    path("toggle_wishlist/<int:id>/", views.toggle_wishlist, name="toggle_wishlist"),
    path("addresses/", views.addresses, name="addresses"),
    path("notis/", views.notis, name="notis"),
    path("mark_noti_seen/<id>/", views.mark_noti_seen, name="mark_noti_seen"),
    path("address_detail/<id>/", views.address_detail, name="address_detail"),
    path("address_create/", views.address_create, name="address_create"),
    path("delete_address/<id>/", views.delete_address, name="delete_address"),
    path("profile/", views.profile, name="profile"),
    path("change_password/", views.change_password, name="change_password"),
]
