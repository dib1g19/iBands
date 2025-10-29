from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.template.loader import render_to_string
from datetime import date as dt_date, datetime as dt_datetime, timedelta as dt_timedelta
import calendar as pycal
from decimal import Decimal, ROUND_HALF_UP
from .models import Category, Product, BandOfTheWeek, CategoryLink, SpinEntry, Coupon, SpinPrize, SpinMilestone, SpinMilestoneAward
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import random
import stripe
from store.utils import (
    paginate_queryset,
    floor_to_cent,
    speedy_v1_find_sites,
    speedy_v1_find_offices,
    speedy_v1_calculate,
    speedy_v1_create_shipment,
    send_meta_purchase_event,
    recalc_cart_group_promos,
)
from store import models as store_models
from customer import models as customer_models
from userauths import models as userauths_models
from customer.utils import get_user_wishlist_products
from store.emails import send_order_notification_email
from django.db.models import Q
from store.utils import increment_500_error_count
from urllib.parse import urlencode
import json
import requests
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

def _hex_to_rgb(hex_code):
    """Convert #RRGGBB or #RGB to integer RGB tuple."""
    if not isinstance(hex_code, str):
        return (0, 0, 0)
    s = hex_code.strip().lstrip('#')
    if len(s) == 3:
        try:
            r, g, b = (int(s[0]*2, 16), int(s[1]*2, 16), int(s[2]*2, 16))
            return (r, g, b)
        except Exception:
            return (0, 0, 0)
    if len(s) == 6:
        try:
            r, g, b = (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
            return (r, g, b)
        except Exception:
            return (0, 0, 0)
    return (0, 0, 0)

def _perceived_brightness(hex_code):
    """Return perceived brightness (0-255) using ITU-R BT.601 weights."""
    r, g, b = _hex_to_rgb(hex_code)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _generate_halloween_bats(count: int):
    paths = ["", "bat-path-b", "bat-path-c", "bat-path-d", "bat-path-e"]
    sizes = ["", "bat-sm", "bat-lg"]
    colors = ["orange", "amber", "tanger", "red"]
    bats = []
    for _ in range(int(count)):
        top_px = random.randint(6, 30)
        start_pct = -random.randint(20, 50)
        speed_s = round(random.uniform(10.5, 16.0), 1)
        delay_s = round(-random.uniform(0.2, 8.0), 1)
        amp_y_px = random.randint(8, 14)
        rot_deg = random.randint(4, 9)
        cls = ["bat-fly"]
        p = random.choice(paths)
        if p:
            cls.append(p)
        s = random.choices(sizes, weights=[6, 3, 2], k=1)[0]
        if s:
            cls.append(s)
        c = random.choice(colors)
        if c:
            cls.append(c)
        bats.append({
            "classes": " ".join(cls),
            "top": top_px,
            "startPct": start_pct,
            "speed": speed_s,
            "delay": delay_s,
            "ampY": amp_y_px,
            "rot": rot_deg,
        })
    return bats

def send_order_to_econt(order):
    url = settings.ECONT_UPDATE_ORDER_ENDPOINT
    headers = {
        "Content-Type": "application/json",
        "Authorization": settings.ECONT_PRIVATE_KEY,
        "X-ID-Shop": str(settings.ECONT_SHOP_ID),
    }
    items = []
    for item in order.order_items.all():
        items.append({
            "name": item.product.name,
            "SKU": getattr(item.product, "sku", ""),
            "count": item.qty,
            "totalPrice": float(item.sub_total),
            "totalWeight": float(getattr(item.product, "weight", 0.1)) * item.qty,
        })
    address = order.address
    data = {
        "id": "",
        "orderNumber": order.order_id,
        "status": "pending",
        "orderSum": float(order.total),
        "cod": float(order.total) if order.payment_method in ["cash_on_delivery"] else 0,
        "currency": "BGN",
        "shipmentDescription": f"iBands.bg поръчка #{order.order_id}",
        "customerInfo": {
            "name": address.name,
            "phone": address.phone,
            "email": address.email,
            "countryCode": "BG",
            "cityName": address.city,
            "postCode": address.post_code,
            "officeCode": address.office_code,
            "address": address.address,
            "face": address.face,
        },
        "items": items,
    }
    response = requests.post(url, headers=headers, json=data, timeout=10)
    if response.status_code == 200:
        try:
            resp_json = response.json()
        except Exception:
            print("ECONT updateOrder: failed to parse JSON. Raw:", getattr(response, "text", "")[:500])
            return None

        # Now, call the createAWB endpoint to generate the AWB/label
        create_awb_url = url.replace("OrdersService.updateOrder", "OrdersService.createAWB")
        try:
            awb_response = requests.post(create_awb_url, headers=headers, json=data, timeout=10)
            if awb_response.status_code == 200:
                try:
                    awb_json = awb_response.json()
                except Exception:
                    print("ECONT createAWB: failed to parse JSON. Raw:", getattr(awb_response, "text", "")[:500])
                    return None
                shipment_number = awb_json.get("shipmentNumber")
                if shipment_number:
                    order.tracking_id = shipment_number
                    order.save(update_fields=["tracking_id"])
                else:
                    print("ECONT createAWB: success status but missing shipmentNumber. Payload:", str(awb_json)[:500])
                return awb_json
            else:
                print("ECONT createAWB failed:", awb_response.status_code, getattr(awb_response, "text", "")[:500])
        except Exception as e:
            print("ECONT createAWB exception:", e)
        return None
    else:
        print("ECONT updateOrder failed:", response.status_code, getattr(response, "text", "")[:500])
        return None


def send_order_to_speedy(order):
    address = order.address
    total_weight = 0.0
    for item in order.order_items.all():
        try:
            total_weight += 0.1 * float(item.qty)
        except Exception:
            continue

    # Note: Calculation endpoint path may vary; we attempt direct shipment creation.
    service_id = None

    # Build recipient details using cached Speedy options (site_id/office_id)
    from django.core.cache import cache
    cached_opts = cache.get(f"speedy_opts_{order.order_id}") or {}
    site_id_cached = cached_opts.get("site_id")
    office_id_cached = cached_opts.get("office_id")

    contact_person = getattr(address, "face", "") or ""
    is_private = not bool(contact_person.strip())

    # Decide office vs address
    pickup_office_id = None
    if getattr(address, "office_code", None) and str(address.office_code).isdigit():
        pickup_office_id = int(address.office_code)
    elif office_id_cached and str(office_id_cached).isdigit():
        pickup_office_id = int(office_id_cached)

    # Minimal recipient for calculation
    recipient_for_calc = {"privatePerson": is_private}
    if pickup_office_id:
        recipient_for_calc["pickupOfficeId"] = pickup_office_id
    else:
        addr_loc = {"countryId": 100}
        city_name = getattr(address, "city", "") or ""
        if site_id_cached and str(site_id_cached).isdigit():
            addr_loc["siteId"] = int(site_id_cached)
        elif city_name:
            addr_loc["siteName"] = city_name
        addr_lines = {}
        if getattr(address, "address", None):
            addr_lines["address"] = address.address
        recipient_for_calc["addressLocation"] = addr_loc
        if addr_lines:
            recipient_for_calc["address"] = addr_lines

    # Try to calculate to obtain serviceId
    try:
        custom_contents = cached_opts.get("speedy_contents")
        # Derive parcels from cart: quantity * 0.1 kg per item, count fixed to 1
        parcels = [{"weight": max(0.01, round(total_weight, 3) or 0.1)}]

        # Determine payer (free shipping -> SENDER pays, else COD->RECIPIENT, card->SENDER)
        try:
            free_shipping = (Decimal(str(order.shipping or 0)) == Decimal("0.00"))
        except Exception:
            free_shipping = False
        is_cod = (order.payment_method == "cash_on_delivery")
        payer_code = "SENDER" if free_shipping else ("RECIPIENT" if is_cod else "SENDER")

        calc_req = {
            "payer": payer_code,
            "documents": False,
            "palletized": False,
            "parcels": parcels or [{"weight": round(total_weight, 3) or 0.1}],
            "recipient": recipient_for_calc,
        }
        if getattr(settings, "SPEEDY_DROPOFF_OFFICE_ID", None):
            calc_req["sender"] = {"dropoffOfficeId": int(settings.SPEEDY_DROPOFF_OFFICE_ID)}
        calc_resp = speedy_v1_calculate(calc_req)
        # Extract serviceId or fallback to default
        if isinstance(calc_resp, dict):
            calcs = calc_resp.get("calculations") or calc_resp.get("services") or []
            if calcs:
                first = calcs[0]
                service_id = first.get("serviceId") or (first.get("service") or {}).get("id") or first.get("id")
        if not service_id:
            try:
                service_id = int(getattr(settings, "SPEEDY_DEFAULT_SERVICE_ID", None) or 0) or None
            except Exception:
                service_id = getattr(settings, "SPEEDY_DEFAULT_SERVICE_ID", None)
    except Exception as e:
        print("Speedy calc exception:", e)
        if not service_id:
            try:
                service_id = int(getattr(settings, "SPEEDY_DEFAULT_SERVICE_ID", None) or 0) or None
            except Exception:
                service_id = getattr(settings, "SPEEDY_DEFAULT_SERVICE_ID", None)

    # Build payload per example structure
    is_cod = (order.payment_method == "cash_on_delivery")
    try:
        free_shipping = (Decimal(str(order.shipping or 0)) == Decimal("0.00"))
    except Exception:
        free_shipping = False
    payer_code = "SENDER" if free_shipping else ("RECIPIENT" if is_cod else "SENDER")
    shipment_request = {
        "language": "BG",
        "service": {
            "serviceId": service_id or getattr(settings, "SPEEDY_DEFAULT_SERVICE_ID", None),
            "additionalServices": {
                **({"cod": {"amount": float(order.total), "processingType": "CASH"}} if is_cod else {}),
            },
            "autoAdjustPickupDate": True,
        },
        "content": {
            "parcelsCount": 1,
            "totalWeight": float(sum(p.get("weight", 0) for p in parcels)),
            "contents": custom_contents or f"iBands.bg поръчка #{order.order_id}",
            "package": "BOX",
        },
        "payment": {
            "courierServicePayer": payer_code,
            "declaredValuePayer": payer_code,
        },
        "sender": ({"dropoffOfficeId": int(settings.SPEEDY_DROPOFF_OFFICE_ID)}
                   if getattr(settings, "SPEEDY_DROPOFF_OFFICE_ID", None) else {}),
        "recipient": {
            "phone1": {"number": (getattr(address, "phone", "") or "")},
            "clientName": getattr(address, "name", "") or "",
            "email": getattr(address, "email", "") or "",
            "privatePerson": is_private,
            **({"contactName": contact_person} if not is_private else {}),
            **({"pickupOfficeId": pickup_office_id} if pickup_office_id else {}),
        },
        "ref1": f"ORDER {order.order_id}",
    }
    # Attach Options Before Payment (OBPD) with configured option (OPEN/TEST) under service.additionalServices.obpd
    try:
        _return_service_id = service_id or int(getattr(settings, "SPEEDY_DEFAULT_SERVICE_ID", 0) or 0) or None
    except Exception:
        _return_service_id = getattr(settings, "SPEEDY_DEFAULT_SERVICE_ID", None)
    # Use configurable OBPD option: OPEN (default) or TEST (for "test before payment")
    obpd_option = str(getattr(settings, "SPEEDY_OBPD_OPTION", "OPEN")).upper()
    if obpd_option not in {"OPEN", "TEST"}:
        obpd_option = "OPEN"
    obp_block = {
        "option": obpd_option,
        "returnShipmentPayer": "SENDER",
    }
    if _return_service_id:
        try:
            obp_block["returnShipmentServiceId"] = int(_return_service_id)
        except Exception:
            pass
    # Ensure additionalServices exists and add obpd
    if "additionalServices" not in shipment_request["service"] or not isinstance(shipment_request["service"].get("additionalServices"), dict):
        shipment_request["service"]["additionalServices"] = {}
    shipment_request["service"]["additionalServices"]["obpd"] = obp_block
    # For address delivery, add address (single block) as before
    if "pickupOfficeId" not in shipment_request["recipient"]:
        addr = {"countryId": 100}
        city_name = getattr(address, "city", "") or ""
        if site_id_cached and str(site_id_cached).isdigit():
            addr["siteId"] = int(site_id_cached)
        elif city_name:
            addr["siteName"] = city_name
        addr_line = (getattr(address, "address", None) or "").strip()
        if addr_line:
            addr["address"] = addr_line
        shipment_request["recipient"]["address"] = addr
    if order.payment_method == "cash_on_delivery":
        shipment_request["cod"] = {
            "amount": float(order.sub_total),
            "currency": "BGN",
        }

    try:
        resp_json = speedy_v1_create_shipment(shipment_request)
        shipment_number = resp_json.get("shipmentNumber") or resp_json.get("id") or resp_json.get("shipmentId")
        # If OBPD TEST is not allowed (e.g., automats), retry with OPEN then without OBPD
        if not shipment_number and isinstance(resp_json, dict) and resp_json.get("error"):
            try:
                err_block = resp_json.get("error") or {}
                err_text = f"{err_block.get('message', '')} {err_block.get('name', '')} {err_block.get('component', '')}".lower()
            except Exception:
                err_text = ""
            obpd_in_payload = isinstance(shipment_request.get("service", {}).get("additionalServices", {}).get("obpd"), dict)
            attempted_test = obpd_option == "TEST"
            mentions_obpd = ("obpd" in err_text) or ("options before payment" in err_text) or ("optionsbeforepayment" in err_text) or ("test" in err_text)
            if obpd_in_payload and (attempted_test or mentions_obpd):
                # 1) Retry with OPEN
                shipment_request_open = json.loads(json.dumps(shipment_request))
                try:
                    shipment_request_open["service"]["additionalServices"]["obpd"]["option"] = "OPEN"
                except Exception:
                    shipment_request_open = None
                if shipment_request_open:
                    resp_json = speedy_v1_create_shipment(shipment_request_open)
                    shipment_number = resp_json.get("shipmentNumber") or resp_json.get("id") or resp_json.get("shipmentId")
                # 2) Retry without OBPD if still no number and still looks related
                if not shipment_number and isinstance(resp_json, dict):
                    try:
                        err_block2 = resp_json.get("error") or {}
                        err_text2 = f"{err_block2.get('message', '')} {err_block2.get('name', '')} {err_block2.get('component', '')}".lower()
                    except Exception:
                        err_text2 = ""
                    if ("obpd" in err_text2) or ("options before payment" in err_text2) or ("optionsbeforepayment" in err_text2) or (attempted_test and not shipment_number):
                        shipment_request_no_obpd = json.loads(json.dumps(shipment_request))
                        try:
                            shipment_request_no_obpd["service"]["additionalServices"].pop("obpd", None)
                        except Exception:
                            pass
                        resp_json = speedy_v1_create_shipment(shipment_request_no_obpd)
                        shipment_number = resp_json.get("shipmentNumber") or resp_json.get("id") or resp_json.get("shipmentId")
        if not shipment_number and isinstance(resp_json, dict) and resp_json.get("error") and "recipient.address" in str(resp_json.get("error", {}).get("component", "")):
            # Fallback: retry with streetName/streetNo if possible
            try:
                rec = shipment_request.get("recipient", {})
                if "pickupOfficeId" not in rec and isinstance(rec.get("address"), dict):
                    addr_block = rec["address"]
                    line = (addr_block.get("address") or "").strip()
                    if line:
                        parts = line.rsplit(' ', 1)
                        if len(parts) == 2 and any(ch.isdigit() for ch in parts[1]):
                            # Build a new address dict with streetName/streetNo
                            new_addr = {k: v for k, v in addr_block.items() if k != "address"}
                            new_addr["streetName"] = parts[0]
                            new_addr["streetNo"] = parts[1]
                            shipment_request_retry = dict(shipment_request)
                            shipment_request_retry["recipient"] = dict(shipment_request["recipient"])
                            shipment_request_retry["recipient"]["address"] = new_addr
                            resp_json = speedy_v1_create_shipment(shipment_request_retry)
                            shipment_number = resp_json.get("shipmentNumber") or resp_json.get("id") or resp_json.get("shipmentId")
            except Exception:
                pass
        if shipment_number:
            order.tracking_id = shipment_number
            order.shipping_service = "speedy"
            order.save(update_fields=["tracking_id", "shipping_service"])
        else:
            print("Speedy create shipment response:", resp_json)
        return resp_json
    except Exception as e:
        print("Speedy shipment exception:", e)
        return None


def _send_shipment(order):
    method = (getattr(order.address, "delivery_method", "") or "").split("_", 1)[0]
    if method == "speedy":
        try:
            send_order_to_speedy(order)
        except Exception:
            pass
    else:
        try:
            econt_response = send_order_to_econt(order)
            if econt_response:
                order.shipping_service = "econt"
                order.save(update_fields=["shipping_service"])
        except Exception:
            pass


@csrf_exempt
def save_econt_address(request, order_id):
    if request.method == "POST":
        try:
            order = store_models.Order.objects.get(order_id=order_id)
            data = json.loads(request.body)

            # Parse shipping price only if provided; otherwise leave as None
            shipping_price = None
            if 'shipping_price' in data:
                try:
                    shipping_price = float(data.get('shipping_price'))
                except (TypeError, ValueError):
                    shipping_price = None

            user = request.user if request.user.is_authenticated else None
            office_name = data.get('office_name', '')
            delivery_method = 'econt_office' if office_name else 'econt'
            address_kwargs = dict(
                name=data.get('name', ''),
                phone=data.get('phone', ''),
                email=data.get('email', ''),
                delivery_method=delivery_method,
                city=data.get('city', ''),
                address=data.get('address', ''),
                office_code=data.get('office_code', ''),
                office_name=office_name,
                post_code=data.get('post_code', ''),
                face=data.get('face', ''),
            )
            # Check if this exact address already exists for this user
            if user:
                existing_address = customer_models.Address.objects.filter(
                    user=user,
                    name=data.get('name', ''),
                    phone=data.get('phone', ''),
                    email=data.get('email', ''),
                    delivery_method=delivery_method,
                    city=data.get('city', ''),
                    address=data.get('address', ''),
                    office_code=data.get('office_code', ''),
                    office_name=office_name,
                    post_code=data.get('post_code', ''),
                    face=data.get('face', ''),
                ).first()
            else:
                existing_address = None
            
            if existing_address:
                # Use existing address for this user
                address = existing_address
            else:
                # Create new address and associate with user if available
                if user:
                    address_kwargs['user'] = user
                address = customer_models.Address.objects.create(**address_kwargs)
            order.address = address
            # Backend free-shipping enforcement: if subtotal >= 75 and office delivery selected -> free
            free_shipping_threshold = Decimal("75")
            is_office_delivery = delivery_method == 'econt_office'
            if (order.sub_total or 0) is not None and Decimal(str(order.sub_total)) >= free_shipping_threshold and is_office_delivery:
                order.shipping = Decimal("0.00")
            else:
                # Update shipping only when a valid shipping price was provided
                if shipping_price is not None:
                    order.shipping = Decimal(str(shipping_price))
            # Recalculate totals (and item prices if coupon present)
            apply_coupon_discount(order)
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {e}"})
    return JsonResponse({"success": False, "message": "Invalid request"})


@csrf_exempt
def save_speedy_address(request, order_id):
    if request.method == "POST":
        try:
            order = store_models.Order.objects.get(order_id=order_id)
            data = json.loads(request.body)

            shipping_price = None
            if 'shipping_price' in data:
                try:
                    shipping_price = float(data.get('shipping_price'))
                except (TypeError, ValueError):
                    shipping_price = None

            user = request.user if request.user.is_authenticated else None
            office_name = data.get('office_name', '')
            delivery_method = 'speedy_office' if office_name else 'speedy'
            address_kwargs = dict(
                name=data.get('name', ''),
                phone=data.get('phone', ''),
                email=data.get('email', ''),
                delivery_method=delivery_method,
                city=data.get('city', ''),
                address=data.get('address', ''),
                office_code=data.get('office_code', ''),
                office_name=office_name,
                face=data.get('face', ''),
            )

            # Note: we do not persist Speedy site_id in Address model (no field). We'll resolve via API when shipping.

            if user:
                existing_address = customer_models.Address.objects.filter(user=user, **address_kwargs).first()
            else:
                existing_address = None

            if existing_address:
                address = existing_address
            else:
                if user:
                    address_kwargs['user'] = user
                address = customer_models.Address.objects.create(**address_kwargs)

            order.address = address
            # Backend free-shipping enforcement: if subtotal >= 75 and office delivery selected -> free
            free_shipping_threshold = Decimal("75")
            is_office_delivery = delivery_method == 'speedy_office'
            if (order.sub_total or 0) is not None and Decimal(str(order.sub_total)) >= free_shipping_threshold and is_office_delivery:
                order.shipping = Decimal("0.00")
            else:
                if shipping_price is not None:
                    order.shipping = Decimal(str(shipping_price))
            # Cache extra Speedy options for shipment creation
            from django.core.cache import cache
            speedy_opts = {
                "speedy_contents": data.get('speedy_contents') or None,
                "parcel_weight": data.get('parcel_weight') or None,
                "parcel_count": data.get('parcel_count') or None,
                "site_id": data.get('site_id') or None,
                "office_id": data.get('office_code') or None,
            }
            cache.set(f"speedy_opts_{order.order_id}", speedy_opts, timeout=60*60)
            apply_coupon_discount(order)
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Error: {e}"})
    return JsonResponse({"success": False, "message": "Invalid request"})


def apply_coupon_discount(order):
    """
    Helper to recalculate coupon discount, saved, and total for an order.
    Also updates order item prices.
    """
    coupons = order.coupons.all()
    shipping = Decimal(str(order.shipping or 0))
    if coupons.exists():
        coupon = coupons.first()
        total_discount = round2(order.sub_total * coupon.discount / 100)
        order.saved = round2(total_discount)
        order.total = round2(order.sub_total + shipping - total_discount)
        apply_item_discounts(order, coupon)
    else:
        order.saved = round2(0)
        order.total = round2(order.sub_total + shipping)
        apply_item_discounts(order, None)
    order.save()


def apply_item_discounts(order, coupon=None):
    """
    Apply coupon discounts to each order item if coupon is provided.
    """
    if not coupon:
        coupons = order.coupons.all()
        coupon = coupons.first() if coupons.exists() else None
    for item in order.order_items.all():
        # Compute base price from the specific SKU (product item) if possible
        try:
            sku_qs = store_models.ProductItem.objects.filter(product=item.product)
            if item.size:
                sku_qs = sku_qs.filter(size__name=item.size)
            else:
                sku_qs = sku_qs.filter(size__isnull=True)
            if item.model:
                sku_qs = sku_qs.filter(device_models__name=item.model)
            sku = sku_qs.first()
        except Exception:
            sku = None

        if sku:
            base_price = Decimal(str(sku.effective_price or 0))
        else:
            base_price = Decimal(str(item.product.effective_price or 0))
        # Determine chargeable (paid) units from current line allocation (not recomputed)
        try:
            paid_units = int(getattr(item, "promo_paid_units", item.qty) or item.qty)
        except Exception:
            paid_units = item.qty

        if coupon:
            discount = Decimal(str(coupon.discount)) / Decimal("100")
            discounted_price = round2(base_price * (Decimal("1") - discount))
            item.price = discounted_price
            item.sub_total = round2(discounted_price * paid_units)
        else:
            item.price = base_price
            item.sub_total = round2(base_price * paid_units)
        item.save()


@csrf_exempt
def speedy_find_sites(request):
    q = request.GET.get("q") or request.POST.get("q")
    if not q:
        return JsonResponse({"sites": []})
    try:
        data = speedy_v1_find_sites(q)
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({"sites": [], "error": str(e)})


@csrf_exempt
def speedy_find_offices(request):
    site_id = request.GET.get("site_id") or request.POST.get("site_id")
    if not site_id:
        return JsonResponse({"offices": []})
    try:
        data = speedy_v1_find_offices(int(site_id))
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({"offices": [], "error": str(e)})


@csrf_exempt
def speedy_quote(request, order_id):
    try:
        order = store_models.Order.objects.get(order_id=order_id)
        site_id = request.GET.get("site_id")
        office_id = request.GET.get("office_id")
        address_line = request.GET.get("address") or (order.address.address if order.address else "")
        post_code = request.GET.get("post_code") or (getattr(order.address, "post_code", None) or None)
        phone = request.GET.get("phone") or (order.address.phone if order.address else "")
        name = request.GET.get("name") or (order.address.name if order.address else "")
        email = request.GET.get("email") or (order.address.email if order.address else "")

        # Build recipient for quote
        recipient_party = {
            "phone1": {"number": phone or ""},
            "clientName": name or "",
            "email": email or "",
            "privatePerson": True,
        }
        if office_id and office_id.isdigit():
            recipient_party["pickupOfficeId"] = int(office_id)
        else:
            # Speedy v1 expects addressLocation (countryId + siteId/siteName) separate from address lines
            addr_loc = {"countryId": 100}
            city = request.GET.get("city") or (order.address.city if order.address else "")
            if site_id and site_id.isdigit():
                addr_loc["siteId"] = int(site_id)
            elif city:
                addr_loc["siteName"] = city

            addr_lines = {}
            if address_line:
                addr_lines["address"] = address_line

            recipient_party["addressLocation"] = addr_loc
            if addr_lines:
                recipient_party["address"] = addr_lines

        # Compute total weight (qty * 0.1)
        total_weight = 0.0
        for item in order.order_items.all():
            try:
                total_weight += 0.1 * float(item.qty)
            except Exception:
                continue
        parcels = [{"weight": max(0.01, round(total_weight, 3) or 0.1)}]

        calc_request = {
            "payer": "RECIPIENT",
            "documents": False,
            "palletized": False,
            "parcels": parcels,
            "recipient": recipient_party,
        }
        if getattr(settings, "SPEEDY_DROPOFF_OFFICE_ID", None):
            calc_request["sender"] = {"dropoffOfficeId": int(settings.SPEEDY_DROPOFF_OFFICE_ID)}
        # Include COD in quote when payment method implies COD
        is_cod = (request.GET.get("payment") == "cod") or (order.payment_method == "cash_on_delivery")
        # Add autoAdjustPickupDate so Speedy quotes next valid pickup even when office is closed
        service_block = {"autoAdjustPickupDate": True}
        if is_cod:
            service_block["additionalServices"] = {
                "cod": {"amount": float(order.total), "processingType": "CASH"}
            }
        calc_request["service"] = service_block
        calc_response = speedy_v1_calculate(calc_request)
        # Try to extract a single price/total
        quote = None
        service_id = None
        calcs = (calc_response or {}).get("calculations") or (calc_response or {}).get("services") or []
        if calcs:
            first = calcs[0]
            service_id = first.get("serviceId") or (first.get("service") or {}).get("id") or first.get("id")
            pricing = first.get("price") or {}
            # Prefer total; fallback to amount
            numeric_price = None
            if isinstance(pricing, dict):
                numeric_price = pricing.get("total") or pricing.get("amount") or pricing.get("totalLocal") or pricing.get("amountLocal")
                currency = pricing.get("currency") or pricing.get("currencyLocal") or first.get("currency") or "BGN"
            else:
                # Some responses might have flat total/amount at the top level
                numeric_price = first.get("total") or first.get("amount")
                currency = first.get("currency") or "BGN"
            quote = {
                "serviceId": service_id,
                "price": float(numeric_price) if isinstance(numeric_price, (int, float)) else None,
                "currency": currency,
            }
        return JsonResponse({
            "success": True,
            "quote": quote,
            "calc_request": calc_request,
            "calc_response": calc_response,
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


def round2(val):
    return Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_category_ancestors(category):
    ancestors = []
    while category.parent:
        ancestors.append(category.parent)
        category = category.parent
    return ancestors[::-1]


def clear_cart_items(request):
    try:
        cart_id = request.session["cart_id"]
        store_models.Cart.objects.filter(cart_id=cart_id).delete()
    except:
        pass
    return


def index(request):
    # Featured products
    products_list = (
        store_models.Product.objects.filter(status="published", featured=True)
        .select_related('category', 'category__parent', 'category__parent__parent')
        .prefetch_related('gallery_images')
    )
    products = paginate_queryset(request, products_list, 20)

    # Sale products (manually marked)
    sale_products = (
        store_models.Product.objects.filter(status="published", on_sale=True)
        .select_related('category', 'category__parent', 'category__parent__parent')
        .prefetch_related('gallery_images')[:12]
    )

    categories = store_models.Category.objects.filter(parent__isnull=True)
    popular_categories = (
        store_models.Category.objects
            .filter(is_popular=True)
            .select_related('parent', 'parent__parent')
    )


    # Band of the Week (50% off)
    band_of_the_week = BandOfTheWeek.get_current_week()
    band_product = getattr(band_of_the_week, "product", None)
    # Ensure gallery_images are prefetched for band product (homepage card)
    if band_product:
        try:
            band_product = (
                Product.objects
                .select_related('category', 'category__parent', 'category__parent__parent')
                .prefetch_related('gallery_images')
                .get(pk=band_product.pk)
            )
        except Exception:
            pass
    band_override_price = None
    band_discount_percent = None
    if band_product and band_product.price:
        half = band_product.price * Decimal("0.5")
        band_override_price = floor_to_cent(half)
        band_discount_percent = 50

    band_of_the_week_url = reverse("store:band_of_the_week") if band_product else None
    band_week_start = getattr(band_of_the_week, "week_start", None)
    band_week_end = (band_week_start + dt_timedelta(days=6)) if band_week_start else None

    # --- Daily Spin (homepage wheel) ---
    try:
        today = timezone.localdate()
        from datetime import datetime as _dt, time as _time
        tz = timezone.get_current_timezone()
        tomorrow = today + dt_timedelta(days=1)
        reset_at = timezone.make_aware(_dt.combine(tomorrow, _time.min), tz)
    except Exception:
        reset_at = None

    spin_last_spin = None
    spin_can_spin = True
    if getattr(request, "user", None) and request.user.is_authenticated:
        try:
            spin_last_spin = store_models.SpinEntry.objects.filter(user=request.user).order_by("-date", "-created_at").first()
            if spin_last_spin and spin_last_spin.date == today:
                spin_can_spin = False
        except Exception:
            pass

    try:
        prizes_qs = store_models.SpinPrize.objects.filter(active=True).order_by("sort_order", "id")
        spin_prizes = [
            {
                "label": p.label,
                "type": p.prize_type,
                "discount_percent": int(p.discount_percent or 0),
                "min_order_total": float(p.min_order_total) if p.min_order_total is not None else None,
                "color": p.color or "#ffe082",
                "weight": float(p.weight or 0),
            }
            for p in prizes_qs
        ]
    except Exception:
        spin_prizes = []

    # Milestone progress (for homepage widget)
    try:
        milestones_qs = store_models.SpinMilestone.objects.filter(active=True).order_by("threshold_spins", "id")
        spin_milestones = [
            {
                "threshold_spins": int(m.threshold_spins),
                "label": m.label,
                "prize_type": m.prize_type,
                "discount_percent": int(m.discount_percent or 0),
                "min_order_total": float(m.min_order_total) if m.min_order_total is not None else None,
            }
            for m in milestones_qs
        ]
    except Exception:
        spin_milestones = []
    if getattr(request, "user", None) and request.user.is_authenticated:
        spin_total_spins = store_models.SpinEntry.objects.filter(user=request.user).count()
        try:
            achieved_qs = store_models.SpinMilestoneAward.objects.filter(user=request.user).select_related("milestone")
            achieved_thresholds = [int(a.milestone.threshold_spins) for a in achieved_qs]
            achieved_details = [
                {
                    "threshold_spins": int(a.milestone.threshold_spins),
                    "label": a.milestone.label,
                    "prize_type": a.milestone.prize_type,
                    "discount_percent": int(a.milestone.discount_percent or 0),
                    "min_order_total": float(a.milestone.min_order_total) if a.milestone.min_order_total is not None else None,
                    "coupon_code": a.coupon_code,
                }
                for a in achieved_qs
            ]
        except Exception:
            achieved_thresholds = []
            achieved_details = []
    else:
        spin_total_spins = 0
        achieved_thresholds = []
        achieved_details = []

    # --- Halloween swarms (randomized) ---
    halloween_bats_top = _generate_halloween_bats(5)
    halloween_bats_bottom = _generate_halloween_bats(5)

    context = {
        "products": products,
        "sale_products": sale_products,
        "categories": categories,
        "popular_categories": popular_categories,
        "user_wishlist_products": get_user_wishlist_products(request),
        "band_of_the_week": band_product,
        "band_price": band_override_price,
        "band_discount_percent": band_discount_percent,
        "band_of_the_week_url": band_of_the_week_url,
        "band_week_start": band_week_start,
        "band_week_end": band_week_end,
        # Spin widget context
        "spin_can_spin": spin_can_spin,
        "spin_last_spin": spin_last_spin,
        "spin_reset_at_iso": reset_at.isoformat() if reset_at else None,
        "spin_prizes_json": json.dumps(spin_prizes, ensure_ascii=False),
        "spin_url": reverse("store:spin_perform"),
        "spin_milestones_json": json.dumps(spin_milestones),
        "spin_milestone_progress_json": json.dumps({
            "spins": spin_total_spins,
            "achieved": achieved_thresholds,
        }),
        "spin_achieved_details_json": json.dumps(achieved_details, ensure_ascii=False),
        # Halloween swarms
        "halloween_bats_top": halloween_bats_top,
        "halloween_bats_bottom": halloween_bats_bottom,
    }
    return render(request, "store/index.html", context)


def band_of_the_week(request):
    # Parse selected date from query (?date=YYYY-MM-DD). Default to today.
    date_str = request.GET.get("date")
    try:
        selected_date = dt_datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else dt_date.today()
    except Exception:
        selected_date = dt_date.today()

    # Get deal for the week of selected date; fallback to current week's if requested week has no deal
    deal = BandOfTheWeek.get_for_date(selected_date)
    if not deal:
        deal = BandOfTheWeek.get_current_week()
        # Keep selected_date unchanged; we still need it for calendar positioning
    product = getattr(deal, "product", None) if deal else None
    if not product:
        messages.info(request, "Няма избрана каишка за тази дата.")
        return redirect("store:index")

    # Refetch product with related data for efficient template rendering
    product = (
        Product.objects
        .select_related('category', 'category__parent', 'category__parent__parent')
        .prefetch_related('gallery_images', 'colors')
        .get(pk=product.pk)
    )

    # Prepare breadcrumbs
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Каишка на седмицата", "url": ""},
    ]

    # Explicit price values for display and override sale display to -50% (only for current week)
    original_price = product.price
    half = product.price * Decimal("0.5") if product and product.price else None
    discounted_price = floor_to_cent(half) if half is not None else product.effective_price
    # For current week's deal: show discounted price. For previous/future weeks: show regular price
    if deal:
        today = dt_date.today()
        current_week_start = today - dt_timedelta(days=today.weekday())
        if getattr(deal, 'week_start', None) == current_week_start:
            product.sale_price = discounted_price
        else:
            product.sale_price = None

    # Build SKU options similar to product_detail
    sku_items = (
        store_models.ProductItem.objects.filter(product=product)
        .select_related("size")
        .prefetch_related("device_models")
    )
    size_list = []
    seen_sizes = set()
    for it in sku_items:
        if it.size and it.size.id not in seen_sizes:
            size_list.append(it.size)
            seen_sizes.add(it.size.id)
    size_list.sort(key=lambda s: (s.sort_order, s.name.lower()))

    model_list = []
    seen_models = set()
    for it in sku_items:
        for dm in it.device_models.all():
            if dm.id not in seen_models:
                model_list.append(dm)
                seen_models.add(dm.id)
    model_list.sort(key=lambda m: (getattr(m, "sort_order", 0), m.name.lower()))

    sku_data = []
    try:
        for it in sku_items:
            size_name = getattr(it.size, "name", None)
            delta_val = float(getattr(it, "price_delta", 0) or 0)
            qty_val = int(getattr(it, "quantity", 0) or 0)
            dms = list(it.device_models.all())
            if dms:
                for dm in dms:
                    sku_data.append({"size": size_name, "model": dm.name, "delta": delta_val, "qty": qty_val})
            else:
                sku_data.append({"size": size_name, "model": None, "delta": delta_val, "qty": qty_val})
    except Exception:
        sku_data = []

    try:
        total_stock = max([max(0, int(getattr(it, "quantity", 0))) for it in sku_items] or [int(product.stock or 0)])
    except Exception:
        total_stock = int(product.stock or 0)
    product_stock_range = range(1, (total_stock or 0) + 1)

    has_length_variant = any(v.variant_type == "length" for v in product.variants.all())

    # Weekly history: show last N weeks (e.g., 4) as cards, independent of selected week
    history_weeks_count = 4
    # Compute current (this) Monday; allow future weeks to be shown
    today = dt_date.today()
    current_week_start = today - dt_timedelta(days=today.weekday())
    # Anchor to the most recent existing (can be future)
    latest_week_start = (
        BandOfTheWeek.objects
        .order_by("-week_start")
        .values_list("week_start", flat=True)
        .first()
        or current_week_start
    )
    # History pagination via offset h (blocks of N weeks), 0 = latest block, 1 = older block, etc.
    try:
        history_offset = int(request.GET.get("h", 0))
    except Exception:
        history_offset = 0
    if history_offset < 0:
        history_offset = 0
    start_base = latest_week_start - dt_timedelta(weeks=history_offset * history_weeks_count)
    # Collect N previous week starts including base
    history_starts = [start_base - dt_timedelta(weeks=i) for i in range(history_weeks_count)]
    weekly_history = (
        BandOfTheWeek.objects
        .filter(week_start__in=history_starts)
        .select_related("product__category")
        .prefetch_related("product__gallery_images")
        .order_by("-week_start")
    )
    # Compute week end (Sunday) for display ranges
    history = []
    for w in weekly_history:
        week_end = w.week_start + dt_timedelta(days=6)
        history.append({
            "deal": w,
            "start": w.week_start,
            "end": week_end,
        })
    # Determine if we can paginate further back/forward
    min_week_start = (
        BandOfTheWeek.objects
        .order_by("week_start")
        .values_list("week_start", flat=True)
        .first()
    )
    # Oldest week shown on current page is the last in history_starts
    oldest_shown = history_starts[-1] if history_starts else None
    has_next_history = bool(min_week_start and oldest_shown and oldest_shown > min_week_start)
    has_prev_history = history_offset > 0

    context = {
        "product": product,
        "original_price": original_price,
        "discounted_price": discounted_price,
        "product_stock_range": product_stock_range,
        "has_length_variant": has_length_variant,
        "breadcrumbs": breadcrumbs,
        "user_wishlist_products": get_user_wishlist_products(request),
        "deal_week_start": getattr(deal, 'week_start', None),
        "deal_week_end": (getattr(deal, 'week_start', None) + dt_timedelta(days=6)) if getattr(deal, 'week_start', None) else None,
        # Week state helpers
        "is_current_week": (getattr(deal, 'week_start', None) == (dt_date.today() - dt_timedelta(days=dt_date.today().weekday()))),
        "is_future_week": (getattr(deal, 'week_start', None) and getattr(deal, 'week_start', None) > (dt_date.today() - dt_timedelta(days=dt_date.today().weekday()))),
        # Weekly history context (last 4 weeks)
        "history": history,
        "history_offset": history_offset,
        "has_prev_history": has_prev_history,
        "has_next_history": has_next_history,
        # For highlighting the selected week in history
        "selected_week_start": (selected_date - dt_timedelta(days=selected_date.weekday())),
        "current_week_start": current_week_start,
        "selected_date": selected_date,
        "total_stock": total_stock,
        # SKU context
        "sizes": size_list,
        "device_models": model_list,
        "sku_data_json": json.dumps(sku_data),
    }
    return render(request, "store/band_of_the_week.html", context)


def band_of_the_week_history(request):
    """AJAX: return weekly history cards (4 items) for a given date + offset h."""
    # History is anchored to latest; ignore date to avoid future weeks
    try:
        history_offset = int(request.GET.get("h", 0))
        if history_offset < 0:
            history_offset = 0
    except Exception:
        history_offset = 0

    # Determine anchor: the latest available (can be future)
    latest_week_start = (
        BandOfTheWeek.objects
        .order_by("-week_start")
        .values_list("week_start", flat=True)
        .first()
    )
    if not latest_week_start:
        latest_week_start = dt_date.today() - dt_timedelta(days=dt_date.today().weekday())

    history_weeks_count = 4
    start_base = latest_week_start - dt_timedelta(weeks=history_offset * history_weeks_count)
    history_starts = [start_base - dt_timedelta(weeks=i) for i in range(history_weeks_count)]

    weekly_history = (
        BandOfTheWeek.objects
        .filter(week_start__in=history_starts)
        .select_related("product__category")
        .order_by("-week_start")
    )
    history = []
    for w in weekly_history:
        week_end = w.week_start + dt_timedelta(days=6)
        history.append({
            "deal": w,
            "start": w.week_start,
            "end": week_end,
        })

    min_week_start = (
        BandOfTheWeek.objects
        .order_by("week_start")
        .values_list("week_start", flat=True)
        .first()
    )
    oldest_shown = history_starts[-1] if history_starts else None
    has_next_history = bool(min_week_start and oldest_shown and oldest_shown > min_week_start)
    has_prev_history = history_offset > 0

    html = render_to_string("store/_botw_history_cards.html", {"history": history})
    return JsonResponse({
        "success": True,
        "html": html,
        "h": history_offset,
        "has_prev": has_prev_history,
        "has_next": has_next_history,
    })


def shop(request):
    products_list = (
        store_models.Product.objects.filter(status="published")
        .select_related('category', 'category__parent', 'category__parent__parent')
    )
    products = paginate_queryset(request, products_list, 20)

    categories = (
        store_models.Category.objects.filter(parent__isnull=True)
        .prefetch_related("subcategories__subcategories")
    )
    # Color groups for color filter (sorted light → dark by perceived brightness)
    color_groups = list(store_models.ColorGroup.objects.all())
    color_groups.sort(key=lambda cg: _perceived_brightness(getattr(cg, "hex_code", "")), reverse=True)

    item_display = [
        {"id": "12", "value": 12},
        {"id": "20", "value": 20},
        {"id": "40", "value": 40},
        {"id": "60", "value": 60},
        {"id": "100", "value": 100},
    ]

    ratings = [
        {"id": "1", "value": "★☆☆☆☆"},
        {"id": "2", "value": "★★☆☆☆"},
        {"id": "3", "value": "★★★☆☆"},
        {"id": "4", "value": "★★★★☆"},
        {"id": "5", "value": "★★★★★"},
    ]

    prices = [
        {"id": "lowest", "value": "Най-висока към най-ниска"},
        {"id": "highest", "value": "Най-ниска към най-висока"},
    ]

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Магазин", "url": ""},
    ]

    context = {
        "products": products,
        "products_list": products_list,
        "categories": categories,
        "color_groups": color_groups,
        "item_display": item_display,
        "ratings": ratings,
        "prices": prices,
        "user_wishlist_products": get_user_wishlist_products(request),
        "breadcrumbs": breadcrumbs,
    }
    context["is_shop"] = True
    return render(request, "store/shop.html", context)


def sale(request):
    products_list = (
        store_models.Product.objects.filter(status="published", on_sale=True)
        .select_related('category', 'category__parent', 'category__parent__parent')
    )
    products = paginate_queryset(request, products_list, 20)

    categories = (
        store_models.Category.objects.filter(parent__isnull=True)
        .prefetch_related("subcategories__subcategories")
    )
    color_groups = list(store_models.ColorGroup.objects.all())
    color_groups.sort(key=lambda cg: _perceived_brightness(getattr(cg, "hex_code", "")), reverse=True)

    item_display = [
        {"id": "12", "value": 12},
        {"id": "20", "value": 20},
        {"id": "40", "value": 40},
        {"id": "60", "value": 60},
        {"id": "100", "value": 100},
    ]

    ratings = [
        {"id": "1", "value": "★☆☆☆☆"},
        {"id": "2", "value": "★★☆☆☆"},
        {"id": "3", "value": "★★★☆☆"},
        {"id": "4", "value": "★★★★☆"},
        {"id": "5", "value": "★★★★★"},
    ]

    prices = [
        {"id": "lowest", "value": "Най-висока към най-ниска"},
        {"id": "highest", "value": "Най-ниска към най-висока"},
    ]

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Разпродажба", "url": ""},
    ]

    # Halloween swarms for sale page
    halloween_bats_top = _generate_halloween_bats(5)
    halloween_bats_bottom = _generate_halloween_bats(5)

    context = {
        "products": products,
        "products_list": products_list,
        "categories": categories,
        "color_groups": color_groups,
        "item_display": item_display,
        "ratings": ratings,
        "prices": prices,
        "user_wishlist_products": get_user_wishlist_products(request),
        "breadcrumbs": breadcrumbs,
    }
    context["is_shop"] = True
    context["halloween_bats_top"] = halloween_bats_top
    context["halloween_bats_bottom"] = halloween_bats_bottom
    return render(request, "store/sale.html", context)


