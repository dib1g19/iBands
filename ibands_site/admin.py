from django.contrib import admin
from django.contrib.auth.models import Group


class iBandsModelAdmin(admin.ModelAdmin):
    """
    Base admin class with global settings applied to all admin classes.
    Inherit from this class instead of admin.ModelAdmin to get global settings.
    """
    list_per_page = 20
    show_full_result_count = False


admin.site.unregister(Group) 