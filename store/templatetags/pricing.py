from decimal import Decimal, ROUND_HALF_UP
from django import template
from django.contrib.humanize.templatetags.humanize import intcomma
from store import models as store_models

register = template.Library()

BGN_PER_EUR = Decimal("1.95583")


def _to_decimal(value):
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


@register.filter
def dual_price(value, decimals=2):
    """
    Format a BGN price as "X.XX € / Y.YY лв."
    """
    try:
        decimals = int(decimals)
    except Exception:
        decimals = 2
    q = Decimal("1." + ("0" * decimals))
    amount_bgn = _to_decimal(value)
    amount_eur = amount_bgn / BGN_PER_EUR if BGN_PER_EUR else Decimal("0")
    bgn_str = intcomma(amount_bgn.quantize(q, rounding=ROUND_HALF_UP))
    eur_str = intcomma(amount_eur.quantize(q, rounding=ROUND_HALF_UP))
    return f"{eur_str} € / {bgn_str} лв."


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


@register.simple_tag
def promo_label(product):
    try:
        label = product.promo_label()
        return label or ""
    except Exception:
        return ""


@register.simple_tag
def promo_paid_units(product, qty):
    try:
        return product.compute_promo_paid_units(qty)
    except Exception:
        return qty


@register.simple_tag
def promo_free_units(product, qty):
    try:
        return product.compute_promo_free_units(qty)
    except Exception:
        return 0