def category(request, category_path):
    slugs = category_path.strip("/").split("/")
    category = None
    parent = None
    for slug in slugs:
        category = get_object_or_404(Category, slug=slug, parent=parent)
        parent = category

    category = Category.objects.select_related('parent', 'parent__parent').get(pk=category.pk)

    # Direct children
    child_categories_qs = Category.objects.filter(parent=category).select_related('parent', 'parent__parent')
    child_categories = list(child_categories_qs)
    # Virtual linked children
    linked_qs = Category.objects.filter(linked_parents__parent=category).select_related('parent', 'parent__parent')
    # Merge unique
    child_ids = {c.id for c in child_categories}
    for lc in linked_qs:
        if lc.id not in child_ids:
            child_categories.append(lc)
            child_ids.add(lc.id)
    all_sub = category
    all_sub.is_all = True
    subcategories_with_all = [all_sub] + child_categories

    # Products in this category including additional placements
    products_list = (
        Product.objects.filter(status="published")
        .filter(models.Q(category=category) | models.Q(additional_categories=category))
        .select_related('category', 'category__parent', 'category__parent__parent')
        .distinct()
    )
    products = paginate_queryset(request, products_list, 12)

    # Build breadcrumbs using get_category_ancestors
    ancestors = get_category_ancestors(category)
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
    ]
    for ancestor in ancestors:
        breadcrumbs.append({"label": ancestor.title, "url": ancestor.get_absolute_url})
    breadcrumbs.append({"label": category.title, "url": ""})

    context = {
        "products": products,
        "category": category,
        "subcategories": subcategories_with_all,
        "user_wishlist_products": get_user_wishlist_products(request),
        "breadcrumbs": breadcrumbs,
    }
    querydict = request.GET.copy()
    if "page" in querydict:
        del querydict["page"]
    querystring = querydict.urlencode()
    context["querystring"] = querystring
    return render(request, "store/category.html", context)


