"""Apply a customer's unredeemed spin and milestone prizes to an order."""

import random
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from store.models import (
    PLACED_ORDER_STATUSES,
    Coupon,
    CouponRedemption,
    Order,
    OrderItem,
    Product,
    SpinEntry,
    SpinMilestone,
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
        if award.prize_type == "free_shipping":
            yield award, award.min_order_total


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
        if award.prize_type == "mystery_box_min_total":
            prizes.append((f"{MILESTONE_NOTE}{award.pk}", award.min_order_total))
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
        if award.prize_type != "mystery_box_min_total":
            continue
        required = _unmet_minimum(award.min_order_total, merchandise)
        if required is None:
            return None
        if shortfall is None or required < shortfall:
            shortfall = required
    return shortfall


def placed_order_count(user):
    return Order.objects.filter(customer=user, order_status__in=PLACED_ORDER_STATUSES).count()


def issue_milestone_award(user, milestone, earned_order=None):
    """Grant a milestone once per customer. A discount milestone comes with a personal coupon."""
    award, created = SpinMilestoneAward.objects.get_or_create(
        user=user, milestone=milestone, defaults={"earned_order": earned_order},
    )
    if created and milestone.prize_type == "discount_percent" and milestone.discount_percent:
        prefix = "LO" if milestone.counts == "orders" else "MS"
        coupon = Coupon.issue_personal(
            code=f"{prefix}-{user.id}-{milestone.threshold_spins}-{random.randint(100000, 999999)}",
            discount=int(milestone.discount_percent),
            user=user,
            min_subtotal=milestone.min_order_total,
        )
        award.coupon_code = coupon.code
        award.save(update_fields=["coupon_code"])
    return award, created


def milestone_award_used(award):
    if award.redeemed_order_id:
        return True
    if award.coupon_code:
        return CouponRedemption.objects.filter(coupon__code=award.coupon_code).exists()
    return False


def sync_order_milestones(user, order=None):
    """Grant the order milestones the customer has reached and take back unused ones they no longer reach.

    Returns the awards granted now.
    """
    if not _signed_in(user):
        return []
    count = placed_order_count(user)
    granted = []
    reached = SpinMilestone.objects.filter(counts="orders", active=True, threshold_spins__lte=count)
    for milestone in reached:
        award, created = issue_milestone_award(user, milestone, earned_order=order)
        if created:
            granted.append(award)
    lost = SpinMilestoneAward.objects.filter(
        user=user, milestone__counts="orders", milestone__threshold_spins__gt=count,
    ).select_related("milestone")
    for award in lost:
        if milestone_award_used(award):
            continue
        if award.coupon_code:
            Coupon.objects.filter(code=award.coupon_code, owner=user).delete()
        award.delete()
    return granted


def _plural(count, one, many):
    return f"{count} {one if count == 1 else many}"


def _how_to_use(prize_type, minimum, code):
    floor = f"{Order.as_money(minimum)} €" if minimum is not None else None
    if prize_type == "free_shipping":
        text = "Прилага се сама при доставка до офис."
        return f"{text} Поръчката трябва да е поне {floor}." if floor else text
    if prize_type == "mystery_box_min_total":
        return f"Добавя се сама в поръчка от поне {floor}." if floor else "Добавя се сама в следващата поръчка."
    if prize_type == "discount_percent" and code:
        text = "Въведете кода в полето „Код за отстъпка“ при поръчка."
        return f"{text} Поръчката трябва да е поне {floor}." if floor else text
    return ""


def _coupon_used(code):
    return bool(code) and CouponRedemption.objects.filter(coupon__code=code).exists()


def customer_rewards(user):
    """Every reward the customer can still use, with where it came from, how it applies, and until when."""
    rewards = []
    spin = unredeemed_spin(user)
    if spin and spin.prize_type != "none" and not _coupon_used(spin.coupon_code):
        rewards.append({
            "label": spin.result_label,
            "source": "Колелото на късмета днес",
            "how": _how_to_use(spin.prize_type, spin.min_order_total, spin.coupon_code),
            "valid": "Важи до края на деня",
            "code": spin.coupon_code,
        })
    for award in unredeemed_milestone_awards(user):
        if milestone_award_used(award):
            continue
        milestone = award.milestone
        if milestone.counts == "orders":
            source = f"Награда за {_plural(milestone.threshold_spins, 'поръчка', 'поръчки')}"
        else:
            source = f"Награда за {_plural(milestone.threshold_spins, 'завъртане', 'завъртания')}"
        coupon = Coupon.objects.filter(code=award.coupon_code).first() if award.coupon_code else None
        minimum = coupon.min_subtotal if coupon else award.min_order_total
        valid_until = coupon.valid_until if coupon else None
        rewards.append({
            "label": award.label,
            "source": source,
            "how": _how_to_use(award.prize_type, minimum, award.coupon_code),
            "valid": f"Важи до {timezone.localtime(valid_until):%d.%m.%Y}" if valid_until else "",
            "code": award.coupon_code,
        })
    return rewards


def order_ladder(user):
    """Where the customer stands on the placed-order reward ladder."""
    count = placed_order_count(user) if _signed_in(user) else 0
    milestones = list(SpinMilestone.objects.filter(counts="orders", active=True).order_by("threshold_spins", "id"))
    upcoming = next((m for m in milestones if m.threshold_spins > count), None)
    progress = int(count * 100 / upcoming.threshold_spins) if upcoming else 100
    return {
        "count": count,
        "next": upcoming,
        "remaining": upcoming.threshold_spins - count if upcoming else 0,
        "progress": progress,
        "has_milestones": bool(milestones),
    }


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
