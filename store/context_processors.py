from django.core.cache import cache
from django.conf import settings
from .models import Category, Cart
from customer.models import Wishlist


def build_category_tree(categories):
    """Recursively build a category tree from a flat list."""
    category_dict = {cat.id: cat for cat in categories}
    # Add an empty children list to each category
    for cat in categories:
        cat.children = []
    tree = []
    for cat in categories:
        if cat.parent_id:
            parent = category_dict.get(cat.parent_id)
            if parent:
                parent.children.append(cat)
        else:
            tree.append(cat)
    # Attach absolute url to each category (while parent is loaded)
    for cat in categories:
        cat.url = cat.get_absolute_url()
    return tree

def navigation_context(request):
    # Fetch category tree from cache
    category_tree = cache.get("category_tree")
    if category_tree is None:
        categories = list(Category.objects.all().select_related('parent'))
        category_tree = build_category_tree(categories)
        cache.set("category_tree", category_tree, timeout=None)

    try:
        cart_id = request.session.get("cart_id")
        total_cart_items = Cart.objects.filter(cart_id=cart_id).count()
    except Exception:
        total_cart_items = 0

    if request.user.is_authenticated:
        wishlist_count = Wishlist.objects.filter(user=request.user).count()
    else:
        wishlist_count = 0

    return {
        "category_tree": category_tree,
        "total_cart_items": total_cart_items,
        "wishlist_count": wishlist_count,
    }


def pixel_settings(request):
    """Expose pixel-related settings to templates."""
    return {
        "FACEBOOK_PIXEL_ID": getattr(settings, "FACEBOOK_PIXEL_ID", None),
    }