# Utility functions for category tree traversal (for zero-query descendant lookup)
def find_category_node(tree, cat_id):
    """Find a node in the tree by ID."""
    for node in tree:
        if node.id == cat_id:
            return node
        found = find_category_node(getattr(node, "children", []), cat_id)
        if found:
            return found
    return None


def collect_descendant_ids(node):
    """Recursively collect all descendant IDs from a tree node."""
    ids = []
    for child in getattr(node, "children", []):
        ids.append(child.id)
        ids += collect_descendant_ids(child)
    return ids


def category_all_sub(request, category_path):
    slugs = category_path.strip("/").split("/")
    category = None
    parent = None
    for slug in slugs:
        category = get_object_or_404(Category, slug=slug, parent=parent)
        parent = category

    # Get descendant ids from the cached category tree (zero queries)
    category_tree = cache.get("category_tree")
    node = find_category_node(category_tree, category.id)
    if node:
        descendant_ids = [node.id] + collect_descendant_ids(node)
    else:
        descendant_ids = [category.id]

    # Include products whose primary or additional categories are within descendant ids
    products_list = (
        Product.objects.filter(status="published")
        .filter(models.Q(category_id__in=descendant_ids) | models.Q(additional_categories__in=descendant_ids))
        .select_related('category', 'category__parent', 'category__parent__parent')
        .distinct()
    )
    query = request.GET.get("q")
    if query:
        products_list = products_list.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__title__icontains=query)
        )
    products = paginate_queryset(request, products_list, 12)
    ancestors = get_category_ancestors(category) if category else []

    # Build breadcrumbs
    breadcrumbs = [{"label": "Начална Страница", "url": reverse("store:index")}]
    for ancestor in ancestors:
        breadcrumbs.append({"label": ancestor.title, "url": ancestor.get_absolute_url})
    breadcrumbs.append({"label": category.title, "url": category.get_absolute_url})
    breadcrumbs.append({
        "label": f"Всички {category.title}",
        "url": "",
    })

    context = {
        "products": products,
        "category": category,
        "breadcrumbs": breadcrumbs,
        "all_sub_mode": True,
    }
    querydict = request.GET.copy()
    if "page" in querydict:
        del querydict["page"]
    querystring = querydict.urlencode()
    context["querystring"] = querystring
    return render(request, "store/category.html", context)


