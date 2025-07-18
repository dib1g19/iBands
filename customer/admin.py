from django.contrib import admin
from customer import models as customer_models


class AddressAdmin(admin.ModelAdmin):
    list_display = ["user", "name"]


class WishlistAdmin(admin.ModelAdmin):
    list_display = ["user", "product"]


class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "type", "seen", "date"]


admin.site.register(customer_models.Address, AddressAdmin)
admin.site.register(customer_models.Wishlist, WishlistAdmin)
admin.site.register(customer_models.Notifications, NotificationAdmin)
