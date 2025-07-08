from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from decimal import Decimal
from .models import Category, Product
import requests
import stripe
import razorpay
from plugin.paginate_queryset import paginate_queryset
from store import models as store_models
from customer import models as customer_models
from userauths import models as userauths_models
from plugin.exchange_rate import (
    convert_usd_to_inr,
    convert_usd_to_kobo,
    convert_usd_to_ngn,
    get_usd_to_ngn_rate,
)
from customer.utils import get_user_wishlist_products
from store.emails import send_order_notification_email
from django.db.models import Q


def get_category_ancestors(category):
    ancestors = []
    while category.parent:
        ancestors.append(category.parent)
        category = category.parent
    return ancestors[::-1]


stripe.api_key = settings.STRIPE_SECRET_KEY
razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


def clear_cart_items(request):
    try:
        cart_id = request.session["cart_id"]
        store_models.Cart.objects.filter(cart_id=cart_id).delete()
    except:
        pass
    return


def index(request):
    products_list = store_models.Product.objects.filter(
        status="published", featured=True
    )
    products = paginate_queryset(request, products_list, 20)

    categories = store_models.Category.objects.filter(parent__isnull=True)
    popular_categories = store_models.Category.objects.filter(is_popular=True)

    context = {
        "products": products,
        "categories": categories,
        "popular_categories": popular_categories,
        "user_wishlist_products": get_user_wishlist_products(request),
    }
    return render(request, "store/index.html", context)


def shop(request):
    products_list = store_models.Product.objects.filter(status="published")
    products = paginate_queryset(request, products_list, 20)

    categories = (
        store_models.Category.objects.filter(parent__isnull=True)
        .prefetch_related("subcategories__subcategories")
        .order_by("id")
    )

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
        "item_display": item_display,
        "ratings": ratings,
        "prices": prices,
        "user_wishlist_products": get_user_wishlist_products(request),
        "breadcrumbs": breadcrumbs,
    }
    context["is_shop"] = True
    return render(request, "store/shop.html", context)


def category(request, category_path):
    slugs = category_path.strip("/").split("/")
    category = None
    parent = None
    for slug in slugs:
        category = get_object_or_404(Category, slug=slug, parent=parent)
        parent = category

    child_categories_qs = Category.objects.filter(parent=category)
    child_categories = list(child_categories_qs)
    all_sub = category
    all_sub.is_all = True
    subcategories_with_all = [all_sub] + child_categories

    products_list = Product.objects.filter(status="published", category=category)

    query = request.GET.get("q")
    if query:
        products_list = products_list.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__title__icontains=query)
        )

    products = paginate_queryset(request, products_list, 12)

    # Build breadcrumbs (all ancestors)
    ancestors = []
    cat = category
    while cat.parent:
        ancestors.append(cat.parent)
        cat = cat.parent
    ancestors = ancestors[::-1]
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


def get_descendant_category_ids(category):
    """Recursively find all descendant category ids for a given category."""
    ids = []
    children = store_models.Category.objects.filter(parent=category)
    for child in children:
        ids.append(child.id)
        ids += get_descendant_category_ids(child)
    return ids


def category_all_sub_root(request, slug):
    category = get_object_or_404(store_models.Category, slug=slug, parent=None)
    descendant_ids = get_descendant_category_ids(category)
    products_list = store_models.Product.objects.filter(
        status="published", category_id__in=descendant_ids
    )
    query = request.GET.get("q")
    if query:
        products_list = products_list.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__title__icontains=query)
        )
    products = paginate_queryset(request, products_list, 12)

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": category.title, "url": category.get_absolute_url},
        {"label": f"Всички {category.title}", "url": ""},
    ]
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