def product_detail(request, category_path, product_slug):
    # Traverse the category path to resolve the correct category
    slugs = category_path.strip("/").split("/")
    category = None
    parent = None
    for slug in slugs:
        category = get_object_or_404(Category, slug=slug, parent=parent)
        parent = category

    # Fetch the product with all related data to minimize queries
    product = get_object_or_404(
        Product.objects
            .select_related('category', 'category__parent', 'category__parent__parent')
            .prefetch_related('gallery_images', 'colors', 'variants__variant_items'),
        slug=product_slug, category=category, status="published"
    )

    # Load SKU items for size/model options
    sku_items = (
        store_models.ProductItem.objects.filter(product=product)
        .select_related("size")
        .prefetch_related("device_models")
    )
    # Distinct sizes ordered by sort_order
    size_list = []
    seen_sizes = set()
    for it in sku_items:
        if it.size and it.size.id not in seen_sizes:
            size_list.append(it.size)
            seen_sizes.add(it.size.id)
    size_list.sort(key=lambda s: (s.sort_order, s.name.lower()))

    # Distinct device models ordered by sort_order then name
    model_list = []
    seen_models = set()
    for it in sku_items:
        for dm in it.device_models.all():
            if dm.id not in seen_models:
                model_list.append(dm)
                seen_models.add(dm.id)
    model_list.sort(key=lambda m: (getattr(m, "sort_order", 0), m.name.lower()))

    # Build SKU price delta map for front-end (also include qty per exact SKU)
    sku_data = []
    try:
        for it in sku_items:
            size_name = getattr(it.size, "name", None)
            delta_val = float(getattr(it, "price_delta", 0) or 0)
            qty_val = int(getattr(it, "quantity", 0) or 0)
            dms = list(it.device_models.all())
            if dms:
                for dm in dms:
                    sku_data.append({
                        "size": size_name,
                        "model": dm.name,
                        "delta": delta_val,
                        "qty": qty_val,
                    })
            else:
                sku_data.append({
                    "size": size_name,
                    "model": None,
                    "delta": delta_val,
                    "qty": qty_val,
                })
    except Exception:
        sku_data = []

    # Prepare related products (from the same category, exclude self)
    related_products_list = (
        Product.objects.filter(category=category)
        .exclude(id=product.id)
        .select_related('category', 'category__parent', 'category__parent__parent')
        .prefetch_related('gallery_images')
    )
    related_products = paginate_queryset(request, related_products_list, 12)

    # Stock/variant details (all preloaded)
    has_length_variant = any(
        v.variant_type == "length" for v in product.variants.all()
    )
    # Total stock across SKUs (fallback to product.stock if no items yet)
    try:
        total_stock = max([max(0, int(getattr(it, "quantity", 0))) for it in sku_items] or [int(product.stock or 0)])
    except Exception:
        total_stock = int(product.stock or 0)
    product_stock_range = range(1, (total_stock or 0) + 1)

    # Breadcrumbs (use full path, using select_related category for zero extra queries)
    ancestors = get_category_ancestors(product.category)
    breadcrumbs = [{"label": "Начална Страница", "url": reverse("store:index")}]
    for ancestor in ancestors:
        breadcrumbs.append({"label": ancestor.title, "url": ancestor.get_absolute_url})
    breadcrumbs.append({"label": product.category.title, "url": product.category.get_absolute_url})
    breadcrumbs.append({"label": product.name, "url": ""})

    context = {
        "product": product,
        "product_stock_range": product_stock_range,
        "products": related_products,
        "user_wishlist_products": get_user_wishlist_products(request),
        "breadcrumbs": breadcrumbs,
        "has_length_variant": has_length_variant,
        "sizes": size_list,
        "device_models": model_list,
        "sku_data_json": json.dumps(sku_data),
        "total_stock": total_stock,
    }
    return render(request, "store/product_detail.html", context)


