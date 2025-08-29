from decimal import Decimal
from django import template
from store import models as store_models

register = template.Library()


@register.simple_tag
def regular_plus_delta(product, size_name=None, model_name=None):
    """
    Returns regular price (product.price) plus the ProductItem.price_delta for the
    given size/model combination if such SKU exists; otherwise returns product.price.
    size_name/model_name are expected to be plain strings as stored in Cart/OrderItem.
    """
    try:
        base = Decimal(str(getattr(product, "price", 0) or 0))
    except Exception:
        base = Decimal("0")

    try:
        qs = store_models.ProductItem.objects.filter(product=product)
        if size_name:
            qs = qs.filter(size__name=size_name)
        if model_name:
            qs = qs.filter(device_models__name=model_name)
        sku = qs.first()
        if not sku:
            return base
        delta = getattr(sku, "price_delta", None) or Decimal("0")
        return base + Decimal(str(delta))
    except Exception:
        return base