def category_all_sub(request, parent_slug, slug):
    parent = get_object_or_404(store_models.Category, slug=parent_slug)
    category = get_object_or_404(store_models.Category, slug=slug, parent=parent)
    descendant_ids = get_descendant_category_ids(category)
    products_list = store_models.Product.objects.filter(
        status="published", category_id__in=descendant_ids
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
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
    ]
    for ancestor in ancestors:
        breadcrumbs.append({"label": ancestor.title, "url": ancestor.get_absolute_url})
    breadcrumbs.append({"label": category.title, "url": category.get_absolute_url})
    breadcrumbs.append(
        {
            "label": f"Всички {category.title}",
            "url": "",
        }
    )
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

    # Find the product within this category
    product = get_object_or_404(
        Product, slug=product_slug, category=category, status="published"
    )

    # Prepare related products (from the same category, exclude self)
    related_products_list = Product.objects.filter(category=category).exclude(
        id=product.id
    )
    related_products = paginate_queryset(request, related_products_list, 12)

    # Stock/variant details
    has_length_variant = product.variants.filter(variant_type="length").exists()
    product_stock_range = range(1, product.stock + 1)

    # Breadcrumbs (use full path)
    ancestors = []
    cat = category
    while cat.parent:
        ancestors.append(cat.parent)
        cat = cat.parent
    ancestors = ancestors[::-1]

    breadcrumbs = [{"label": "Начална Страница", "url": reverse("store:index")}]
    for ancestor in ancestors:
        breadcrumbs.append({"label": ancestor.title, "url": ancestor.get_absolute_url})
    breadcrumbs.append({"label": category.title, "url": category.get_absolute_url})
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
        cart_item.price = cart_item.product.price
        cart_item.sub_total = Decimal(cart_item.product.price) * Decimal(cart_item.qty)
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
        cart_item.price = product.price
        cart_item.sub_total = Decimal(product.price) * Decimal(cart_item.qty)
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
        cart.price = product.price
        cart.model = model
        cart.size = size
        cart.sub_total = Decimal(product.price) * Decimal(qty)
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

    items = store_models.Cart.objects.filter(cart_id=cart_id)
    cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
        sub_total=models.Sum("sub_total")
    )["sub_total"]

    try:
        addresses = customer_models.Address.objects.filter(user=request.user)
    except:
        addresses = None

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
        "addresses": addresses,
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
        address_id = request.POST.get("address")

        # --- Handle guest address or direct form ---
        address = None
        if address_id and address_id.isdigit():
            # Existing address (logged in user)
            address = customer_models.Address.objects.filter(
                user=request.user, id=address_id
            ).first()
        else:
            # Guest or inline new address
            guest_address_id = request.session.get("guest_address_id")
            if guest_address_id:
                address = customer_models.Address.objects.filter(
                    id=guest_address_id
                ).first()
            else:
                # Fallback: create a new address from POST (if data present)
                address = customer_models.Address.objects.create(
                    full_name=request.POST.get("full_name"),
                    mobile=request.POST.get("mobile"),
                    email=request.POST.get("email"),
                    delivery_method=request.POST.get("delivery_method"),
                    city=request.POST.get("city"),
                    address=request.POST.get("address"),
                )

        if not address:
            messages.warning(request, "Please provide or select an address to continue")
            return redirect("store:cart")

        if "cart_id" in request.session:
            cart_id = request.session["cart_id"]
        else:
            cart_id = None

        items = store_models.Cart.objects.filter(cart_id=cart_id)
        cart_sub_total = store_models.Cart.objects.filter(cart_id=cart_id).aggregate(
            sub_total=models.Sum("sub_total")
        )["sub_total"]

        order = store_models.Order()
        order.sub_total = cart_sub_total
        order.customer = request.user if request.user.is_authenticated else None
        order.address = address

        shipping_fee = 0
        if address and address.delivery_method:
            if address.delivery_method in [
                "econt",
                "econt_box",
                "speedy",
                "speedy_box",
            ]:
                if cart_sub_total >= 75:
                    shipping_fee = 0
                elif address.delivery_method == "econt":
                    shipping_fee = 6.5
                elif address.delivery_method == "econt_box":
                    shipping_fee = 6
                elif address.delivery_method == "speedy":
                    shipping_fee = 6
                elif address.delivery_method == "speedy_box":
                    shipping_fee = 4
            elif address.delivery_method == "personal":
                shipping_fee = 9
        from decimal import Decimal

        order.shipping = Decimal(str(shipping_fee))
        order.total = order.sub_total + order.shipping
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
        order_items = store_models.OrderItem.objects.filter(order=order)
    except store_models.Order.DoesNotExist:
        messages.error(request, "Order not found")
        return redirect("store:cart")

    if request.method == "POST":
        coupon_code = request.POST.get("coupon_code")

        if not coupon_code:
            messages.error(request, "No coupon entered")
            return redirect("store:checkout", order.order_id)

        try:
            coupon = store_models.Coupon.objects.get(code=coupon_code)
        except store_models.Coupon.DoesNotExist:
            messages.error(request, "Coupon does not exist")
            return redirect("store:checkout", order.order_id)

        if coupon in order.coupons.all():
            messages.warning(request, "Coupon already activated")
            return redirect("store:checkout", order.order_id)
        else:
            # Coupon now applies globally to all items
            total_discount = 0
            for item in order_items:
                if coupon not in item.coupon.all():
                    item_discount = (
                        item.sub_total * coupon.discount / 100
                    )  # Discount for this item
                    total_discount += item_discount
                    item.coupon.add(coupon)
                    item.saved += item_discount
                    item.save()

            # Apply total discount to the order after processing all items
            if total_discount > 0:
                order.coupons.add(coupon)
                order.total -= total_discount
                order.saved += total_discount
                order.save()

        messages.success(request, "Coupon Activated")
        return redirect("store:checkout", order.order_id)


