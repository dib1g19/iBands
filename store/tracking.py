import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from store.utils import econt_request, pigeon_request

logger = logging.getLogger(__name__)

# 148 is the label Speedy writes at creation, before a courier picks the parcel up.
SPEEDY_QUIET = {
    111, 112, 114, 120, 121, 123, 124, 125, 127, 128, 129, 148, 164,
}


def next_status(current, level):
    if level == "delivered" and current in ("received", "shipped"):
        return "delivered"
    if level == "shipped" and current == "received":
        return "shipped"
    return None


def speedy_level(operation_code, return_shipment_id=None):
    if return_shipment_id:
        return None
    try:
        code = int(operation_code)
    except (TypeError, ValueError):
        return None
    if code == -14:
        return "delivered"
    if code in SPEEDY_QUIET:
        return None
    return "shipped"


def econt_level(status):
    if not isinstance(status, dict):
        return None
    bg = (status.get("shortDeliveryStatus") or "").strip().casefold()
    en = (status.get("shortDeliveryStatusEn") or "").strip().casefold()
    text = f"{bg} {en}"
    if any(word in text for word in ("анулир", "върн", "връща", "cancel", "return")):
        return None
    if status.get("deliveryTime") or bg == "доставена" or en == "delivered":
        return "delivered"
    if "подготвена" in bg or en.startswith("prepared"):
        return None
    if status.get("sendTime") or bg or en:
        return "shipped"
    return None


def pigeon_level(row):
    if not isinstance(row, dict) or row.get("found") is False:
        return None
    code = (row.get("status_code") or "").strip()
    if not code or "return" in code or "cancel" in code or code == "shipment_registered":
        return None
    if code == "shipment_delivered_to_recipient" or row.get("delivery_date"):
        return "delivered"
    return "shipped"


def _chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def speedy_fetch(tracking_ids):
    found = {}
    url = getattr(settings, "SPEEDY_API_BASE", "https://api.speedy.bg").rstrip("/") + "/v1/track"
    for chunk in _chunks(list(tracking_ids), 10):
        payload = {
            "userName": settings.SPEEDY_USERNAME,
            "password": settings.SPEEDY_PASSWORD,
            "language": "BG",
            "parcels": [{"id": tracking_id} for tracking_id in chunk],
            "lastOperationOnly": True,
        }
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=15,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.exception("Speedy tracking failed")
            continue
        for parcel in body.get("parcels") or []:
            operations = parcel.get("operations") or []
            operation = operations[-1] if operations else {}
            found[str(parcel.get("parcelId"))] = speedy_level(
                operation.get("operationCode"),
                operation.get("returnShipmentId"),
            )
    return found


def econt_fetch(tracking_ids):
    found = {}
    url = "https://ee.econt.com/services/Shipments/ShipmentService.getShipmentStatuses.json"
    for chunk in _chunks(list(tracking_ids), 50):
        try:
            body = econt_request(url, {"shipmentNumbers": chunk})
        except Exception:
            logger.exception("Econt tracking failed")
            continue
        for row in (body or {}).get("shipmentStatuses") or []:
            status = row.get("status") if isinstance(row, dict) else None
            if not isinstance(status, dict):
                continue
            number = status.get("shipmentNumber")
            if number:
                found[str(number)] = econt_level(status)
    return found


def pigeon_fetch(tracking_ids):
    found = {}
    for chunk in _chunks(list(tracking_ids), 100):
        try:
            body = pigeon_request("POST", "/shipments/track/bulk", {"references": chunk})
        except Exception:
            logger.exception("Pigeon tracking failed")
            continue
        data = (body or {}).get("data") or {}
        if not isinstance(data, dict):
            continue
        for key, row in data.items():
            if not isinstance(row, dict):
                continue
            found[str(row.get("reference_number") or key)] = pigeon_level(row)
    return found


def fetch_levels(service, tracking_ids):
    if service == "speedy":
        return speedy_fetch(tracking_ids)
    if service == "econt":
        return econt_fetch(tracking_ids)
    if service == "pigeon":
        return pigeon_fetch(tracking_ids)
    return {}


def sync_open_orders():
    from store.models import Order

    cutoff = timezone.now() - timedelta(days=30)
    orders = list(
        Order.objects.filter(
            order_status__in=("received", "shipped"),
            shipping_service__in=("speedy", "econt", "pigeon"),
            date__gte=cutoff,
        )
        .exclude(tracking_id__isnull=True)
        .exclude(tracking_id="")
        .select_related("address")
    )
    grouped = {}
    for order in orders:
        grouped.setdefault(order.shipping_service, []).append(order)

    updated = 0
    for service, group in grouped.items():
        try:
            levels = fetch_levels(service, [(order.tracking_id or "").strip() for order in group])
        except Exception:
            logger.exception("Tracking sync failed for %s", service)
            continue
        for order in group:
            level = levels.get((order.tracking_id or "").strip())
            status = next_status(order.order_status, level)
            if not status:
                continue
            order.order_status = status
            try:
                order.save(update_fields=["order_status"])
            except Exception:
                logger.exception("Tracking sync could not save %s", order.order_id)
                continue
            updated += 1
    return updated
