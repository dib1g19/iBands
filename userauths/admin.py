from django.contrib import admin
from ibands_site.admin import iBandsModelAdmin
from userauths import models as userauths_models


@admin.register(userauths_models.User)
class UserAdmin(iBandsModelAdmin):
    list_display = ["username", "email"]
    exclude = ['user_permissions']  # Hide this field to avoid content type queries


@admin.register(userauths_models.Profile)
class ProfileAdmin(iBandsModelAdmin):
    list_display = ["user", "full_name"]


@admin.register(userauths_models.ContactMessage)
class ContactMessageAdmin(iBandsModelAdmin):
    list_display = ["full_name", "email", "subject", "date"]


@admin.register(userauths_models.NewsletterSubscription)
class NewsletterSubscriptionAdmin(iBandsModelAdmin):
    list_display = ['email', 'date_subscribed', 'is_active']
    search_fields = ['email']