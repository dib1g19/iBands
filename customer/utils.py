from customer import models as customer_models
from store import models as store_models


def get_order_for_customer(user, order_id, queryset=None):
    """Return an order the user may view, claiming guest orders with the same email."""
    qs = queryset if queryset is not None else store_models.Order.objects.all()
    order = qs.filter(order_id=order_id).select_related("address").first()
    if not order:
        return None
    if order.customer_id == user.id:
        return order
    if order.customer_id is not None:
        return None

    address_email = ""
    if order.address_id and order.address:
        address_email = (order.address.email or "").strip().lower()
    user_email = (getattr(user, "email", None) or "").strip().lower()
    if address_email and user_email and address_email == user_email:
        order.customer = user
        order.save(update_fields=["customer"])
        return order
    return None


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
