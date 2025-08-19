from django.core.paginator import Paginator
from django.core.cache import cache
from django.conf import settings
from decimal import Decimal, ROUND_FLOOR
import requests


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


# --- Speedy v1 JSON-credential endpoints ---
def speedy_v1_find_sites(name: str, country_id: int = 100):
    url = getattr(settings, "SPEEDY_API_BASE", "https://api.speedy.bg") + "/v1/location/site"
    payload = {
        "userName": settings.SPEEDY_USERNAME,
        "password": settings.SPEEDY_PASSWORD,
        "countryId": country_id,
        "name": name,
    }
    r = requests.post(url, json=payload, timeout=12, headers={"Content-Type": "application/json", "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def speedy_v1_find_offices(site_id: int):
    url = getattr(settings, "SPEEDY_API_BASE", "https://api.speedy.bg") + "/v1/location/office"
    payload = {
        "userName": settings.SPEEDY_USERNAME,
        "password": settings.SPEEDY_PASSWORD,
        "siteId": int(site_id),
    }
    r = requests.post(url, json=payload, timeout=12, headers={"Content-Type": "application/json", "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def speedy_v1_calculate(calculation_request: dict):
    url = getattr(settings, "SPEEDY_API_BASE", "https://api.speedy.bg") + "/v1/calculate"
    # v1/calculate expects a flat payload (not nested under calculationRequest)
    # Build a robust payload using provided fields, with sane defaults
    payer = calculation_request.get("payer") or "RECIPIENT"
    documents = bool(calculation_request.get("documents", False))
    palletized = bool(calculation_request.get("palletized", False))

    # Derive content (parcelsCount + totalWeight) from either content or parcels
    content_in = calculation_request.get("content") or {}
    parcels = calculation_request.get("parcels") or []
    total_weight = None
    if isinstance(content_in, dict):
        total_weight = content_in.get("totalWeight")
    if (total_weight is None) and parcels:
        try:
            total_weight = sum(float(p.get("weight", 0)) for p in parcels)
        except Exception:
            total_weight = None
    if total_weight is None:
        total_weight = 0.1
    try:
        total_weight = max(0.01, round(float(total_weight), 3))
    except Exception:
        total_weight = 0.1

    parcels_count = 1
    try:
        parcels_count = int(content_in.get("parcelsCount") or 1)
    except Exception:
        parcels_count = 1

    # Service: preserve any provided fields (e.g., additionalServices.cod) and ensure serviceIds array
    service_in = calculation_request.get("service") or {}
    service_ids = service_in.get("serviceIds")
    if not service_ids:
        default_service_id = getattr(settings, "SPEEDY_DEFAULT_SERVICE_ID", None)
        if default_service_id:
            service_ids = [int(default_service_id)]
    service_payload = dict(service_in) if isinstance(service_in, dict) else {}
    if service_ids:
        service_payload["serviceIds"] = service_ids

    recipient = calculation_request.get("recipient") or {}
    sender_in = calculation_request.get("sender") or None

    payment_in = calculation_request.get("payment") or {}
    if not payment_in:
        payer_code = "RECIPIENT" if str(payer).upper() == "RECIPIENT" else "SENDER"
        payment_in = {
            "courierServicePayer": payer_code,
            "declaredValuePayer": payer_code,
        }

    payload = {
        "userName": settings.SPEEDY_USERNAME,
        "password": settings.SPEEDY_PASSWORD,
        "language": "BG",
        "payer": payer,
        "documents": documents,
        "palletized": palletized,
        "recipient": recipient,
        "payment": payment_in,
        "content": {
            "parcelsCount": parcels_count,
            "totalWeight": total_weight,
            # Keep package if provided in input content
            **({"package": content_in.get("package")} if isinstance(content_in, dict) and content_in.get("package") else {}),
        },
        **({"service": service_payload} if service_payload else {}),
    }
    if sender_in:
        payload["sender"] = sender_in

    r = requests.post(url, json=payload, timeout=15, headers={"Content-Type": "application/json", "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def speedy_v1_create_shipment(shipment_request: dict):
    url = getattr(settings, "SPEEDY_API_BASE", "https://api.speedy.bg") + "/v1/shipment"
    payload = {
        "userName": settings.SPEEDY_USERNAME,
        "password": settings.SPEEDY_PASSWORD,
        # v1/shipment expects top-level fields, not nested under 'shipment'
        **shipment_request,
    }
    r = requests.post(url, json=payload, timeout=15, headers={"Content-Type": "application/json", "Accept": "application/json"})
    r.raise_for_status()
    return r.json()
