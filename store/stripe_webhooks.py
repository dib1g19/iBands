import logging
from datetime import UTC, datetime
from uuid import UUID

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from store.models import Order, StripeCheckoutAttempt


logger = logging.getLogger(__name__)
ATTEMPT_METADATA_KEY = "ibands_checkout_attempt"


@csrf_exempt
@require_POST
def payment_failure_webhook(request):
    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse(status=503)

    try:
        event = stripe.Webhook.construct_event(
            request.body,
            request.headers.get("Stripe-Signature", ""),
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event.get("type") == "payment_intent.payment_failed":
        try:
            _record_payment_failure(event)
        except IntegrityError:
            logger.warning("Could not bind Stripe failure event %s to a unique attempt", event.get("id"))
            return HttpResponse(status=409)
    return HttpResponse(status=200)


def _record_payment_failure(event):
    intent = event["data"]["object"]
    reference = (intent.get("metadata") or {}).get(ATTEMPT_METADATA_KEY)
    if not isinstance(reference, str) or not reference:
        return
    try:
        reference = UUID(reference)
        failed_at = datetime.fromtimestamp(event["created"], UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        return

    payment_intent_id = intent.get("id")
    if not isinstance(payment_intent_id, str) or not payment_intent_id:
        return
    payment_error = intent.get("last_payment_error") or {}
    failure_code = payment_error.get("decline_code") or payment_error.get("code") or ""

    with transaction.atomic():
        attempt = StripeCheckoutAttempt.objects.filter(reference=reference).first()
        if attempt is None:
            return
        order = Order.objects.select_for_update().filter(pk=attempt.order_id).first()
        if order is None:
            return
        attempt.refresh_from_db(fields=["payment_intent_id", "last_failed_at"])
        if (
            intent.get("amount") != attempt.amount_minor
            or intent.get("currency") != attempt.currency
            or attempt.payment_intent_id not in (None, payment_intent_id)
            or (attempt.last_failed_at and failed_at <= attempt.last_failed_at)
        ):
            return

        attempt.payment_intent_id = payment_intent_id
        attempt.last_failed_at = failed_at
        attempt.failure_code = failure_code[:80]
        attempt.save(update_fields=["payment_intent_id", "last_failed_at", "failure_code"])

        if (
            order.order_status == "initiated"
            and order.payment_method == "card"
            and order.payment_status == "processing"
            and not order.stripe_checkout_attempts.filter(pk__gt=attempt.pk).exists()
        ):
            order.payment_status = "failed"
            order.save(update_fields=["payment_status"])
