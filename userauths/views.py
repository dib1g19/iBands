from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth import logout
from django.urls import reverse

from userauths import models as userauths_models
from userauths import forms as userauths_forms
from store import models as store_models
from customer import models as customer_models
from decimal import Decimal
from store.emails import send_welcome_email


def register_view(request):
    if request.user.is_authenticated:
        messages.warning(request, f"Вече сте влезли в профила си")
        return redirect("/")

    form = userauths_forms.UserRegisterForm(request.POST or None)

    if form.is_valid():
        # Preserve anonymous session cart before login (session rotates on login)
        preserved_cart_id = request.session.get("cart_id")
        try:
            user = form.save()
        except Exception as e:
            # Surface any model/DB errors as non-field errors
            form.add_error(None, "Възникна грешка при създаването на профила. Моля, опитайте отново.")
            return render(request, "userauths/sign-up.html", {"form": form, "breadcrumbs": [
                {"label": "Начална Страница", "url": reverse("store:index")},
                {"label": "Създай акаунт", "url": ""},
            ]})

        full_name = form.cleaned_data.get("full_name")
        email = form.cleaned_data.get("email")
        mobile = form.cleaned_data.get("mobile")
        password = form.cleaned_data.get("password1")

        user = authenticate(request, email=email, password=password)
        if not user:
            form.add_error(None, "Профилът беше създаден, но възникна проблем при вход. Моля, влезте ръчно.")
        else:
            login(request, user)

        # Restore cart_id and attach anonymous cart items to the new user
        if preserved_cart_id and user:
            request.session["cart_id"] = preserved_cart_id
            try:
                store_models.Cart.objects.filter(cart_id=preserved_cart_id).update(user=user)
            except Exception:
                pass

        messages.success(request, f"Профилът беше създаден успешно.")
        # Ensure a profile exists; idempotent across retries/races
        profile, _ = userauths_models.Profile.objects.get_or_create(
            user=user,
            defaults={"full_name": full_name, "mobile": mobile},
        )

        # Send welcome email (fail silently on errors)
        try:
            if user:
                send_welcome_email(user=user)
        except Exception:
            pass

        # Safe redirect handling (avoid undefined/external values)
        next_url = request.GET.get("next")
        if not user:
            # Stay on the form when auto-login failed
            return render(request, "userauths/sign-up.html", {"form": form, "breadcrumbs": [
                {"label": "Начална Страница", "url": reverse("store:index")},
                {"label": "Създай акаунт", "url": ""},
            ]})
        if next_url in ("/undefined/", "undefined", None):
            return redirect("store:index")
        if not isinstance(next_url, str) or not next_url.startswith("/"):
            return redirect("store:index")
        return redirect(next_url)

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Създай акаунт", "url": ""},
    ]

    context = {
        "form": form,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "userauths/sign-up.html", context)


def login_view(request):
    if request.user.is_authenticated:
        messages.warning(request, "Вече сте в профила си")
        return redirect("store:index")

    if request.method == "POST":
        form = userauths_forms.LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower().strip()
            password = form.cleaned_data["password"]
            # Captcha temporarily disabled; proceed directly
            try:
                    user_authenticate = authenticate(
                        request, email=email, password=password
                    )

                    if user_authenticate is not None:
                        login(request, user_authenticate)
                        messages.success(request, "Успешно влязохте в профила си.")
                        # Merge any previous carts linked to this user into current session cart_id
                        try:
                            current_cart_id = request.session.get("cart_id")
                            if not current_cart_id:
                                # Generate a simple 10-digit numeric cart id similar to frontend
                                import random
                                current_cart_id = "".join(str(random.randint(0, 9)) for _ in range(10))
                                request.session["cart_id"] = current_cart_id

                            # Attach any existing session cart lines to the user
                            store_models.Cart.objects.filter(cart_id=current_cart_id).update(user=user_authenticate)

                            # Find other carts for this user and merge into current_cart_id
                            other_items = store_models.Cart.objects.filter(user=user_authenticate).exclude(cart_id=current_cart_id)
                            for item in other_items:
                                # Try to find an existing line in the target cart with same product/model/size
                                target = store_models.Cart.objects.filter(
                                    cart_id=current_cart_id,
                                    product=item.product,
                                    model=item.model,
                                    size=item.size,
                                ).first()
                                # Resolve line unit price (prefer SKU when size/model selected)
                                try:
                                    sku_qs = store_models.ProductItem.objects.filter(product=item.product)
                                    if item.size:
                                        sku_qs = sku_qs.filter(size__name=item.size)
                                    else:
                                        sku_qs = sku_qs.filter(size__isnull=True)
                                    if item.model:
                                        sku_qs = sku_qs.filter(device_models__name=item.model)
                                    sku = sku_qs.first()
                                    unit_price = getattr(sku, "effective_price", None) if sku else item.product.effective_price
                                except Exception:
                                    unit_price = item.product.effective_price

                                if target:
                                    # Merge quantities
                                    target.qty = int(target.qty or 0) + int(item.qty or 0)
                                    target.price = unit_price
                                    target.sub_total = Decimal(str(unit_price or 0)) * Decimal(str(target.qty or 0))
                                    target.user = user_authenticate
                                    target.cart_id = current_cart_id
                                    target.save()
                                    item.delete()
                                else:
                                    # Move this line into current cart
                                    item.cart_id = current_cart_id
                                    item.user = user_authenticate
                                    item.price = unit_price
                                    item.sub_total = Decimal(str(unit_price or 0)) * Decimal(str(item.qty or 0))
                                    item.save()
                            # Merge wishlist: attach any anonymous session wishlist to the authenticated user
                            try:
                                # Attach session wishlist rows to this user
                                customer_models.Wishlist.objects.filter(wishlist_id=current_cart_id).update(user=user_authenticate)
                                # Deduplicate same product for this user (keep a single row per product)
                                user_wishlist = (
                                    customer_models.Wishlist.objects
                                    .filter(user=user_authenticate)
                                    .order_by("product_id", "id")
                                )
                                seen = set()
                                for wl in user_wishlist:
                                    if wl.product_id in seen:
                                        wl.delete()
                                    else:
                                        seen.add(wl.product_id)
                            except Exception:
                                pass
                        except Exception:
                            # Don't block login on cart merge issues
                            pass
                        next_url = request.GET.get("next", "store:index")

                        print("next_url ========", next_url)
                        if next_url == "/undefined/":
                            return redirect("store:index")

                        if next_url == "undefined":
                            return redirect("store:index")

                        if next_url is None or not next_url.startswith("/"):
                            return redirect("store:index")

                        return redirect(next_url)
                    else:
                        messages.error(request, "Грешен имейл или парола")
            except userauths_models.User.DoesNotExist:
                messages.error(request, "Потребителят не съществува")
    else:
        form = userauths_forms.LoginForm()

    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Вход", "url": ""},
    ]

    context = {
        "form": form,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "userauths/sign-in.html", context)


def logout_view(request):
    if "cart_id" in request.session:
        cart_id = request.session["cart_id"]
    else:
        cart_id = None
    logout(request)
    request.session["cart_id"] = cart_id
    messages.success(request, "Успешно излязохте от профила си.")
    return redirect("userauths:sign-in")


def handler404(request, exception, *args, **kwargs):
    context = {}
    response = render(request, "userauths/404.html", context)
    response.status_code = 404
    return response


def handler500(request, *args, **kwargs):
    context = {}
    response = render(request, "userauths/500.html", context)
    response.status_code = 500
    return response
