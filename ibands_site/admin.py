from django.contrib import admin
from django.contrib.auth.models import Group

from ibands_site.admin_undo import undo_snapshot


class iBandsModelAdmin(admin.ModelAdmin):
    """
    Base admin class with global settings applied to all admin classes.
    Inherit from this class instead of admin.ModelAdmin to get global settings.
    """
    list_per_page = 20
    show_full_result_count = False

    def save_model(self, request, obj, form, change):
        request._admin_undo = undo_snapshot(form) if change else None
        super().save_model(request, obj, form, change)

    def log_change(self, request, obj, message):
        snapshot = getattr(request, "_admin_undo", None)
        request._admin_undo = None
        if snapshot and isinstance(message, list):
            message = [*message, {"undo": snapshot}]
        return super().log_change(request, obj, message)


admin.site.unregister(Group) 