def add_to_cart(request):
    # Get parameters from the request (ID, model, size, quantity, cart_id)
    id = request.GET.get("id")
    qty = request.GET.get("qty")
    model = request.GET.get("model")  # device model name
    size = request.GET.get("size")    # size name
    cart_id = request.GET.get("cart_id")
    item_id = request.GET.get("item_id")
    request.session["cart_id"] = cart_id

    # If item_id is provided, update cart item directly (from cart page +/- buttons)
    if item_id:
        cart_item = store_models.Cart.objects.filter(
            id=item_id, cart_id=cart_id
        ).first()
        if not cart_item:
            return JsonResponse({"error": "Cart item not found"}, status=404)
        new_qty = cart_item.qty + int(qty)
        if new_qty < 1:
            cart_item.delete()
            message = "Продуктът е изтрит от количката"
            total_cart_items = store_models.Cart.objects.filter(cart_id=cart_id)
            cart_sub_total = (
                store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
                    sub_total=models.Sum("sub_total")
                )["sub_total"]
                or 0.00
            )
            return JsonResponse(
                {
                    "message": message,
                    "total_cart_items": total_cart_items.count(),
                    "cart_sub_total": "{:,.2f}".format(cart_sub_total),
                    "item_sub_total": "0.00",
                    "current_qty": 0,
                }
            )
        cart_item.qty = new_qty
        cart_item.price = cart_item.product.effective_price
        # Apply product-level promo: charge only for paid units
        try:
            paid_units = cart_item.product.compute_promo_paid_units(cart_item.qty)
        except Exception:
            paid_units = cart_item.qty
        cart_item.sub_total = Decimal(cart_item.product.effective_price) * Decimal(paid_units)
        cart_item.user = request.user if request.user.is_authenticated else None
        cart_item.cart_id = cart_id
        cart_item.save()
        # After saving the change, normalize promos across product variants in this cart
        try:
            recalc_cart_group_promos(store_models.Cart.objects.filter(cart_id=cart_id))
        except Exception:
            pass
        message = "Koличката е обновена"
        total_cart_items = store_models.Cart.objects.filter(cart_id=cart_id)
        cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
            sub_total=models.Sum("sub_total")
        )["sub_total"]
        # Build promo map for dynamic UI update
        promo_map = {}
        try:
            for ci in store_models.Cart.objects.filter(cart_id=cart_id):
                promo_map[str(ci.id)] = int(getattr(ci, "promo_free_units", 0) or 0)
        except Exception:
            pass
        return JsonResponse(
            {
                "message": message,
                "total_cart_items": total_cart_items.count(),
                "cart_sub_total": "{:,.2f}".format(cart_sub_total),
                "item_sub_total": "{:,.2f}".format(cart_item.sub_total),
                "current_qty": cart_item.qty,
                "promo_free_units_by_item": promo_map,
            }
        )

    # Validate required fields for product detail add-to-cart
    if not id or not qty or not cart_id:
        return JsonResponse({"error": "Невалидна заявка."}, status=400)

    # Try to fetch the product, return an error if it doesn't exist
    try:
        product = store_models.Product.objects.get(status="published", id=id)
    except store_models.Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

    # Check if product has any SKU items at all
    has_any_skus = store_models.ProductItem.objects.filter(product=product).exists()

    sku = None
    unit_price = None

    if has_any_skus:
        # If product has ProductItems with size/model, require corresponding selection when relevant
        has_size_dimension = store_models.ProductItem.objects.filter(product=product, size__isnull=False).exists()
        has_model_dimension = store_models.ProductItem.objects.filter(product=product, device_models__isnull=False).exists()
        if has_size_dimension and not (request.GET.get("size")):
            return JsonResponse({"error": "Моля, изберете размер."}, status=400)
        if has_model_dimension and not (request.GET.get("model")):
            return JsonResponse({"error": "Моля, изберете модел."}, status=400)

        # Resolve SKU by size/model selection and validate stock per SKU
        selected_size = None
        if size:
            selected_size = store_models.Size.objects.filter(name=size).first()
            if not selected_size:
                return JsonResponse({"error": "Невалиден размер."}, status=400)

        selected_model = None
        if model:
            selected_model = store_models.DeviceModel.objects.filter(name=model).first()
            if not selected_model:
                return JsonResponse({"error": "Невалиден модел."}, status=400)

        # Find SKU candidates
        sku_qs = store_models.ProductItem.objects.filter(product=product)
        if selected_size:
            sku_qs = sku_qs.filter(size=selected_size)
        if selected_model:
            sku_qs = sku_qs.filter(device_models=selected_model)

        sku = sku_qs.first()
        if not sku:
            return JsonResponse({"error": "Избраната комбинация не е налична."}, status=400)

        if int(qty) > int(getattr(sku, "quantity", 0)):
            return JsonResponse({"error": "Недостатъчна наличност."}, status=404)
        unit_price = sku.effective_price
    else:
        # No SKU items: use product-level stock and price
        if int(qty) > int(product.stock or 0):
            return JsonResponse({"error": "Недостатъчна наличност."}, status=404)
        unit_price = product.effective_price

    cart_item = store_models.Cart.objects.filter(
        cart_id=cart_id,
        product=product,
        model=model,
        size=size,
    ).first()

    if cart_item:
        new_qty = cart_item.qty + int(qty)
        if new_qty < 1:
            cart_item.delete()
            message = "Продуктът е изтрит от количката"
            # recalculate cart_sub_total after deletion
            total_cart_items = store_models.Cart.objects.filter(cart_id=cart_id)
            cart_sub_total = (
                store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
                    sub_total=models.Sum("sub_total")
                )["sub_total"]
                or 0.00
            )
            return JsonResponse(
                {
                    "message": message,
                    "total_cart_items": total_cart_items.count(),
                    "cart_sub_total": "{:,.2f}".format(cart_sub_total),
                    "item_sub_total": "0.00",
                    "current_qty": 0,
                }
            )
        cart_item.qty = new_qty
        # Resolve price from current cart line selection when possible
        if not sku:
            # Try to resolve SKU based on stored size/model on cart item
            try:
                sku_try = store_models.ProductItem.objects.filter(product=cart_item.product)
                if cart_item.size:
                    sku_try = sku_try.filter(size__name=cart_item.size)
                else:
                    sku_try = sku_try.filter(size__isnull=True)
                if cart_item.model:
                    sku_try = sku_try.filter(device_models__name=cart_item.model)
                sku_resolved = sku_try.first()
                line_price = sku_resolved.effective_price if sku_resolved else cart_item.product.effective_price
            except Exception:
                line_price = cart_item.product.effective_price
        else:
            line_price = sku.effective_price
        cart_item.price = line_price
        try:
            paid_units = cart_item.product.compute_promo_paid_units(cart_item.qty)
        except Exception:
            paid_units = cart_item.qty
        cart_item.sub_total = Decimal(line_price) * Decimal(paid_units)
        cart_item.user = request.user if request.user.is_authenticated else None
        cart_item.cart_id = cart_id
        cart_item.size = size
        cart_item.model = model
        cart_item.save()
        message = "Koличката е обновена"
    else:
        if int(qty) < 1:
            return JsonResponse(
                {"error": "Cannot add less than 1 item to cart"}, status=400
            )
        cart = store_models.Cart()
        cart.product = product
        cart.qty = qty
        cart.price = unit_price
        cart.model = model
        cart.size = size
        try:
            paid_units = product.compute_promo_paid_units(int(qty))
        except Exception:
            paid_units = int(qty)
        cart.sub_total = Decimal(unit_price) * Decimal(paid_units)
        cart.user = request.user if request.user.is_authenticated else None
        cart.cart_id = cart_id
        cart.save()
        # After adding a new line, normalize promos across product variants in this cart
        try:
            recalc_cart_group_promos(store_models.Cart.objects.filter(cart_id=cart_id))
        except Exception:
            pass
        cart_item = cart
        message = "Продуктът е добавен в количката"

    # Count the total number of items in the cart
    total_cart_items = store_models.Cart.objects.filter(cart_id=cart_id)
    cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
        sub_total=models.Sum("sub_total")
    )["sub_total"]

    # Return the response with the cart update message and total cart items
    promo_map = {}
    try:
        for ci in store_models.Cart.objects.filter(cart_id=cart_id):
            promo_map[str(ci.id)] = int(getattr(ci, "promo_free_units", 0) or 0)
    except Exception:
        pass
    return JsonResponse(
        {
            "message": message,
            "total_cart_items": total_cart_items.count(),
            "cart_sub_total": "{:,.2f}".format(cart_sub_total),
            "item_sub_total": "{:,.2f}".format(cart_item.sub_total),
            "current_qty": cart_item.qty,
            "promo_free_units_by_item": promo_map,
        }
    )


