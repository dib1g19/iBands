from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Order
from .emails import send_order_shipped_email, send_order_delivered_email

@receiver(pre_save, sender=Order)
def order_shipped_signal(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return
    if previous.order_status != "shipped" and instance.order_status == "shipped":
        send_order_shipped_email(instance)
    if previous.order_status != "delivered" and instance.order_status == "delivered":
        send_order_delivered_email(instance)