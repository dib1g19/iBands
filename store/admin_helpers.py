from django.urls import reverse
from django.utils.html import format_html


def order_product_label(product, *, link=False):
    """Full product name and SKU for an order line.

    Uses the product already loaded on the row. Callers prefetch or
    select_related the product so this does not query.
    """
    if not product:
        return "-"
    name = product.name or "-"
    sku = (product.sku or "").strip()
    if link and product.pk:
        url = reverse("admin:store_product_change", args=[product.pk])
        name_html = format_html('<a href="{}">{}</a>', url, name)
    else:
        name_html = format_html("{}", name)
    if sku:
        return format_html(
            '<span style="white-space:normal;display:inline-block;max-width:28rem">{} <span style="color:#666">({})</span></span>',
            name_html,
            sku,
        )
    return format_html(
        '<span style="white-space:normal;display:inline-block;max-width:28rem">{}</span>',
        name_html,
    )


def product_path_label(product, *, link=False, max_depth=3):
    """
    Build 'Grandparent / Parent / Category — Name' without calling Product.__str__.
    Assumes admins did select_related('product__category__parent__parent') to avoid N+1.
    """
    if not product:
        return "-"
    c = getattr(product, "category", None)
    titles = []
    if c:
        gp = getattr(c, "parent", None)
        ggp = getattr(gp, "parent", None)
        for node in (ggp, gp, c):
            if node:
                titles.append(node.title)
    label = f"{' — '.join(titles)} — {product.name}" if titles else product.name
    if link:
        url = reverse("admin:store_product_change", args=[product.pk])
        return format_html('<a href="{}">{}</a>', url, label)
    return label