from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from .models import Order, Category
from .emails import send_order_notification_email
from django.core.cache import cache

@receiver(pre_save, sender=Order)
def order_status_signal(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return
    if previous.order_status != "shipped" and instance.order_status == "shipped":
        send_order_notification_email(
            instance,
            f"Поръчка #{instance.order_id} e изпратена",
            "iBands: Пратката е изпратена",
            to_email=instance.address.email,
        )
    if previous.order_status != "delivered" and instance.order_status == "delivered":
        send_order_notification_email(
            instance,
            f"Поръчка #{instance.order_id} е доставена",
            "iBands: Пратката е доставена",
            to_email=instance.address.email,
        )

@receiver([post_save, post_delete], sender=Category)
def clear_category_cache(sender, **kwargs):
    cache.delete("category_tree")