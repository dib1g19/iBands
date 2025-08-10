from django.contrib import admin
from django.template.response import TemplateResponse
from ibands_site.middleware import RequestCounterMiddleware
from store.utils import get_500_error_stats


def stats_view(request):
    stats = {
        "user_request_count": RequestCounterMiddleware.get_user_request_count(),
        "user_request_unique_count": RequestCounterMiddleware.get_user_request_unique_count(),
        "bot_request_count": RequestCounterMiddleware.get_bot_request_count(),
        "bot_request_unique_count": RequestCounterMiddleware.get_bot_request_unique_count(),
    }
    stats.update(get_500_error_stats())
    context = dict(admin.site.each_context(request), stats=stats)
    return TemplateResponse(request, "admin/stats.html", context)