from django import template

register = template.Library()

# Sidebar sections. Keys are Jazzmin's "app.model" strings, or a custom link name.
MENU_SECTIONS = [
    {
        "name": "Catalog",
        "icon": "fas fa-box",
        "open": True,
        "items": [
            "store.product",
            "store.productitem",
            "store.category",
            "store.categorylink",
            "store.gallery",
        ],
    },
    {
        "name": "Options",
        "icon": "fas fa-sliders",
        "items": [
            "store.variant",
            "store.variantitem",
            "store.color",
            "store.colorgroup",
            "store.size",
            "store.sizegroup",
            "store.devicemodel",
            "store.modelgroup",
        ],
    },
    {
        "name": "Orders",
        "icon": "fas fa-clipboard-list",
        "open": True,
        "items": [
            "store.order",
            "store.orderitem",
            "store.cart",
        ],
    },
    {
        "name": "Promotions",
        "icon": "fas fa-bullhorn",
        "items": [
            "store.coupon",
            "store.bandoftheweek",
            "store.review",
            "store.spinprize",
            "store.spinmilestone",
            "store.spinmilestoneaward",
            "store.spinentry",
        ],
    },
    {
        "name": "Site",
        "icon": "fas fa-gear",
        "items": [
            "store.storethemesettings",
            "stats",
            "store.servererrorlog",
        ],
    },
    {
        "name": "Accounts",
        "icon": "fas fa-users",
        "items": [
            "userauths.user",
            "userauths.profile",
            "userauths.contactmessage",
            "userauths.newslettersubscription",
        ],
    },
    {
        "name": "Customers",
        "icon": "fas fa-address-book",
        "items": [
            "customer.address",
            "customer.notifications",
            "customer.wishlist",
        ],
    },
]


def _menu_key(item):
    model_str = item.get("model_str")
    if model_str:
        return model_str.lower()
    return (item.get("name") or "").strip().lower()


@register.simple_tag
def admin_menu_sections(side_menu_list):
    """Split the Jazzmin app menu into collapsible sections."""
    by_key = {}
    ordered = []
    for app in side_menu_list or []:
        for item in app.get("models", []):
            key = _menu_key(item)
            if not key or key in by_key:
                continue
            by_key[key] = item
            ordered.append(key)

    used = set()
    sections = []
    for section in MENU_SECTIONS:
        models = []
        for key in section["items"]:
            item = by_key.get(key.lower())
            if item:
                models.append(item)
                used.add(key.lower())
        if models:
            sections.append(
                {
                    "name": section["name"],
                    "icon": section["icon"],
                    "open": section.get("open", False),
                    "models": models,
                }
            )

    leftover = [by_key[key] for key in ordered if key not in used]
    if leftover:
        sections.append({"name": "More", "icon": "fas fa-ellipsis", "models": leftover})
    return sections
