from customer import models as customer_models


def get_user_wishlist_products(request):
    try:
        if request.user.is_authenticated:
            return set(
                customer_models.Wishlist.objects.filter(user=request.user).values_list(
                    "product_id", flat=True
                )
            )
        # Anonymous: use session cart_id as the anonymous wishlist identifier
        cart_id = request.session.get("cart_id")
        if not cart_id:
            return set()
        return set(
            customer_models.Wishlist.objects.filter(wishlist_id=cart_id).values_list(
                "product_id", flat=True
            )
        )
    except Exception:
        return set()
