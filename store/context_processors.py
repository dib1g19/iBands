from .models import Category, Cart
from customer.models import Wishlist


def navigation_context(request):
    # All categories
    categories = Category.objects.all()
    # Root categories
    root_categories = Category.objects.filter(parent__isnull=True)
    # Cart item count
    try:
        cart_id = request.session["cart_id"]
        total_cart_items = Cart.objects.filter(cart_id=cart_id).count()
    except Exception:
        total_cart_items = 0
    # Wishlist count
    if request.user.is_authenticated:
        wishlist_count = Wishlist.objects.filter(user=request.user).count()
    else:
        wishlist_count = 0
    return {
        "categories": categories,
        "root_categories": root_categories,
        "total_cart_items": total_cart_items,
        "wishlist_count": wishlist_count,
    }