def cart(request):
    if "cart_id" in request.session:
        cart_id = request.session["cart_id"]
    else:
        cart_id = None

    # Normalize promos across variants before rendering
    try:
        recalc_cart_group_promos(store_models.Cart.objects.filter(cart_id=cart_id))
    except Exception:
        pass

    items = store_models.Cart.objects.filter(cart_id=cart_id).select_related(
        "product",
        "product__category",
        "product__category__parent",
        "product__category__parent__parent"
    )
    cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
        sub_total=models.Sum("sub_total")
    )["sub_total"]

    if not items:
        messages.warning(request, "Количката е празна")
        return redirect("store:index")

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Магазин", "url": reverse("store:shop")},
        {"label": "Количка", "url": ""},
    ]

    context = {
        "items": items,
        "cart_sub_total": cart_sub_total,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "store/cart.html", context)


def delete_cart_item(request):
    id = request.GET.get("id")
    item_id = request.GET.get("item_id")
    cart_id = request.GET.get("cart_id")

    # Validate required fields
    if not id and not item_id and not cart_id:
        return JsonResponse({"error": "Item or Product id not found"}, status=400)

    try:
        product = store_models.Product.objects.get(status="published", id=id)
    except store_models.Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

    # Check if the item is already in the cart
    item = store_models.Cart.objects.get(product=product, id=item_id)
    item.delete()
    # Normalize promos after deletion
    try:
        recalc_cart_group_promos(store_models.Cart.objects.filter(cart_id=cart_id))
    except Exception:
        pass

    # Count the total number of items in the cart
    total_cart_items = store_models.Cart.objects.filter(cart_id=cart_id)
    cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
        sub_total=models.Sum("sub_total")
    )["sub_total"]

    promo_map = {}
    try:
        for ci in store_models.Cart.objects.filter(cart_id=cart_id):
            promo_map[str(ci.id)] = int(getattr(ci, "promo_free_units", 0) or 0)
    except Exception:
        pass
    return JsonResponse(
        {
            "message": "Продуктът е изтрит",
            "total_cart_items": total_cart_items.count(),
            "cart_sub_total": (
                "{:,.2f}".format(cart_sub_total) if cart_sub_total else 0.00
            ),
            "promo_free_units_by_item": promo_map,
        }
    )


def create_order(request):
    # Only allow POST; on GET direct the user back to the cart
    if request.method != "POST":
        messages.warning(request, "Моля, направете поръчка от количката.")
        return redirect("store:cart")

    cart_id = request.session.get("cart_id")
    items = store_models.Cart.objects.filter(cart_id=cart_id)

    # Guard: empty cart
    if not items.exists():
        messages.error(request, "Количката е празна.")
        return redirect("store:cart")

    cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
        sub_total=models.Sum("sub_total")
    )["sub_total"] or 0

    shipping = 0.00
    order = store_models.Order()
    order.sub_total = cart_sub_total
    order.customer = request.user if request.user.is_authenticated else None
    order.shipping = shipping
    order.total = (order.sub_total or 0) + (order.shipping or 0)
    order.save()

    # Before snapshotting items to the order, recalc promos at cart level to ensure correct sub_totals
    try:
        recalc_cart_group_promos(items)
    except Exception:
        pass

    for i in items:
        # Snapshot price and sub_total exactly as in cart to avoid rounding/alloc mismatch
        line_price = Decimal(str(i.price or 0))
        sub_total_snapshot = Decimal(str(i.sub_total or 0))
        store_models.OrderItem.objects.create(
            order=order,
            product=i.product,
            qty=i.qty,
            model=i.model,
            size=i.size,
            price=line_price,
            sub_total=sub_total_snapshot,
        )

    return redirect("store:checkout", order.order_id)


def coupon_apply(request, order_id):
    print("Order Id ========", order_id)

    try:
        order = store_models.Order.objects.get(order_id=order_id)
    except store_models.Order.DoesNotExist:
        msg = "Поръчката не беше намерена."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
        return redirect("store:cart")

    if request.method == "POST":
        coupon_code = request.POST.get("coupon_code")

        if not coupon_code:
            msg = "Моля, въведете купон."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg})
            messages.error(request, msg)
            return redirect("store:checkout", order.order_id)

        try:
            coupon = store_models.Coupon.objects.get(code=coupon_code)
        except store_models.Coupon.DoesNotExist:
            msg = "Купонът не съществува."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg})
            messages.error(request, msg)
            return redirect("store:checkout", order.order_id)

        # Enforce SPIN coupon validity: same user, same day
        if coupon.code.startswith("SPIN-"):
            if not request.user.is_authenticated:
                msg = "Трябва да сте влезли, за да използвате този купон."
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': msg})
                messages.error(request, msg)
                return redirect("store:checkout", order.order_id)
            spin = store_models.SpinEntry.objects.filter(user=request.user, coupon_code=coupon.code).first()
            if not spin:
                msg = "Този купон не е валиден за вашия акаунт."
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': msg})
                messages.error(request, msg)
                return redirect("store:checkout", order.order_id)
            if spin.date != timezone.localdate():
                msg = "Купонът от колелото е валиден само за днес."
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': msg})
                messages.error(request, msg)
                return redirect("store:checkout", order.order_id)

        # Always clear any existing coupons and reset saved and total
        order.coupons.clear()
        order.saved = round2(0)
        order.total = round2(order.sub_total + (order.shipping or 0))

        # Apply coupon, recalculate everything in one place!
        order.coupons.add(coupon)
        apply_coupon_discount(order)

        msg = "Купонът е активиран."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # Render the updated summary and items HTML
            summary_html = render_to_string("store/_checkout_summary.html", {"order": order})
            items_html = render_to_string("store/_checkout_items.html", {"order": order})
            return JsonResponse({
                'success': True,
                'message': msg,
                'summary_html': summary_html,
                'items_html': items_html,
            })
        messages.success(request, msg)
        return redirect("store:checkout", order.order_id)

    return redirect("store:checkout", order_id)


