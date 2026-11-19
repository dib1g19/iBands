"""Apply a customer's unredeemed spin and milestone prizes to an order."""

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from store.models import (
    Order,
    OrderItem,
    Product,
    SpinEntry,
    SpinMilestoneAward,
)

FREE_SHIPPING_THRESHOLD = Decimal("40")
SPIN_NOTE = "prize:spin:"
MILESTONE_NOTE = "prize:milestone:"


def _signed_in(user):
    return user is not None and getattr(user, "is_authenticated", False)


def unredeemed_spin(user):
    if not _signed_in(user):
        return None
    return SpinEntry.objects.filter(
        user=user,
        date=timezone.localdate(),
        redeemed_order__isnull=True,
    ).first()


def unredeemed_milestone_awards(user):
    if not _signed_in(user):
        return SpinMilestoneAward.objects.none()
    return (
        SpinMilestoneAward.objects.filter(user=user, redeemed_order__isnull=True)
        .select_related("milestone")
        .order_by("awarded_at", "id")
    )


def _minimum_met(merchandise, minimum):
    if minimum is None:
        return True
    return Order.as_money(merchandise) >= Order.as_money(minimum)


def _free_shipping_candidates(user):
    spin = unredeemed_spin(user)
    if spin and (spin.free_shipping or spin.prize_type == "free_shipping"):
        yield spin, spin.min_order_total
    for award in unredeemed_milestone_awards(user):
        if award.milestone.prize_type == "free_shipping":
            yield award, award.milestone.min_order_total


def free_shipping_prize(user, merchandise):
    """The free-shipping prize this order qualifies for, if the customer has one."""
    for prize, minimum in _free_shipping_candidates(user):
        if _minimum_met(merchandise, minimum):
            return prize
    return None


def mystery_prizes(user):
    """Unredeemed mystery-box prizes as (note, minimum merchandise subtotal)."""
    prizes = []
    spin = unredeemed_spin(user)
    if spin and spin.prize_type == "mystery_box_min_total":
        prizes.append((f"{SPIN_NOTE}{spin.pk}", spin.min_order_total))
    for award in unredeemed_milestone_awards(user):
        if award.milestone.prize_type == "mystery_box_min_total":
            prizes.append((f"{MILESTONE_NOTE}{award.pk}", award.milestone.min_order_total))
    return prizes


def goods_after_coupon(order):
    """Merchandise total after the coupon. This is what free-shipping rules use."""
    sub_total = Order.as_money(order.sub_total)
    saved = order.discount_for_subtotal(sub_total, without_coupon=0)
    net = sub_total - saved
    if net < 0:
        net = Decimal("0.00")
    return Order.as_money(net)


def free_shipping_minimums(user):
    """Minimums for the customer's free-shipping prizes. None means no minimum."""
    return [None if minimum is None else float(Order.as_money(minimum)) for _prize, minimum in _free_shipping_candidates(user)]


def apply_quoted_shipping(order, user, quoted_price, is_office):
    """Store the carrier quote, or zero it for an office when the threshold or a prize says so."""
    goods = goods_after_coupon(order)
    office_free = is_office and goods >= FREE_SHIPPING_THRESHOLD
    prize_free = is_office and free_shipping_prize(user, goods) is not None
    if office_free or prize_free:
        order.shipping = Decimal("0.00")
        order.prize_free_shipping = prize_free and not office_free
    elif quoted_price is not None:
        order.shipping = Order.as_money(quoted_price)
        order.prize_free_shipping = False


def _mystery_gift_products():
    return Product.objects.filter(status="published").filter(
        Q(slug="mystery-gift") | Q(name__icontains="mystery gift")
    )


def _shop_mystery_boxes():
    return (
        Product.objects.filter(status="published")
        .filter(Q(category__slug="mystery-box") | Q(additional_categories__slug="mystery-box"))
        .exclude(pk__in=_mystery_gift_products().values("pk"))
        .distinct()
    )


def product_for_mystery_prize(note, minimum):
    """Daily spin adds the Mystery gift. A milestone adds the shop box closest to its minimum."""
    if note.startswith(SPIN_NOTE):
        return _mystery_gift_products().order_by("id").first()
    boxes = list(_shop_mystery_boxes())
    if not boxes:
        return None
    if minimum is None:
        return min(boxes, key=lambda product: (Order.as_money(product.price), product.id))
    target = Order.as_money(minimum)
    return min(boxes, key=lambda product: (abs(Order.as_money(product.price) - target), product.id))


def apply_mystery_box_prizes(order, user):
    """Add a free prize product for each prize whose minimum the merchandise total meets."""
    merchandise = Order.as_money(order.sub_total)
    for note, minimum in mystery_prizes(user):
        OrderItem.objects.filter(note=note, order__order_status="initiated").exclude(order=order).delete()
        existing = order.order_items.filter(note=note)
        product = product_for_mystery_prize(note, minimum) if _minimum_met(merchandise, minimum) else None
        if product is not None and existing.filter(product=product).exists():
            continue
        existing.delete()
        if product is None:
            continue
        OrderItem.objects.create(
            order=order,
            product=product,
            qty=1,
            price=Decimal("0.00"),
            sub_total=Decimal("0.00"),
            note=note,
        )


def _unmet_minimum(minimum, merchandise):
    if _minimum_met(merchandise, minimum):
        return None
    return Order.as_money(minimum)


def mystery_gift_shortfall(user, merchandise):
    """Minimum still required for today's Mystery gift, or None when it is met or absent."""
    spin = unredeemed_spin(user)
    if not spin or spin.prize_type != "mystery_box_min_total":
        return None
    return _unmet_minimum(spin.min_order_total, merchandise)


def mystery_milestone_shortfall(user, merchandise):
    """Smallest unmet milestone mystery-box minimum, or None when one already qualifies."""
    shortfall = None
    for award in unredeemed_milestone_awards(user):
        if award.milestone.prize_type != "mystery_box_min_total":
            continue
        required = _unmet_minimum(award.milestone.min_order_total, merchandise)
        if required is None:
            return None
        if shortfall is None or required < shortfall:
            shortfall = required
    return shortfall


def redeem_prizes(order):
    """Mark the prizes this paid order actually used."""
    notes = [
        note
        for note in order.order_items.values_list("note", flat=True)
        if note
    ]
    spin_ids = [note.removeprefix(SPIN_NOTE) for note in notes if note.startswith(SPIN_NOTE)]
    milestone_ids = [note.removeprefix(MILESTONE_NOTE) for note in notes if note.startswith(MILESTONE_NOTE)]
    if spin_ids:
        SpinEntry.objects.filter(pk__in=spin_ids, redeemed_order__isnull=True).update(redeemed_order=order)
    if milestone_ids:
        SpinMilestoneAward.objects.filter(pk__in=milestone_ids, redeemed_order__isnull=True).update(
            redeemed_order=order
        )
    if order.prize_free_shipping and order.customer_id:
        prize = free_shipping_prize(order.customer, goods_after_coupon(order))
        if prize is not None and prize.redeemed_order_id is None:
            prize.redeemed_order = order
            prize.save(update_fields=["redeemed_order"])
