from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.contrib import messages
from django.db import models
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password
from django.urls import reverse
from store.prizes import customer_rewards, order_ladder, sync_order_milestones
from store.utils import paginate_queryset
from store import models as store_models
from customer import models as customer_models
from customer.utils import get_order_for_customer


def _account_orders():
    coupon_codes = (
        store_models.Coupon.objects.filter(order=models.OuterRef("pk"))
        .order_by("id")
        .values("code")
    )
    return store_models.Order.objects.annotate(
        promo_code=models.Case(
            models.When(saved__gt=0, then=models.Subquery(coupon_codes[:1])),
        ),
    ).prefetch_related(
        models.Prefetch(
            "order_items",
            queryset=store_models.OrderItem.objects.select_related(
                "product",
                "product__category",
                "product__category__parent",
                "product__category__parent__parent",
            ),
        ),
    )


@login_required
def dashboard(request):
    orders = _account_orders().filter(customer=request.user)
    sync_order_milestones(request.user)
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Табло", "url": ""},
    ]

    context = {
        "orders": orders,
        "ladder": order_ladder(request.user),
        "rewards": customer_rewards(request.user),
        "breadcrumbs": breadcrumbs,
    }

    return render(request, "customer/dashboard.html", context)


@login_required
def order_detail(request, order_id):
    order_qs = _account_orders()
    if request.user.is_staff:
        order = order_qs.filter(order_id=order_id).select_related("address").first()
    else:
        order = get_order_for_customer(request.user, order_id, queryset=order_qs)
    if not order:
        messages.error(request, "Поръчката не беше намерена в този профил.")
        return redirect("customer:dashboard")

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

    wishlist_list = wishlist_qs.filter(
        product__status="published"
    ).select_related(
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
                user=request.user, product__status="published"
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
                user=request.user, product__status="published"
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
                wishlist_id=cart_id, product__status="published"
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
                wishlist_id=cart_id, product__status="published"
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
def addresses(request):
    addresses = customer_models.Address.objects.filter(user=request.user, saved=True).order_by("-is_main", "-id")

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
    return redirect("customer:addresses")


@login_required
def address_create(request):
    return redirect("customer:addresses")


@login_required
@require_POST
def set_main_address(request, id):
    customer_models.Address.objects.filter(user=request.user, is_main=True).update(is_main=False)
    address = customer_models.Address.objects.get(user=request.user, id=id, saved=True)
    address.is_main = True
    address.save()
    messages.success(request, "Основният адрес е обновен успешно!")
    return redirect("customer:addresses")


def delete_address(request, id):
    address = customer_models.Address.objects.get(user=request.user, id=id, saved=True)
    if store_models.Order.objects.filter(address=address).exists():
        address.saved = False
        address.is_main = False
        address.save(update_fields=["saved", "is_main"])
    else:
        address.delete()
    messages.success(request, "Адресът е изтрит.")
    return redirect("customer:addresses")


@login_required
def profile(request):
    user = request.user

    if request.method == "POST":
        image = request.FILES.get("image")
        full_name = request.POST.get("full_name")
        mobile = request.POST.get("mobile")

        if image != None:
            user.image = image

        user.full_name = full_name
        user.mobile = mobile
        user.save()

        messages.success(request, "Профилът е обновен успешно.")
        return redirect("customer:profile")

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Профил", "url": ""},
    ]
    context = {
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
