from customer import models as customer_models


def get_user_wishlist_products(request):
    try:
        published = {"product__status": "published"}
        if request.user.is_authenticated:
            return set(
                customer_models.Wishlist.objects.filter(
                    user=request.user, **published
                ).values_list("product_id", flat=True)
            )
        # Anonymous: use session cart_id as the anonymous wishlist identifier
        cart_id = request.session.get("cart_id")
        if not cart_id:
            return set()
        return set(
            customer_models.Wishlist.objects.filter(
                wishlist_id=cart_id, **published
            ).values_list("product_id", flat=True)
        )
    except Exception:
        return set()
