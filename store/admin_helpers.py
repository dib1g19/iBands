from django.urls import reverse
from django.utils.html import format_html

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