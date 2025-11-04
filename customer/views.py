from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.contrib import messages
from django.db import models
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password
from django.urls import reverse
from store.utils import paginate_queryset
from store import models as store_models
from customer import models as customer_models


@login_required
def dashboard(request):
    # Prefetch order items and select_related product, category, and category parents
    orders = (
        store_models.Order.objects
        .filter(customer=request.user)
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
    )
    total_spent = store_models.Order.objects.filter(customer=request.user).aggregate(
        total=models.Sum("total")
    )["total"]
    notis = customer_models.Notifications.objects.filter(user=request.user, seen=False)

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Табло", "url": ""},
    ]

    context = {
        "orders": orders,
        "total_spent": total_spent,
        "notis": notis,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "customer/dashboard.html", context)


@login_required
def order_detail(request, order_id):
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
        .get(customer=request.user, order_id=order_id)
    )

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Поръчки", "url": reverse("customer:dashboard")},
        {"label": f"Поръчка #{order.order_id}", "url": ""},
    ]
    context = {
        "order": order,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "customer/order_detail.html", context)


def wishlist(request):
    # Show wishlist for both authenticated and anonymous users
    if request.user.is_authenticated:
        wishlist_qs = customer_models.Wishlist.objects.filter(user=request.user)
    else:
        # Use session cart_id as anonymous wishlist identifier; do not create if not present
        cart_id = request.session.get("cart_id")
        wishlist_qs = customer_models.Wishlist.objects.filter(wishlist_id=cart_id)

    wishlist_list = wishlist_qs.select_related(
        "product__category", "product__category__parent", "product__category__parent__parent"
    )
    wishlist = paginate_queryset(request, wishlist_list, 6)

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Любими", "url": ""},
    ]
    context = {
        "wishlist": wishlist,
        "wishlist_list": wishlist_list,
        "breadcrumbs": breadcrumbs,
        "products": wishlist,
    }

    return render(request, "customer/wishlist.html", context)


def toggle_wishlist(request, id):
    # Allow guests to toggle wishlist by binding to session cart_id
    product = store_models.Product.objects.get(id=id)

    # Ensure we have a session identifier similar to cart
    cart_id = request.session.get("cart_id")
    if not cart_id:
        import random
        cart_id = "".join(str(random.randint(0, 9)) for _ in range(10))
        request.session["cart_id"] = cart_id

    if request.user.is_authenticated:
        wishlist_item, created = customer_models.Wishlist.objects.get_or_create(
            product=product, user=request.user
        )
        if not created:
            wishlist_item.delete()
            total_wishlist_items = customer_models.Wishlist.objects.filter(
                user=request.user
            ).count()
            return JsonResponse(
                {
                    "status": "removed",
                    "message": "Продуктът е премахнат от любими",
                    "total_wishlist_items": total_wishlist_items,
                }
            )
        else:
            # Optionally mark current session id for consistency (useful for header count if session is used elsewhere)
            wishlist_item.wishlist_id = cart_id
            wishlist_item.save(update_fields=["wishlist_id"])
            total_wishlist_items = customer_models.Wishlist.objects.filter(
                user=request.user
            ).count()
            return JsonResponse(
                {
                    "status": "added",
                    "message": "Продуктът е добавен в любими",
                    "total_wishlist_items": total_wishlist_items,
                }
            )
    else:
        wishlist_item, created = customer_models.Wishlist.objects.get_or_create(
            product=product, wishlist_id=cart_id
        )
        if not created:
            wishlist_item.delete()
            total_wishlist_items = customer_models.Wishlist.objects.filter(
                wishlist_id=cart_id
            ).count()
            return JsonResponse(
                {
                    "status": "removed",
                    "message": "Продуктът е премахнат от любими",
                    "total_wishlist_items": total_wishlist_items,
                }
            )
        else:
            total_wishlist_items = customer_models.Wishlist.objects.filter(
                wishlist_id=cart_id
            ).count()
            return JsonResponse(
                {
                    "status": "added",
                    "message": "Продуктът е добавен в любими",
                    "total_wishlist_items": total_wishlist_items,
                }
            )


def remove_from_wishlist(request, id):
    # Remove wishlist item for both authenticated and anonymous users
    try:
        if request.user.is_authenticated:
            wishlist = customer_models.Wishlist.objects.get(user=request.user, id=id)
        else:
            cart_id = request.session.get("cart_id")
            wishlist = customer_models.Wishlist.objects.get(wishlist_id=cart_id, id=id)
        wishlist.delete()
        messages.success(request, "Продуктът е премахнат от любими.")
    except customer_models.Wishlist.DoesNotExist:
        messages.warning(request, "Артикулът не беше намерен в любими.")
    return redirect("customer:wishlist")


