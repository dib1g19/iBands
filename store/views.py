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
from datetime import date as dt_date, datetime as dt_datetime
import calendar as pycal
from decimal import Decimal, ROUND_HALF_UP
from .models import Category, Product, BandOfTheDay
import stripe
from store.utils import (
    paginate_queryset,
    floor_to_cent,
    speedy_v1_find_sites,
    speedy_v1_find_offices,
    speedy_v1_calculate,
    speedy_v1_create_shipment,
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
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

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
            return None

        # Now, call the createAWB endpoint to generate the AWB/label
        create_awb_url = url.replace("OrdersService.updateOrder", "OrdersService.createAWB")
        try:
            awb_response = requests.post(create_awb_url, headers=headers, json=data, timeout=10)
            if awb_response.status_code == 200:
                awb_json = awb_response.json()
                shipment_number = awb_json.get("shipmentNumber")
                if shipment_number:
                    order.tracking_id = shipment_number
                    order.save(update_fields=["tracking_id"])
                return awb_json
        except Exception:
            pass
        return None
    else:
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

        calc_req = {
            "payer": "RECIPIENT" if order.payment_method == "cash_on_delivery" else "SENDER",
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
    shipment_request = {
        "language": "BG",
        "service": {
            "serviceId": service_id or getattr(settings, "SPEEDY_DEFAULT_SERVICE_ID", None),
            "additionalServices": {
                **({"cod": {"amount": float(order.sub_total), "processingType": "CASH"}} if is_cod else {}),
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
            "courierServicePayer": ("RECIPIENT" if is_cod else "SENDER"),
            "declaredValuePayer": ("RECIPIENT" if is_cod else "SENDER"),
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
            # Update shipping only when a valid shipping price was provided
            if shipping_price is not None:
                order.shipping = shipping_price
            # Coupon logic: recalculate discount and totals if coupon is applied
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
            if shipping_price is not None:
                order.shipping = shipping_price
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
        base_price = Decimal(str(item.product.effective_price or 0))
        if coupon:
            discount = Decimal(str(coupon.discount)) / Decimal("100")
            discounted_price = round2(base_price * (Decimal("1") - discount))
            item.price = discounted_price
            item.sub_total = round2(discounted_price * item.qty)
        else:
            item.price = base_price
            item.sub_total = round2(base_price * item.qty)
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
        if is_cod:
            calc_request["service"] = {
                "additionalServices": {
                    "cod": {"amount": float(order.sub_total), "processingType": "CASH"}
                }
            }
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
    )
    products = paginate_queryset(request, products_list, 20)

    # Sale products (manually marked)
    sale_products = (
        store_models.Product.objects.filter(status="published", on_sale=True)
        .select_related('category', 'category__parent', 'category__parent__parent')[:12]
    )

    categories = store_models.Category.objects.filter(parent__isnull=True)
    popular_categories = (
        store_models.Category.objects
            .filter(is_popular=True)
            .select_related('parent', 'parent__parent')
    )


    # Band of the Day (50% off)
    band_of_the_day = BandOfTheDay.get_today()
    band_product = getattr(band_of_the_day, "product", None)
    band_override_price = None
    band_discount_percent = None
    if band_product and band_product.price:
        half = band_product.price * Decimal("0.5")
        band_override_price = floor_to_cent(half)
        band_discount_percent = 50

    band_of_the_day_url = reverse("store:band_of_the_day") if band_product else None
    band_date = getattr(band_of_the_day, "date", None)

    context = {
        "products": products,
        "sale_products": sale_products,
        "categories": categories,
        "popular_categories": popular_categories,
        "user_wishlist_products": get_user_wishlist_products(request),
        "band_of_the_day": band_product,
        "band_price": band_override_price,
        "band_discount_percent": band_discount_percent,
        "band_of_the_day_url": band_of_the_day_url,
        "band_date": band_date,
    }
    return render(request, "store/index.html", context)


def band_of_the_day(request):
    # Parse selected date from query (?date=YYYY-MM-DD). Default to today.
    date_str = request.GET.get("date")
    try:
        selected_date = dt_datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else dt_date.today()
    except Exception:
        selected_date = dt_date.today()

    # Get deal for selected date; fallback to today's if requested date has no deal
    deal = BandOfTheDay.objects.filter(date=selected_date).select_related("product__category").first()
    if not deal:
        deal = BandOfTheDay.get_today()
        selected_date = deal.date if deal else selected_date
    product = getattr(deal, "product", None) if deal else None
    if not product:
        messages.info(request, "Няма избрана каишка за тази дата.")
        return redirect("store:index")

    # Refetch product with related data for efficient template rendering
    product = (
        Product.objects
        .select_related('category', 'category__parent', 'category__parent__parent')
        .prefetch_related('gallery_images', 'colors', 'variants__variant_items')
        .get(pk=product.pk)
    )

    # Prepare breadcrumbs
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Каишка на деня", "url": ""},
    ]

    # Explicit price values for display and override sale display to -50% (only for today)
    original_price = product.price
    half = product.price * Decimal("0.5") if product and product.price else None
    discounted_price = floor_to_cent(half) if half is not None else product.effective_price
    # For today's deal: show discounted price. For past days: show regular price
    if deal.date == dt_date.today():
        product.sale_price = discounted_price
    else:
        product.sale_price = None
    product_stock_range = range(1, (product.stock or 0) + 1)
    has_length_variant = any(v.variant_type == "length" for v in product.variants.all())

    # Build month calendar for history
    first_day = selected_date.replace(day=1)
    # Compute next month start safely
    if first_day.month == 12:
        next_month_start = first_day.replace(year=first_day.year + 1, month=1, day=1)
    else:
        next_month_start = first_day.replace(month=first_day.month + 1, day=1)
    month_end = next_month_start
    month_deals = BandOfTheDay.objects.filter(date__gte=first_day, date__lt=month_end).select_related("product__category")
    deals_by_day = {d.date.day: d for d in month_deals}
    cal = pycal.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(first_day.year, first_day.month)  # list of weeks, 0=pad
    # Build template-friendly structure: each cell has {day, deal}
    weeks_data = []
    for wk in weeks:
        row = []
        for d in wk:
            row.append({
                "day": d,
                "deal": deals_by_day.get(d) if d else None,
            })
        weeks_data.append(row)

    # Prev/next month params for navigation
    if first_day.month == 1:
        prev_month = first_day.replace(year=first_day.year - 1, month=12, day=1)
    else:
        prev_month = first_day.replace(month=first_day.month - 1, day=1)
    next_month = next_month_start

    context = {
        "product": product,
        "original_price": original_price,
        "discounted_price": discounted_price,
        "product_stock_range": product_stock_range,
        "has_length_variant": has_length_variant,
        "breadcrumbs": breadcrumbs,
        "user_wishlist_products": get_user_wishlist_products(request),
        "deal_date": deal.date,
        "is_today": (deal.date == dt_date.today()),
        # Calendar context
        "calendar_weeks": weeks,
        "weeks_data": weeks_data,
        "calendar_month": first_day,
        "prev_month": prev_month,
        "next_month": next_month,
        "selected_date": selected_date,
    }
    return render(request, "store/band_of_the_day.html", context)


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
    # Color groups for color filter
    color_groups = store_models.ColorGroup.objects.all()

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
    color_groups = store_models.ColorGroup.objects.all()

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
    return render(request, "store/sale.html", context)


def category(request, category_path):
    slugs = category_path.strip("/").split("/")
    category = None
    parent = None
    for slug in slugs:
        category = get_object_or_404(Category, slug=slug, parent=parent)
        parent = category

    category = Category.objects.select_related('parent', 'parent__parent').get(pk=category.pk)

    child_categories_qs = Category.objects.filter(parent=category).select_related('parent', 'parent__parent')
    child_categories = list(child_categories_qs)
    all_sub = category
    all_sub.is_all = True
    subcategories_with_all = [all_sub] + child_categories

    products_list = (
        Product.objects.filter(status="published", category=category)
        .select_related('category', 'category__parent', 'category__parent__parent')
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

    products_list = (
        Product.objects.filter(status="published", category_id__in=descendant_ids)
        .select_related('category', 'category__parent', 'category__parent__parent')
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
    product_stock_range = range(1, product.stock + 1)

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
    }
    return render(request, "store/product_detail.html", context)


def add_to_cart(request):
    # Get parameters from the request (ID, model, size, quantity, cart_id)
    id = request.GET.get("id")
    qty = request.GET.get("qty")
    model = request.GET.get("model")
    size = request.GET.get("size")
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
        cart_item.sub_total = Decimal(cart_item.product.effective_price) * Decimal(cart_item.qty)
        cart_item.user = request.user if request.user.is_authenticated else None
        cart_item.cart_id = cart_id
        cart_item.save()
        message = "Koличката е обновена"
        total_cart_items = store_models.Cart.objects.filter(cart_id=cart_id)
        cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
            sub_total=models.Sum("sub_total")
        )["sub_total"]
        return JsonResponse(
            {
                "message": message,
                "total_cart_items": total_cart_items.count(),
                "cart_sub_total": "{:,.2f}".format(cart_sub_total),
                "item_sub_total": "{:,.2f}".format(cart_item.sub_total),
                "current_qty": cart_item.qty,
            }
        )

    # Validate required fields for product detail add-to-cart
    if not id or not qty or not cart_id:
        return JsonResponse({"error": "No model or size selected"}, status=400)

    # Try to fetch the product, return an error if it doesn't exist
    try:
        product = store_models.Product.objects.get(status="published", id=id)
    except store_models.Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

    # Check if quantity that user is adding exceed item stock qty
    if int(qty) > product.stock:
        return JsonResponse({"error": "Qty exceed current stock amount"}, status=404)

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
        cart_item.price = product.effective_price
        cart_item.sub_total = Decimal(product.effective_price) * Decimal(cart_item.qty)
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
        cart.price = product.effective_price
        cart.model = model
        cart.size = size
        cart.sub_total = Decimal(product.effective_price) * Decimal(qty)
        cart.user = request.user if request.user.is_authenticated else None
        cart.cart_id = cart_id
        cart.save()
        cart_item = cart
        message = "Продуктът е добавен в количката"

    # Count the total number of items in the cart
    total_cart_items = store_models.Cart.objects.filter(cart_id=cart_id)
    cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
        sub_total=models.Sum("sub_total")
    )["sub_total"]

    # Return the response with the cart update message and total cart items
    return JsonResponse(
        {
            "message": message,
            "total_cart_items": total_cart_items.count(),
            "cart_sub_total": "{:,.2f}".format(cart_sub_total),
            "item_sub_total": "{:,.2f}".format(cart_item.sub_total),
            "current_qty": cart_item.qty,
        }
    )


def cart(request):
    if "cart_id" in request.session:
        cart_id = request.session["cart_id"]
    else:
        cart_id = None

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

    # Count the total number of items in the cart
    total_cart_items = store_models.Cart.objects.filter(cart_id=cart_id)
    cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
        sub_total=models.Sum("sub_total")
    )["sub_total"]

    return JsonResponse(
        {
            "message": "Продуктът е изтрит",
            "total_cart_items": total_cart_items.count(),
            "cart_sub_total": (
                "{:,.2f}".format(cart_sub_total) if cart_sub_total else 0.00
            ),
        }
    )


def create_order(request):
    if request.method == "POST":
        cart_id = request.session.get("cart_id")
        items = store_models.Cart.objects.filter(cart_id=cart_id)
        cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
            sub_total=models.Sum("sub_total")
        )["sub_total"]

        shipping = 0.00
        order = store_models.Order()
        order.sub_total = cart_sub_total
        order.customer = request.user if request.user.is_authenticated else None
        order.shipping = shipping
        order.total = (order.sub_total or 0) + (order.shipping or 0)
        order.save()

        for i in items:
            store_models.OrderItem.objects.create(
                order=order,
                product=i.product,
                qty=i.qty,
                model=i.model,
                size=i.size,
                price=i.price,
                sub_total=i.sub_total,
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
        ),
    )

    print("checkkout session", checkout_session)
    return JsonResponse({"sessionId": checkout_session.id})


