from django.contrib import admin
from ibands_site.admin import iBandsModelAdmin
from customer import models as customer_models
from store.admin_helpers import product_path_label


@admin.register(customer_models.Address)
class AddressAdmin(iBandsModelAdmin):
    list_display = ["name", "user"]


@admin.register(customer_models.Wishlist)
class WishlistAdmin(iBandsModelAdmin):
    list_display = ["user", "product_path"]
    list_select_related = ["user", "product__category__parent__parent"]

    @admin.display(description="Product")
    def product_path(self, obj):
        return product_path_label(obj.product, link=True)