@login_required
def notis(request):
    notis_list = customer_models.Notifications.objects.filter(
        user=request.user, seen=False
    )
    notis = paginate_queryset(request, notis_list, 10)

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Известия", "url": ""},
    ]
    context = {
        "notis": notis,
        "notis_list": notis_list,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "customer/notis.html", context)


@login_required
def mark_noti_seen(request, id):
    noti = customer_models.Notifications.objects.get(user=request.user, id=id)
    noti.seen = True
    noti.save()

    messages.success(request, "Нотификацията е отбелязана като прочетена.")
    return redirect("customer:notis")


@login_required
def addresses(request):
    addresses = customer_models.Address.objects.filter(user=request.user).order_by('id')

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Адреси", "url": ""},
    ]
    context = {
        "addresses": addresses,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "customer/addresses.html", context)


@login_required
def address_detail(request, id):
    address = customer_models.Address.objects.get(user=request.user, id=id)

    if request.method == "POST":
        name = request.POST.get("name")
        face = request.POST.get("face")
        phone = request.POST.get("phone")
        email = request.POST.get("email")
        delivery_method = request.POST.get("delivery_method")
        city = request.POST.get("city")
        address_location = request.POST.get("address")
        office_name = request.POST.get("office_name")

        address.name = name
        address.face = face
        address.phone = phone
        address.email = email
        address.delivery_method = delivery_method
        address.city = city

        if delivery_method in ["econt_office", "speedy_office"]:
            address.address = ""
            address.office_name = office_name
        else:
            address.address = address_location
            address.office_name = ""

        address.save()

        messages.success(request, "Адресът е обновен успешно!")
        return redirect("customer:addresses")

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Адреси", "url": reverse("customer:addresses")},
        {"label": "Актуализирай Адрес", "url": ""},
    ]
    context = {
        "address": address,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "customer/address_detail.html", context)


@login_required
def address_create(request):
    if request.method == "POST":
        name = request.POST.get("name")
        face = request.POST.get("face")
        phone = request.POST.get("phone")
        email = request.POST.get("email")
        delivery_method = request.POST.get("delivery_method")
        city = request.POST.get("city")

        # Get both address fields, only save one depending on delivery method
        address = request.POST.get("address")
        office_name = request.POST.get("office_name")

        if delivery_method in ["econt_office", "speedy_office"]:
            address_to_save = ""
            office_name_to_save = office_name
        else:
            address_to_save = address
            office_name_to_save = ""

        customer_models.Address.objects.create(
            user=request.user,
            name=name,
            face=face,
            phone=phone,
            email=email,
            delivery_method=delivery_method,
            city=city,
            address=address_to_save,
            office_name=office_name_to_save,
        )

        messages.success(request, "Адресът е създаден успешно!")
        return redirect("customer:addresses")

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Адреси", "url": reverse("customer:addresses")},
        {"label": "Създай Адрес", "url": ""},
    ]
    context = {
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "customer/address_create.html", context)


@login_required
@require_POST
def set_main_address(request, id):
    # Unset all addresses for the user
    customer_models.Address.objects.filter(user=request.user, is_main=True).update(is_main=False)
    # Set this address as main
    address = customer_models.Address.objects.get(user=request.user, id=id)
    address.is_main = True
    address.save()
    messages.success(request, "Основният адрес е обновен успешно!")
    return redirect("customer:addresses")


def delete_address(request, id):
    address = customer_models.Address.objects.get(user=request.user, id=id)
    address.delete()
    messages.success(request, "Адресът е изтрит.")
    return redirect("customer:addresses")


@login_required
def profile(request):
    profile = request.user.profile

    if request.method == "POST":
        image = request.FILES.get("image")
        full_name = request.POST.get("full_name")
        mobile = request.POST.get("mobile")

        if image != None:
            profile.image = image

        profile.full_name = full_name
        profile.mobile = mobile

        request.user.save()
        profile.save()

        messages.success(request, "Профилът е обновен успешно.")
        return redirect("customer:profile")

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Профил", "url": ""},
    ]
    context = {
        "profile": profile,
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "customer/profile.html", context)


@login_required
def change_password(request):
    if request.method == "POST":
        old_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")
        confirm_new_password = request.POST.get("confirm_new_password")

        if confirm_new_password != new_password:
            messages.error(request, "Паролите не съвпадат.")
            return redirect("customer:change_password")

        if check_password(old_password, request.user.password):
            request.user.set_password(new_password)
            request.user.save()
            messages.success(request, "Паролата беше успешно променена.")
            return redirect("customer:profile")
        else:
            messages.error(request, "Старата парола е неправилна.")
            return redirect("customer:change_password")

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Профил", "url": reverse("customer:profile")},
        {"label": "Смяна на парола", "url": ""},
    ]
    context = {
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "customer/change_password.html", context)