def checkout(request, order_id):
    order = (
        store_models.Order.objects
        .prefetch_related(
            models.Prefetch(
                "order_items",
                queryset=store_models.OrderItem.objects.select_related(
                    "product",
                    "product__category",
                    "product__category__parent",
                    "product__category__parent__parent"
                ),
            )
        )
        .get(order_id=order_id)
    )

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Магазин", "url": reverse("store:shop")},
        {"label": "Количка", "url": reverse("store:cart")},
        {"label": "Поръчка", "url": ""},
    ]

    cart_total_weight = 0
    for item in order.order_items.all():
        cart_total_weight += 0.1 * item.qty

    address = None
    if request.user.is_authenticated:
        # Prefer main address for autofill; fallback to most recent if no main exists
        main_address = customer_models.Address.objects.filter(user=request.user, is_main=True).first()
        if main_address:
            address = main_address
        else:
            address = customer_models.Address.objects.filter(user=request.user).order_by('-id').first()
    econt_params = {
        "id_shop": settings.ECONT_SHOP_ID,
        "order_total": float(order.total) or 0,
        "order_currency": "BGN", 
        "order_weight": cart_total_weight,
        "customer_name": address.name if address and getattr(address, "name", None) else "",
        "customer_phone": address.phone if address and getattr(address, "phone", None) else "",
        "customer_email": address.email if address and address.email else "",
        "customer_city_name": address.city if address and address.city else "",
    }
    if address:
        if address.delivery_method == "econt_office" and address.office_code:
            econt_params["customer_office_code"] = address.office_code
        elif address.delivery_method == "econt" and address.address:
            econt_params["customer_address"] = address.address
    econt_url = f"{settings.ECONT_SHIPPMENT_CALC_URL}?{urlencode(econt_params)}"

    context = {
        "order": order,
        "stripe_public_key": settings.STRIPE_PUBLIC_KEY,
        "breadcrumbs": breadcrumbs,
        "econt_url": econt_url,
    }

    return render(request, "store/checkout.html", context)


def cod_payment(request, order_id):
    if request.method == "POST":
        order = store_models.Order.objects.get(order_id=order_id)
        order.payment_method = "cash_on_delivery"
        order.payment_status = "cash_on_delivery"
        # Mark order as received when customer confirms COD
        order.order_status = "received"
        _send_shipment(order)
        try:
            send_meta_purchase_event(order, request)
        except Exception:
            pass
        order.save()
        send_order_notification_email(
            order=order,
            email_heading=f"Потвърдена поръчка #{order.order_id}",
            email_title="iBands: Приета поръчка",
            to_email=order.address.email,
        )
        send_order_notification_email(
            order=order,
            email_heading=f"Потвърдена поръчка #{order.order_id}",
            email_title="iBands: Приета поръчка",
            to_email=settings.ORDER_NOTIFICATION_EMAIL,
        )

        if request.user.is_authenticated:
            customer_models.Notifications.objects.create(
                type="New Order", user=request.user
            )
        clear_cart_items(request)
        return redirect(
            reverse("store:payment_status", args=[order.order_id])
            + "?payment_status=paid"
        )
    else:
        return redirect("store:checkout", order_id)


@login_required
def spin_page(request):
    today = timezone.localdate()
    # Compute next reset at local midnight (start of next day)
    try:
        from datetime import datetime as _dt, time as _time
        tz = timezone.get_current_timezone()
        tomorrow = today + dt_timedelta(days=1)
        reset_at = timezone.make_aware(_dt.combine(tomorrow, _time.min), tz)
    except Exception:
        reset_at = None
    last_spin = SpinEntry.objects.filter(user=request.user).order_by("-date", "-created_at").first()
    can_spin = True
    next_spin_date = today
    if last_spin and last_spin.date == today:
        can_spin = False
        next_spin_date = today + dt_timedelta(days=1)

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Колелото на късмета", "url": ""},
    ]

    # Provide current active prizes to drive client wheel rendering
    prizes_qs = SpinPrize.objects.filter(active=True).order_by("sort_order", "id")
    prizes = [
        {
            "label": p.label,
            "type": p.prize_type,
            "discount_percent": int(p.discount_percent or 0),
            "min_order_total": float(p.min_order_total) if p.min_order_total is not None else None,
            "color": p.color or "#ffe082",
            "weight": float(p.weight or 0),
        }
        for p in prizes_qs
    ]

    # Milestone progress (spin page)
    try:
        milestones_qs = SpinMilestone.objects.filter(active=True).order_by("threshold_spins", "id")
        spin_milestones = [
            {
                "threshold_spins": int(m.threshold_spins),
                "label": m.label,
                "prize_type": m.prize_type,
                "discount_percent": int(m.discount_percent or 0),
                "min_order_total": float(m.min_order_total) if m.min_order_total is not None else None,
            }
            for m in milestones_qs
        ]
    except Exception:
        spin_milestones = []
    spin_total_spins = SpinEntry.objects.filter(user=request.user).count()
    _awards_qs = SpinMilestoneAward.objects.filter(user=request.user).select_related("milestone")
    achieved_thresholds = [int(a.milestone.threshold_spins) for a in _awards_qs]
    achieved_details = [
        {
            "threshold_spins": int(a.milestone.threshold_spins),
            "label": a.milestone.label,
            "prize_type": a.milestone.prize_type,
            "discount_percent": int(a.milestone.discount_percent or 0),
            "min_order_total": float(a.milestone.min_order_total) if a.milestone.min_order_total is not None else None,
            "coupon_code": a.coupon_code,
        }
        for a in _awards_qs
    ]

    context = {
        "can_spin": can_spin,
        "last_spin": last_spin,
        "next_spin_date": next_spin_date,
        "breadcrumbs": breadcrumbs,
        "reset_at_iso": reset_at.isoformat() if reset_at else None,
        "prizes": prizes,
        "prizes_json": json.dumps(prizes, ensure_ascii=False),
        "spin_url": reverse("store:spin_perform"),
        # server + client milestone data
        "spin_milestones": spin_milestones,
        "spin_milestones_json": json.dumps(spin_milestones, ensure_ascii=False),
        "spin_milestone_progress_json": json.dumps({
            "spins": spin_total_spins,
            "achieved": achieved_thresholds,
        }),
        "spin_achieved_details": achieved_details,
        "spin_achieved_details_json": json.dumps(achieved_details, ensure_ascii=False),
    }
    return render(request, "store/spin.html", context)


@require_POST
def spin_perform(request):
    if not request.user.is_authenticated:
        return JsonResponse({
            "success": False,
            "message": "Моля, влезте или се регистрирайте, за да завъртите.",
            "login_url": reverse("userauths:sign-in") + "?next=" + request.path,
        }, status=401)
    today = timezone.localdate()
    # Enforce one spin per day
    if SpinEntry.objects.filter(user=request.user, date=today).exists():
        return JsonResponse({
            "success": False,
            "message": "Вече завъртя днес. Опитай отново утре!",
        }, status=400)

    # Load active prizes from DB, fallback to defaults if none configured
    prizes_qs = SpinPrize.objects.filter(active=True).order_by("sort_order", "id")
    outcomes = []
    if prizes_qs.exists():
        for p in prizes_qs:
            outcomes.append({
                "label": p.label,
                "type": p.prize_type,
                "discount_percent": int(p.discount_percent or 0),
                "min_order_total": float(p.min_order_total) if p.min_order_total is not None else None,
                "weight": float(p.weight or 0),
                "color": p.color or None,
            })
    else:
        outcomes = [
            {"label": "Опитай пак утре", "type": "none", "discount_percent": 0, "min_order_total": None, "weight": 0.45, "color": "#ffd54f"},
            {"label": "Отстъпка 3%", "type": "discount_percent", "discount_percent": 3, "min_order_total": None, "weight": 0.25, "color": "#fff9c4"},
            {"label": "Отстъпка 5%", "type": "discount_percent", "discount_percent": 5, "min_order_total": None, "weight": 0.15, "color": "#ffe082"},
            {"label": "Безплатна доставка", "type": "free_shipping", "discount_percent": 0, "min_order_total": None, "weight": 0.07, "color": "#fff59d"},
            {"label": "Mystery Box", "type": "mystery_box_min_total", "discount_percent": 0, "min_order_total": 20.00, "weight": 0.08, "color": "#ffecb3"},
        ]

    r = random.random()
    cumulative = 0.0
    selected = outcomes[-1]
    for item in outcomes:
        w = float(item.get("weight", 0))
        cumulative += w
        if r <= cumulative:
            selected = item
            break

    coupon_code = None
    if selected["type"] == "discount_percent" and selected.get("discount_percent"):
        # Generate a unique coupon code
        # Keep it short but not easily guessable
        code = f"SPIN-{request.user.id}-{random.randint(100000, 999999)}"
        coupon = Coupon.objects.create(code=code, discount=int(selected["discount_percent"]))
        coupon_code = coupon.code

    entry = SpinEntry.objects.create(
        user=request.user,
        date=today,
        result_label=selected["label"],
        prize_type=selected["type"],
        coupon_discount_percent=(int(selected["discount_percent"]) if selected.get("discount_percent") else None),
        free_shipping=(selected["type"] == "free_shipping"),
        min_order_total=(Decimal(str(selected["min_order_total"])) if selected.get("min_order_total") else None),
        coupon_code=coupon_code,
    )

    # Compute user's lifetime spin count and check milestones
    total_spins = SpinEntry.objects.filter(user=request.user).count()
    milestone_payload = None
    from store.models import SpinMilestone, SpinMilestoneAward  # local import to avoid cycles
    try:
        milestones = list(SpinMilestone.objects.filter(active=True, threshold_spins__lte=total_spins).order_by('threshold_spins'))
        for ms in milestones:
            already_awarded = SpinMilestoneAward.objects.filter(user=request.user, milestone=ms).exists()
            if already_awarded:
                continue
            # Award this milestone
            ms_coupon_code = None
            if ms.prize_type == 'discount_percent' and ms.discount_percent:
                ms_code = f"MS-{request.user.id}-{ms.threshold_spins}-{random.randint(100000,999999)}"
                Coupon.objects.create(code=ms_code, discount=int(ms.discount_percent))
                ms_coupon_code = ms_code
            SpinMilestoneAward.objects.create(user=request.user, milestone=ms, coupon_code=ms_coupon_code)
            milestone_payload = {
                "threshold_spins": ms.threshold_spins,
                "label": ms.label,
                "prize_type": ms.prize_type,
                "discount_percent": int(ms.discount_percent or 0),
                "min_order_total": float(ms.min_order_total) if ms.min_order_total is not None else None,
                "coupon_code": ms_coupon_code,
            }
    except Exception:
        milestone_payload = None

    # Persist reward in session for UI hints at checkout
    try:
        request.session["spin_reward"] = {
            "date": str(today),
            "label": selected["label"],
            "type": selected["type"],
            "discount_percent": (int(selected["discount_percent"]) if selected.get("discount_percent") else 0),
            "min_order_total": selected.get("min_order_total"),
            "coupon_code": coupon_code,
        }
        request.session.modified = True
    except Exception:
        pass

    return JsonResponse({
        "success": True,
        "label": selected["label"],
        "coupon_code": coupon_code,
        "discount_percent": (int(selected["discount_percent"]) if selected.get("discount_percent") else 0),
        "prize_type": selected["type"],
        "min_order_total": selected.get("min_order_total"),
        "outcomes": outcomes,
        "milestone": milestone_payload,
    })

