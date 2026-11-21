from django.db import models

from store.models import Product
from userauths.models import User


TYPE = (
    ("New Order", "New Order"),
    ("Item Shipped", "Item Shipped"),
    ("Item Delivered", "Item Delivered"),
)


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="wishlist"
    )
    # Anonymous session identifier (mirrors cart_id usage for Cart)
    wishlist_id = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Wishlist"

    def __str__(self):
        if self.product.name:
            return self.product.name
        else:
            return "Wishlist"


class Address(models.Model):
    DELIVERY_CHOICES = [
        ("econt_office", "Еконт офис"),
        ("econt", "Еконт адрес"),
        ("speedy_office", "Спиди офис"),
        ("speedy", "Спиди адрес"),
        ("pigeon_office", "Pigeon офис"),
        ("pigeon_locker", "Pigeon автомат"),
        ("pigeon", "Pigeon адрес"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=200, null=True, blank=True, default=None)
    phone = models.CharField(max_length=50, null=True, blank=True, default=None)
    email = models.CharField(max_length=100, null=True, blank=True, default=None)
    delivery_method = models.CharField(
        max_length=16, choices=DELIVERY_CHOICES, null=True, blank=True
    )
    city = models.CharField(max_length=100, null=True, blank=True, default=None)
    office_code = models.CharField(max_length=32, null=True, blank=True)
    office_name = models.CharField(max_length=255, null=True, blank=True)
    address = models.CharField(max_length=100, null=True, blank=True, default=None)
    post_code = models.CharField(max_length=10, blank=True, null=True)
    face = models.CharField(max_length=255, blank=True, null=True)
    is_main = models.BooleanField(default=False, verbose_name="Основен адрес")
    saved = models.BooleanField(default=False)
    site_id = models.CharField(max_length=32, blank=True, null=True)
    city_id = models.CharField(max_length=32, blank=True, null=True)
    street_id = models.CharField(max_length=32, blank=True, null=True)
    street_number = models.CharField(max_length=32, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Customer Addresses"

    def __str__(self):
        return self.name


OFFICE_DELIVERY_METHODS = ("econt_office", "speedy_office", "pigeon_office", "pigeon_locker")


def delivery_place_key(delivery_method, office_code, city, street):
    method = (delivery_method or "").strip()
    if method in OFFICE_DELIVERY_METHODS:
        code = (office_code or "").strip()
        if not code:
            return None
        return (method, code)
    city_key = (city or "").strip().casefold()
    street_key = (street or "").strip().casefold()
    if not method or not city_key or not street_key:
        return None
    return (method, city_key, street_key)


def delivery_is_complete(phone, delivery_method, office_code, city, street):
    return bool((phone or "").strip()) and delivery_place_key(
        delivery_method, office_code, city, street
    ) is not None


def saved_destination_winners(addresses):
    """One complete row per customer and place. Main wins, otherwise the newest."""
    groups = {}
    for address in addresses:
        if not address.user_id:
            continue
        if not delivery_is_complete(
            address.phone, address.delivery_method, address.office_code, address.city, address.address
        ):
            continue
        key = (address.user_id, delivery_place_key(
            address.delivery_method, address.office_code, address.city, address.address
        ))
        groups.setdefault(key, []).append(address)
    winners = []
    for rows in groups.values():
        mains = [row for row in rows if row.is_main]
        winners.append(max(mains or rows, key=lambda row: row.id))
    return winners


class Notifications(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    type = models.CharField(max_length=100, choices=TYPE, default=None)
    seen = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Notification"

    def __str__(self):
        return self.type
