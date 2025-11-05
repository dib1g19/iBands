from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

def _validated_email(email_value):
    """Return a cleaned, valid email or None if invalid."""
    if not email_value:
        return None
    try:
        candidate = str(email_value).strip()
    except Exception:
        return None
    if not candidate or "@" not in candidate:
        return None
    # Syntactic validation
    try:
        validate_email(candidate)
    except ValidationError:
        return None
    # Extra safety: ensure each domain label length is 1..63 to avoid idna errors
    try:
        domain = candidate.split("@", 1)[1]
        labels = domain.split(".")
        if any(len(label) == 0 or len(label) > 63 for label in labels):
            return None
    except Exception:
        return None
    return candidate


def send_order_notification_email(order, email_heading, email_title, to_email):
    context = {
        "order": order,
        "order_items": order.order_items.all,
        "email_heading": email_heading,
        "email_title": email_title,
    }
    subject = f"{email_heading}"
    text_body = render_to_string("email/order.txt", context)
    html_body = render_to_string("email/order.html", context)

    cleaned_recipient = _validated_email(to_email)
    if not cleaned_recipient:
        # No valid recipient; do not attempt to send
        return
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[cleaned_recipient],
    )
    msg.attach_alternative(html_body, "text/html")
    try:
        msg.send()
    except Exception:
        # Fail safe: don't let email errors break checkout flow
        pass


def send_welcome_email(user=None, to_email=None, full_name=None):
    """
    Send a welcome email to a newly registered user.
    You can pass a user instance or just to_email/full_name.
    """
    try:
        if user is not None:
            if not to_email:
                to_email = getattr(user, "email", None)
            if not full_name:
                # Try user.profile.full_name first; fallback to any attribute
                try:
                    full_name = getattr(user, "profile", None) and getattr(user.profile, "full_name", None)
                except Exception:
                    full_name = None
                if not full_name:
                    full_name = getattr(user, "full_name", None) or getattr(user, "username", None) or ""
        if not to_email:
            return

        context = {
            "full_name": full_name or "",
            "site_url": settings.SITE_URL,
        }
        subject = "Добре дошли в iBands"
        text_body = render_to_string("email/welcome.txt", context)
        html_body = render_to_string("email/welcome.html", context)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send()
    except Exception:
        # Fail silently for welcome emails so registration flow is not interrupted
        pass