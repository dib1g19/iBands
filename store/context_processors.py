from django.core.cache import cache
from django.conf import settings
from .models import Category, Cart, CategoryLink, StoreThemeSettings
from customer.models import Wishlist


def build_category_tree(categories):
    """Recursively build a category tree from a flat list."""
    category_dict = {cat.id: cat for cat in categories}
    # Add an empty children list to each category
    for cat in categories:
        cat.children = []
        cat.url = None
    tree = []
    for cat in categories:
        if cat.parent_id:
            parent = category_dict.get(cat.parent_id)
            if parent:
                parent.children.append(cat)
        else:
            tree.append(cat)
    # Include virtual placements (CategoryLink) as additional children
    try:
        links = CategoryLink.objects.select_related("parent", "child").all()
        for link in links:
            parent = category_dict.get(link.parent_id)
            child = category_dict.get(link.child_id)
            if parent and child and child not in parent.children:
                parent.children.append(child)
    except Exception:
        pass
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

    try:
        if request.user.is_authenticated:
            wishlist_count = Wishlist.objects.filter(user=request.user).count()
        else:
            cart_id = request.session.get("cart_id")
            wishlist_count = (
                Wishlist.objects.filter(wishlist_id=cart_id).count() if cart_id else 0
            )
    except Exception:
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


def theme_settings(request):
    """Expose the active seasonal campaign for manual admin-controlled theming.

    Returns a small dict with label/icon/classes and titles used across templates.
    """
    active_key = StoreThemeSettings.get_active_campaign()

    campaigns = {
        "default": {
            "key": "default",
            "nav_label": "Разпродажба",
            "nav_icon": "fas fa-tags",
            "nav_icon_class": "",
            "nav_text_class": "",
            "section_class": "",
            "home_sale_title": "Разпродажба",
            "sale_title": "Разпродажба",
        },
        "halloween": {
            "key": "halloween",
            "nav_label": "Halloween",
            "nav_icon": "fas fa-spider",
            "nav_icon_class": "text-warning",
            "nav_text_class": "text-warning",
            "section_class": "halloween-section",
            "home_sale_title": "Halloween Разпродажба",
            "sale_title": "Halloween Разпродажба – Намалени продукти",
        },
        # Prepared for future toggle without code changes
        "black-friday": {
            "key": "black-friday",
            "nav_label": "Black Friday",
            "nav_icon": "fas fa-tag",
            "nav_icon_class": "",
            "nav_text_class": "",
            "section_class": "",  # add a class and CSS later if needed
            "home_sale_title": "Black Friday Разпродажба",
            "sale_title": "Black Friday Разпродажба – Намалени продукти",
        },
    }

    campaign = campaigns.get(active_key) or campaigns["default"]
    return {"campaign": campaign}