def checkout(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)

    amount_in_inr = convert_usd_to_inr(order.total)
    amount_in_kobo = convert_usd_to_kobo(order.total)
    amount_in_ngn = convert_usd_to_ngn(order.total)

    try:
        razorpay_order = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        ).order.create(
            {"amount": int(amount_in_inr), "currency": "INR", "payment_capture": "1"}
        )
    except:
        razorpay_order = None

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Магазин", "url": reverse("store:shop")},
        {"label": "Количка", "url": reverse("store:cart")},
        {"label": "Поръчка", "url": ""},
    ]

    context = {
        "order": order,
        "amount_in_inr": amount_in_inr,
        "amount_in_kobo": amount_in_kobo,
        "amount_in_ngn": round(amount_in_ngn, 2),
        "razorpay_order_id": razorpay_order["id"] if razorpay_order else None,
        "stripe_public_key": settings.STRIPE_PUBLIC_KEY,
        "paypal_client_id": settings.PAYPAL_CLIENT_ID,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "paystack_public_key": settings.PAYSTACK_PUBLIC_KEY,
        "flutterwave_public_key": settings.FLUTTERWAVE_PUBLIC_KEY,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "store/checkout.html", context)


def cod_payment(request, order_id):
    if request.method == "POST":
        order = store_models.Order.objects.get(order_id=order_id)
        order.payment_method = "cash_on_delivery"
        order.payment_status = "cash_on_delivery"
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
                    "product_data": {"name": order.address.full_name},
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
            return redirect(f"/payment_status/{order.order_id}/?payment_status=paid")
    return redirect(f"/payment_status/{order.order_id}/?payment_status=failed")


def get_paypal_access_token():
    token_url = "https://api.sandbox.paypal.com/v1/oauth2/token"
    data = {"grant_type": "client_credentials"}
    auth = (settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET_ID)
    response = requests.post(token_url, data=data, auth=auth)

    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(
            f"Failed to get access token from PayPal. Status code: {response.status_code}"
        )


def paypal_payment_verify(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)

    transaction_id = request.GET.get("transaction_id")
    paypal_api_url = (
        f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{transaction_id}"
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_paypal_access_token()}",
    }
    response = requests.get(paypal_api_url, headers=headers)

    if response.status_code == 200:
        paypal_order_data = response.json()
        paypal_payment_status = paypal_order_data["status"]
        if paypal_payment_status == "COMPLETED":
            if order.payment_status == "Processing":
                order.payment_status = "Paid"
                payment_method = request.GET.get("payment_method")
                order.payment_method = payment_method
                order.save()
                clear_cart_items(request)
                return redirect(
                    f"/payment_status/{order.order_id}/?payment_status=paid"
                )
    else:
        return redirect(f"/payment_status/{order.order_id}/?payment_status=failed")