@csrf_exempt
def stripe_payment(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    checkout_session = stripe.checkout.Session.create(
        customer_email=order.address.email,
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "BGN",
                    "product_data": {"name": order.address.name},
                    "unit_amount": int(order.total * 100),
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url=request.build_absolute_uri(
            reverse("store:stripe_payment_verify", args=[order.order_id])
        )
        + "?session_id={CHECKOUT_SESSION_ID}"
        + "&payment_method=Stripe",
        cancel_url=request.build_absolute_uri(
            reverse("store:stripe_payment_verify", args=[order.order_id])
        )
        + "?canceled=1",
    )

    print("checkkout session", checkout_session)
    return JsonResponse({"sessionId": checkout_session.id})


def stripe_payment_verify(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Handle explicit cancel or missing session id gracefully
    if request.GET.get("canceled") == "1":
        # Mark as failed if not already paid
        if order.payment_status != "paid":
            order.payment_status = "failed"
            if not order.payment_method:
                order.payment_method = "card"
            order.save(update_fields=["payment_status", "payment_method"])
        return redirect(reverse("store:payment_status", args=[order.order_id]) + "?payment_status=failed")

    session_id = request.GET.get("session_id")
    if not session_id:
        if order.payment_status != "paid":
            order.payment_status = "failed"
            if not order.payment_method:
                order.payment_method = "card"
            order.save(update_fields=["payment_status", "payment_method"])
        return redirect(reverse("store:payment_status", args=[order.order_id]) + "?payment_status=failed")

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        if order.payment_status != "paid":
            order.payment_status = "failed"
            if not order.payment_method:
                order.payment_method = "card"
            order.save(update_fields=["payment_status", "payment_method"])
        return redirect(reverse("store:payment_status", args=[order.order_id]) + "?payment_status=failed")

    if getattr(session, "payment_status", None) == "paid":
        if order.payment_status != "paid":
            # Prefer payment_intent/id as a stable event id for deduplication
            try:
                order.payment_id = getattr(session, "payment_intent", None) or getattr(session, "id", None)
            except Exception:
                pass
            order.payment_status = "paid"
            order.payment_method = "card"
            # Mark order as received upon successful payment
            order.order_status = "received"
            _send_shipment(order)
            try:
                send_meta_purchase_event(order, request)
            except Exception:
                pass
            order.save()
            send_order_notification_email(
                order=order,
                email_heading=f"Потвърдена поръчка #{order.order_id}",
                email_title="iBands: Приета поръчка",
                to_email=order.address.email,
            )
            send_order_notification_email(
                order=order,
                email_heading=f"Потвърдена поръчка #{order.order_id}",
                email_title="iBands: Приета поръчка",
                to_email=settings.ORDER_NOTIFICATION_EMAIL,
            )
            if request.user.is_authenticated:
                customer_models.Notifications.objects.create(
                    type="New Order", user=request.user
                )
            clear_cart_items(request)
        return redirect(
            reverse("store:payment_status", args=[order.order_id]) + "?payment_status=paid"
        )

    # Not paid: mark as failed
    if order.payment_status != "paid":
        order.payment_status = "failed"
        if not order.payment_method:
            order.payment_method = "card"
        order.save(update_fields=["payment_status", "payment_method"])
    return redirect(reverse("store:payment_status", args=[order.order_id]) + "?payment_status=failed")


def payment_status(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)
    payment_status = request.GET.get("payment_status")

    context = {"order": order, "payment_status": payment_status}
    return render(request, "store/payment_status.html", context)


@require_POST
def set_payment_method(request, order_id):
    """
    Persist the customer's selected payment method (e.g., 'card' or 'cash_on_delivery')
    without changing payment_status. This lets us restore their choice if they return.

    Distinguishing completed vs not:
    - payment_status remains 'processing' until Stripe success or COD is confirmed.
    - This view only updates order.payment_method.
    """
    try:
        order = store_models.Order.objects.get(order_id=order_id)
    except store_models.Order.DoesNotExist:
        return JsonResponse({"success": False, "message": "Поръчката не беше намерена."}, status=404)

    # Accept JSON or form-encoded
    payment_method = None
    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body or b"{}")
            payment_method = (payload.get("payment_method") or "").strip()
        except Exception:
            payment_method = None
    if not payment_method:
        payment_method = (request.POST.get("payment_method") or "").strip()

    allowed = {"card", "cash_on_delivery"}
    if payment_method not in allowed:
        return JsonResponse({"success": False, "message": "Невалиден метод на плащане."}, status=400)

    # If already paid, do not change persisted method
    if order.payment_status == "paid":
        return JsonResponse({"success": True, "message": "Поръчката вече е платена.", "payment_method": order.payment_method})

    order.payment_method = payment_method
    order.save(update_fields=["payment_method"])
    return JsonResponse({"success": True, "payment_method": order.payment_method})


def filter_products(request):
    products = store_models.Product.objects.all()

    # Get filters from the AJAX request
    categories = request.GET.getlist("categories[]")
    rating = request.GET.getlist("rating[]")
    sizes = request.GET.getlist("sizes[]")
    colors = request.GET.getlist("colors[]")
    price_order = request.GET.get("prices")
    search_filter = request.GET.get("searchFilter")
    display = request.GET.get("display")
    page = request.GET.get("page", 1)

    # Apply category filtering
    if categories:
        # Use the cached category tree for descendant lookup
        category_tree = cache.get("category_tree")
        all_category_ids = []
        for cid in categories:
            try:
                cid_int = int(cid)
                node = find_category_node(category_tree, cid_int)
                if node:
                    all_category_ids.append(node.id)
                    all_category_ids.extend(collect_descendant_ids(node))
            except Exception:
                continue
        products = products.filter(
            models.Q(category__id__in=all_category_ids) |
            models.Q(additional_categories__id__in=all_category_ids)
        ).distinct()

    # Apply rating filtering
    if rating:
        products = products.filter(reviews__rating__in=rating).distinct()

    # Apply size filtering (by ProductItem sizes)
    if sizes:
        products = products.filter(items__size__name__in=sizes).distinct()

    # Apply color filtering by selected color group ids
    if colors:
        try:
            color_group_ids = [int(cid) for cid in colors]
        except Exception:
            color_group_ids = []
        if color_group_ids:
            products = products.filter(
                colors__group__id__in=color_group_ids
            ).distinct()

    # Apply price ordering (by effective price: sale_price if lower, else price)
    if price_order in {"lowest", "highest"}:
        products = products.annotate(
            sort_price=models.Case(
                models.When(
                    models.Q(sale_price__isnull=False) & models.Q(sale_price__lt=models.F("price")),
                    then=models.F("sale_price"),
                ),
                default=models.F("price"),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        )
        if price_order == "lowest":
            products = products.order_by("-sort_price")
        else:
            products = products.order_by("sort_price")

    # Apply search filter
    if search_filter:
        products = products.filter(
            Q(name__icontains=search_filter) |
            Q(description__icontains=search_filter) |
            Q(category__title__icontains=search_filter)
        )

    # Determine items per page
    try:
        per_page = int(display) if display else 20
    except Exception:
        per_page = 20

    # Paginate filtered queryset
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    paginator = Paginator(products, per_page)
    try:
        products_page = paginator.page(page)
    except PageNotAnInteger:
        products_page = paginator.page(1)
    except EmptyPage:
        products_page = paginator.page(paginator.num_pages)

    user_wishlist_products = get_user_wishlist_products(request)
    product_html_list = [
        render_to_string(
            "partials/_product_list.html",
            {
                "product": product,
                "user_wishlist_products": user_wishlist_products,
            }
        )
        for product in products_page
    ]
    html = ''.join(product_html_list)
    pagination_html = render_to_string(
        "partials/_pagination.html", {"products": products_page, "is_shop": True}
    )

    return JsonResponse(
        {
            "html": html,
            "pagination_html": pagination_html,
            "product_count": paginator.count,
        }
    )


def order_tracker_page(request):
    if request.method == "POST":
        key = request.POST.get("item_id", "").strip()
        order = store_models.Order.objects.filter(order_id=key).first()
        if not order:
            order = store_models.Order.objects.filter(tracking_id=key).first()

        if not order:
            messages.error(request, "Поръчката не беше намерена.")
            return redirect("store:order_tracker_page")

        return redirect("customer:order_detail", order.order_id)

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Проследяване на поръчка", "url": ""},
    ]
    return render(
        request, "store/order_tracker_page.html", {"breadcrumbs": breadcrumbs}
    )


def about(request):
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "За Нас", "url": ""},
    ]
    return render(request, "pages/about.html", {"breadcrumbs": breadcrumbs})


def contact(request):
    if request.method == "POST":
        full_name = request.POST.get("full_name")
        email = request.POST.get("email")
        subject = request.POST.get("subject")
        message = request.POST.get("message")

        userauths_models.ContactMessage.objects.create(
            full_name=full_name,
            email=email,
            subject=subject,
            message=message,
        )
        messages.success(request, "Съобщението е изпратено успешно")
        return redirect("store:contact")

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Контакти", "url": ""},
    ]
    return render(request, "pages/contact.html", {"breadcrumbs": breadcrumbs})


def faqs(request):
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Често задавани въпроси", "url": ""},
    ]
    return render(request, "pages/faqs.html", {"breadcrumbs": breadcrumbs})


def privacy_policy(request):
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Политика за поверителност", "url": ""},
    ]
    return render(request, "pages/privacy_policy.html", {"breadcrumbs": breadcrumbs})


def terms_conditions(request):
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Общи условия", "url": ""},
    ]
    return render(request, "pages/terms_conditions.html", {"breadcrumbs": breadcrumbs})


def returns_and_exchanges(request):
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Доставка и връшане", "url": ""},
    ]
    return render(
        request, "pages/returns_and_exchanges.html", {"breadcrumbs": breadcrumbs}
    )


@require_POST
def subscribe_newsletter(request):
    email = request.POST.get("email")
    try:
        validate_email(email)
        # Prevent duplicates
        obj, created = userauths_models.NewsletterSubscription.objects.get_or_create(email=email)
        if created:
            return JsonResponse({"success": True, "message": "Успешно се абонирахте!"})
        else:
            return JsonResponse({"success": False, "message": "Този имейл вече е абониран."})
    except ValidationError:
        return JsonResponse({"success": False, "message": "Невалиден имейл адрес."})


def is_bot_request(request):
    user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
    bot_keywords = [
        "bot", "crawl", "slurp", "spider", "mediapartners", "facebookexternalhit",
        "meta-externalagent", "twitterbot", "bingpreview", "yandex", "duckduckbot"
    ]
    return any(bot in user_agent for bot in bot_keywords)


def get_client_ip(request):
    # Prefer HTTP_X_FORWARDED_FOR if behind a proxy (e.g., nginx, cloudflare)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Sometimes X-Forwarded-For can contain multiple IPs, use the first
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip

def custom_server_error(request):
    is_bot = is_bot_request(request)
    ip = get_client_ip(request)
    increment_500_error_count(is_bot=is_bot, ip=ip)
    if is_bot:
        return render(request, "500_bot.html", status=500)
    else:
        return render(request, "500.html", status=500)