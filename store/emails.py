from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

def send_order_shipped_email(order):
    customer_merge_data = {
        'order': order,
        'order_items': order.order_items,
    }
    subject = f"Вашата поръчка #{order.order_id} беше изпратена"
    text_body = render_to_string("email/order/order_shipped.txt", customer_merge_data)
    html_body = render_to_string("email/order/order_shipped.html", customer_merge_data)
    email_msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.address.email]
    )
    email_msg.attach_alternative(html_body, "text/html")
    email_msg.send()

def send_order_delivered_email(order):
    customer_merge_data = {
        'order': order,
        'order_items': order.order_items,
    }
    subject = f"Вашата поръчка #{order.order_id} беше доставена"
    text_body = render_to_string("email/order/order_delivered.txt", customer_merge_data)
    html_body = render_to_string("email/order/order_delivered.html", customer_merge_data)
    email_msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.address.email]
    )
    email_msg.attach_alternative(html_body, "text/html")
    email_msg.send()