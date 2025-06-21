from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

def send_order_notification_email(order, email_heading, email_title):
    customer_merge_data = {
        'order': order,
        'order_items': order.order_items,
        'email_heading': email_heading,
        'email_title': email_title,
    }
    subject = f"{email_heading}"
    text_body = render_to_string("email/order.txt", customer_merge_data)
    html_body = render_to_string("email/order.html", customer_merge_data)
    email_msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.address.email]
    )
    email_msg.attach_alternative(html_body, "text/html")
    email_msg.send()