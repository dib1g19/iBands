from django.core.paginator import Paginator
from django.core.cache import cache
from decimal import Decimal, ROUND_FLOOR


def paginate_queryset(request, queryset, per_page):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


def increment_500_error_count(is_bot=None, ip=None):
    # Total 500 errors
    key_total = "custom_500_error_count"
    cache.set(key_total, cache.get(key_total, 0) + 1, timeout=None)

    if is_bot is not None and ip is not None:
        if is_bot:
            key = "custom_500_bot_error_count"
            key_unique = "custom_500_bot_error_unique_ips"
        else:
            key = "custom_500_user_error_count"
            key_unique = "custom_500_user_error_unique_ips"
        cache.set(key, cache.get(key, 0) + 1, timeout=None)
        ip_set = set(cache.get(key_unique, []))
        ip_set.add(ip)
        cache.set(key_unique, list(ip_set), timeout=None)


def get_500_error_stats():
    return {
        "total": cache.get("custom_500_error_count", 0),
        "user": cache.get("custom_500_user_error_count", 0),
        "bot": cache.get("custom_500_bot_error_count", 0),
        "user_unique": len(cache.get("custom_500_user_error_unique_ips", [])),
        "bot_unique": len(cache.get("custom_500_bot_error_unique_ips", [])),
    }


def floor_to_cent(amount):
    """Round down to 2 decimals (e.g., 9.995 -> 9.99). Returns Decimal."""
    try:
        dec = Decimal(str(amount))
    except Exception:
        return amount
    return dec.quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
