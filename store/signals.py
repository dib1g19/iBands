from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from .models import Order, Category, CategoryLink
from .emails import send_order_notification_email
from .context_processors import invalidate_category_tree_cache
from .prizes import sync_order_milestones

@receiver(pre_save, sender=Order)
def order_status_signal(sender, instance, **kwargs):
    instance._previous_status = None
    if not instance.pk:
        return
    try:
        previous = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return
    instance._previous_status = previous.order_status
    if getattr(instance, "_skip_order_email", False):
        return
    if previous.order_status != "shipped" and instance.order_status == "shipped":
        send_order_notification_email(
            instance,
            f"Поръчка #{instance.order_id} e изпратена",
            "iBands: Пратката е изпратена",
            to_email=instance.address.email,
        )
    if previous.order_status != "ready" and instance.order_status == "ready":
        send_order_notification_email(
            instance,
            f"Поръчка #{instance.order_id} е готова за взимане",
            "iBands: Пратката е готова за взимане",
            to_email=instance.address.email,
        )


@receiver(post_save, sender=Order)
def order_cancel_rewards(sender, instance, **kwargs):
    previous = getattr(instance, "_previous_status", None)
    if not instance.customer_id or previous == instance.order_status:
        return
    if "canceled" in (previous, instance.order_status):
        sync_order_milestones(instance.customer, instance)


@receiver([post_save, post_delete], sender=Category)
def clear_category_cache(sender, **kwargs):
    invalidate_category_tree_cache()


@receiver([post_save, post_delete], sender=CategoryLink)
def clear_category_link_cache(sender, **kwargs):
    invalidate_category_tree_cache()