@csrf_exempt
def razorpay_payment_verify(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)
    payment_method = request.GET.get("payment_method")

    if request.method == "POST":
        data = request.POST

        # Extract payment data
        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")

        print("razorpay_order_id: ====", razorpay_order_id)
        print("razorpay_payment_id: ====", razorpay_payment_id)
        print("razorpay_signature: ====", razorpay_signature)

        params_dict = {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        }

        # Verify the payment signature
        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )

        razorpay_client.utility.verify_payment_signature(params_dict)

        # Success response
        if order.payment_status == "Processing":
            order.payment_status = "Paid"
            order.payment_method = payment_method
            order.save()
            clear_cart_items(request)
            customer_models.Notifications.objects.create(
                type="New Order", user=request.user
            )

            return redirect(f"/payment_status/{order.order_id}/?payment_status=paid")

    return redirect(f"/payment_status/{order.order_id}/?payment_status=failed")


def paystack_payment_verify(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)
    reference = request.GET.get("reference", "")

    if reference:
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_PRIVATE_KEY}",
            "Content-Type": "application/json",
        }
        # Verify the transaction
        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}", headers=headers
        )
        response_data = response.json()

        if response_data["status"]:
            if response_data["data"]["status"] == "success":
                if order.payment_status == "Processing":
                    order.payment_status = "Paid"
                    payment_method = request.GET.get("payment_method")
                    order.payment_method = payment_method
                    order.save()
                    clear_cart_items(request)
                    return redirect(
                        f"/payment_status/{order.order_id}/?payment_status=paid"
                    )
                else:
                    return redirect(
                        f"/payment_status/{order.order_id}/?payment_status=failed"
                    )
            else:
                # Payment failed
                return redirect(
                    f"/payment_status/{order.order_id}/?payment_status=failed"
                )
        else:
            return redirect(f"/payment_status/{order.order_id}/?payment_status=failed")
    else:
        return redirect(f"/payment_status/{order.order_id}/?payment_status=failed")


def flutterwave_payment_callback(request, order_id):
    order = store_models.Order.objects.get(order_id=order_id)

    payment_id = request.GET.get("tx_ref")
    status = request.GET.get("status")

    headers = {"Authorization": f"Bearer {settings.FLUTTERWAVE_PRIVATE_KEY}"}
    response = requests.get(
        f"https://api.flutterwave.com/v3/charges/verify_by_id/{payment_id}",
        headers=headers,
    )

    if response.status_code == 200:
        if order.payment_status == "Processing":
            order.payment_status = "Paid"
            payment_method = request.GET.get("payment_method")
            order.payment_method = payment_method
            order.save()
            clear_cart_items(request)
            return redirect(f"/payment_status/{order.order_id}/?payment_status=paid")
        else:
            return redirect(f"/payment_status/{order.order_id}/?payment_status=failed")
    else:
        return redirect(f"/payment_status/{order.order_id}/?payment_status=failed")


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
        all_category_ids = []
        for cid in categories:
            try:
                cid_int = int(cid)
                all_category_ids.append(cid_int)
                category = store_models.Category.objects.get(id=cid_int)
                descendant_ids = get_descendant_category_ids(category)
                all_category_ids.extend(descendant_ids)
            except:
                continue
        products = products.filter(category__id__in=all_category_ids)

    # Apply rating filtering
    if rating:
        products = products.filter(reviews__rating__in=rating).distinct()

    # Apply size filtering
    if sizes:
        products = products.filter(variant__variant_items__content__in=sizes).distinct()

    # Apply color filtering
    if colors:
        products = products.filter(
            variant__variant_items__content__in=colors
        ).distinct()

    # Apply price ordering
    if price_order == "lowest":
        products = products.order_by("-price")
    elif price_order == "highest":
        products = products.order_by("price")

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

    html = render_to_string(
        "store/_product_list.html",
        {
            "products": products_page,
            "user_wishlist_products": get_user_wishlist_products(request),
        },
    )
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