def stripe_payment_verify(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)
    session_id = request.GET.get("session_id")
    session = stripe.checkout.Session.retrieve(session_id)

    if session.payment_status == "paid":
        if order.payment_status == "processing":
            order.payment_status = "paid"
            order.payment_method = "card"
            # Mark order as received upon successful payment
            order.order_status = "received"
            _send_shipment(order)
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
            customer_models.Notifications.objects.create(
                type="New Order", user=request.user
            )
            clear_cart_items(request)
            return redirect(reverse("store:payment_status", args=[order.order_id]) + "?payment_status=paid")
    return redirect(reverse("store:payment_status", args=[order.order_id]) + "?payment_status=failed")


def payment_status(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)
    payment_status = request.GET.get("payment_status")

    context = {"order": order, "payment_status": payment_status}
    return render(request, "store/payment_status.html", context)


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
        products = products.filter(category__id__in=all_category_ids)

    # Apply rating filtering
    if rating:
        products = products.filter(reviews__rating__in=rating).distinct()

    # Apply size filtering
    if sizes:
        products = products.filter(variant__variant_items__content__in=sizes).distinct()

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
            effective_price=models.Case(
                models.When(
                    models.Q(sale_price__isnull=False) & models.Q(sale_price__lt=models.F("price")),
                    then=models.F("sale_price"),
                ),
                default=models.F("price"),
                output_field=models.DecimalField(max_digits=12, decimal_places=2),
            )
        )
        if price_order == "lowest":
            products = products.order_by("-effective_price")
        else:
            products = products.order_by("effective_price")

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