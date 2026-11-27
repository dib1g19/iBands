import io
import hmac
import json
from types import SimpleNamespace
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, Client, SimpleTestCase, override_settings
from PIL import Image

from ibands_site.images import convert_uploaded_images
from store.admin import add_gallery_uploads
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from unittest.mock import patch
import re
from django.template.loader import render_to_string
from store.templatetags import pricing as pricing_tags

from store import models as store_models
from customer import models as customer_models


class FreeShippingPersistenceTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _claim(self, order):
        session = self.client.session
        owned = [str(item) for item in (session.get("checkout_order_ids") or [])]
        token = str(order.order_id)
        if token not in owned:
            owned.append(token)
        session["checkout_order_ids"] = owned
        session.save()

    def test_econt_office_free_shipping_applies_when_subtotal_over_threshold(self):
        order = store_models.Order.objects.create(sub_total=Decimal("100.00"), shipping=Decimal("5.00"), total=Decimal("105.00"))
        self._claim(order)
        url = reverse("store:save_econt_address", args=[order.order_id])
        payload = {
            "name": "Test User",
            "phone": "0888123456",
            "email": "test@example.com",
            "city": "София",
            "address": "",
            "office_code": "1234",
            "office_name": "Офис Еконт",
            "post_code": "1000",
            "face": "",
            "shipping_price": 6.20,
        }
        resp = self.client.post(url, data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.shipping, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("100.00"))

    def test_speedy_office_free_shipping_applies_when_subtotal_over_threshold(self):
        order = store_models.Order.objects.create(sub_total=Decimal("80.00"), shipping=Decimal("5.00"), total=Decimal("85.00"))
        self._claim(order)
        url = reverse("store:save_speedy_address", args=[order.order_id])
        payload = {
            "name": "Test User",
            "phone": "0888123456",
            "email": "test@example.com",
            "city": "София",
            "address": "",
            "office_code": "5678",
            "office_name": "Офис Спиди",
            "site_id": "12345",
            "shipping_price": 5.90,
        }
        resp = self.client.post(url, data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.shipping, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("80.00"))

    def test_pigeon_office_free_shipping_applies_when_subtotal_over_threshold(self):
        order = store_models.Order.objects.create(sub_total=Decimal("80.00"), shipping=Decimal("5.00"), total=Decimal("85.00"))
        self._claim(order)
        response = self.client.post(
            reverse("store:save_pigeon_address", args=[order.order_id]),
            data={
                "name": "Test User",
                "phone": "0888123456",
                "email": "test@example.com",
                "city": "София",
                "address": "",
                "office_code": "627",
                "office_name": "Офис Pigeon",
                "delivery_method": "pigeon_office",
                "city_id": "759",
                "shipping_price": 2.83,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.shipping, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("80.00"))
        self.assertEqual(order.address.delivery_method, "pigeon_office")

    def _save_office(self, order, price=6.20):
        self._claim(order)
        return self.client.post(
            reverse("store:save_econt_address", args=[order.order_id]),
            data={
                "name": "Test User",
                "phone": "0888123456",
                "email": "test@example.com",
                "city": "София",
                "address": "",
                "office_code": "1234",
                "office_name": "Офис Еконт",
                "post_code": "1000",
                "face": "",
                "shipping_price": price,
            },
            content_type="application/json",
        )

    def test_office_free_shipping_starts_at_40(self):
        order = store_models.Order.objects.create(sub_total=Decimal("40.00"), shipping=Decimal("5.00"), total=Decimal("45.00"))

        self._save_office(order)

        order.refresh_from_db()
        self.assertEqual(order.shipping, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("40.00"))

    def test_office_shipping_is_charged_under_40(self):
        order = store_models.Order.objects.create(sub_total=Decimal("39.99"), shipping=Decimal("5.00"), total=Decimal("44.99"))

        self._save_office(order)

        order.refresh_from_db()
        self.assertEqual(order.shipping, Decimal("6.20"))
        self.assertEqual(order.total, Decimal("46.19"))

    def test_coupon_changes_the_total_that_counts_toward_free_office_shipping(self):
        qualifies = store_models.Order.objects.create(sub_total=Decimal("50.00"), shipping=Decimal("5.00"), total=Decimal("55.00"))
        qualifies.coupons.add(store_models.Coupon.objects.create(code="OFF20", discount=20))

        self._save_office(qualifies)

        qualifies.refresh_from_db()
        self.assertEqual(qualifies.saved, Decimal("10.00"))
        self.assertEqual(qualifies.shipping, Decimal("0.00"))
        self.assertEqual(qualifies.total, Decimal("40.00"))

        misses = store_models.Order.objects.create(sub_total=Decimal("50.00"), shipping=Decimal("5.00"), total=Decimal("55.00"))
        misses.coupons.add(store_models.Coupon.objects.create(code="OFF30", discount=30))

        self._save_office(misses)

        misses.refresh_from_db()
        self.assertEqual(misses.saved, Decimal("15.00"))
        self.assertEqual(misses.shipping, Decimal("6.20"))
        self.assertEqual(misses.total, Decimal("41.20"))


class SpeedyCODAmountTests(TestCase):
    def setUp(self):
        self.client = Client()

    @patch("store.views.speedy_v1_create_shipment")
    def test_send_order_to_speedy_uses_goods_total_excluding_shipping_for_cod(self, mock_create_shipment):
        # Minimal product and order to generate a shipment
        product = store_models.Product.objects.create(name="Band X", price=Decimal("100.00"), sku="SKU-1")
        # Shipping should not be part of COD amount; set shipping to 10 to verify
        order = store_models.Order.objects.create(sub_total=Decimal("100.00"), shipping=Decimal("10.00"), total=Decimal("110.00"), payment_method="cash_on_delivery")
        address = customer_models.Address.objects.create(name="Test", phone="0888", email="t@e.com", delivery_method="speedy_office", city="София", office_code="1111", office_name="Офис")
        order.address = address
        order.save(update_fields=["address"])

        # Add one order item so weight calculation runs
        store_models.OrderItem.objects.create(order=order, product=product, qty=1, price=Decimal("100.00"), sub_total=Decimal("100.00"))

        # Configure mock to return a fake shipment response
        mock_create_shipment.return_value = {"shipmentNumber": "SP123"}

        from store import views as store_views
        store_views.send_order_to_speedy(order)

        self.assertTrue(mock_create_shipment.called)
        args, kwargs = mock_create_shipment.call_args
        shipment_request = args[0]
        cod_block = ((shipment_request or {}).get("service") or {}).get("additionalServices", {}).get("cod")
        self.assertIsNotNone(cod_block)
        self.assertEqual(cod_block.get("amount"), float(Decimal("100.00")))
        # Also ensure top-level COD block (if present) matches the same amount
        top_level_cod = (shipment_request or {}).get("cod")
        if isinstance(top_level_cod, dict):
            self.assertEqual(top_level_cod.get("amount"), float(Decimal("100.00")))
            self.assertEqual(top_level_cod.get("currency"), "EUR")


class PigeonShipmentTests(TestCase):
    @patch("store.views.pigeon_request")
    def test_cod_uses_goods_total_and_saves_the_reference(self, pigeon_request):
        pigeon_request.return_value = {"success": True, "data": {"reference_number": "PG123", "label_pdf": "abc"}}
        product = store_models.Product.objects.create(name="Band X", price=Decimal("100.00"), sku="SKU-PG")
        order = store_models.Order.objects.create(
            sub_total=Decimal("100.00"),
            shipping=Decimal("10.00"),
            total=Decimal("110.00"),
            payment_method="cash_on_delivery",
        )
        order.address = customer_models.Address.objects.create(
            name="Test User",
            phone="0888123456",
            email="t@e.com",
            delivery_method="pigeon_office",
            city="София",
            office_code="627",
            office_name="Офис",
        )
        order.save(update_fields=["address"])
        store_models.OrderItem.objects.create(
            order=order, product=product, qty=1, price=Decimal("100.00"), sub_total=Decimal("100.00"),
        )

        from store import views as store_views
        store_views.send_order_to_pigeon(order)

        payload = pigeon_request.call_args.args[2]
        self.assertEqual(payload["service_codes"]["cod_amount"], float(Decimal("100.00")))
        self.assertEqual(payload["who_pays"], "receiver")
        self.assertEqual(payload["delivery_office_id"], 627)
        self.assertEqual(payload["pickup_type"], "office")
        self.assertEqual(payload["pickup_office_id"], 10)
        self.assertNotIn("sender_address_id", payload)
        self.assertNotIn("label_pdf", pigeon_request.return_value["data"])
        order.refresh_from_db()
        self.assertEqual(order.tracking_id, "PG123")
        self.assertEqual(order.shipping_service, "pigeon")


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_checkout_test")
class StripeCheckoutTests(TestCase):
    def setUp(self):
        self.order = store_models.Order.objects.create(
            sub_total=Decimal("10.00"), shipping=Decimal("0.00"), total=Decimal("10.50"),
            address=customer_models.Address.objects.create(
                name="Test", phone="0888", email="t@example.com",
                delivery_method="econt_office", office_code="1234",
            ),
        )
        session = self.client.session
        session["checkout_order_ids"] = [str(self.order.order_id)]
        session.save()

    def _url(self, name):
        return reverse(f"store:{name}", args=[self.order.order_id])

    @patch("store.views.stripe.checkout.Session.create")
    def test_owned_checkout_saves_stripe_session_and_euro_amount(self, create):
        create.return_value = SimpleNamespace(id="cs_test")
        response = self.client.post(self._url("stripe_payment"))
        self.assertEqual(response.status_code, 200)
        price = create.call_args.kwargs["line_items"][0]["price_data"]
        self.assertEqual(price["currency"], "eur")
        self.assertEqual(price["unit_amount"], 1050)
        self.assertEqual(create.call_args.kwargs["client_reference_id"], str(self.order.pk))
        attempt = self.order.stripe_checkout_attempts.get()
        self.assertEqual((attempt.session_id, attempt.amount_minor, attempt.currency), ("cs_test", 1050, "eur"))
        self.assertEqual(
            create.call_args.kwargs["payment_intent_data"]["metadata"]["ibands_checkout_attempt"],
            str(attempt.reference),
        )

    @patch("store.views.stripe.checkout.Session.create")
    def test_card_checkout_requires_owned_csrf_protected_post(self, create):
        create.return_value = SimpleNamespace(id="cs_csrf")
        url = self._url("stripe_payment")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(Client().post(url).status_code, 404)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.cookies.update(self.client.cookies)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        create.assert_not_called()
        self.assertEqual(csrf_client.get(self._url("checkout")).status_code, 200)
        token = csrf_client.cookies["csrftoken"].value
        self.assertEqual(csrf_client.post(url, HTTP_X_CSRFTOKEN=token).status_code, 200)
        create.assert_called_once()

    def _paid_attempt(self):
        attempt = self.order.stripe_checkout_attempts.create(
            session_id="cs_confirm", amount_minor=1050, currency="eur",
        )
        session = {
            "id": attempt.session_id,
            "client_reference_id": str(self.order.pk),
            "mode": "payment",
            "payment_status": "paid",
            "payment_intent": "pi_confirm",
            "amount_total": 1050,
            "currency": "eur",
        }
        return attempt, session

    @patch("store.views._finish_checkout")
    @patch("store.views.stripe.checkout.Session.retrieve")
    def test_matching_payment_is_recorded_once(self, retrieve, finish):
        attempt, retrieve.return_value = self._paid_attempt()
        for _ in range(2):
            response = self.client.get(self._url("stripe_payment_verify"), {"session_id": attempt.session_id})
            self.assertRedirects(response, self._url("payment_status"), fetch_redirect_response=False)

        self.order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(self.order.order_status, "received")
        self.assertEqual(self.order.payment_id, "pi_confirm")
        self.assertEqual(attempt.payment_intent_id, "pi_confirm")
        finish.assert_called_once()
        retrieve.assert_called_once()

    @patch("store.views._finish_checkout")
    @patch("store.views.stripe.checkout.Session.retrieve")
    def test_confirmation_requires_a_local_attempt_and_matching_amount_and_currency(self, retrieve, finish):
        url = self._url("stripe_payment_verify")
        self.client.get(url, {"session_id": "cs_legacy"})
        retrieve.assert_not_called()

        attempt, paid_session = self._paid_attempt()
        for field, value in (("amount_total", 1000), ("currency", "usd"), ("client_reference_id", "other-order")):
            with self.subTest(field=field):
                retrieve.return_value = {**paid_session, field: value}
                self.client.get(url, {"session_id": attempt.session_id})
                self.order.refresh_from_db()
                self.assertEqual(self.order.payment_status, "processing")
        finish.assert_not_called()

    @patch("store.views._finish_checkout")
    def test_cod_can_only_be_confirmed_once_by_the_checkout_owner(self, finish):
        self.assertEqual(Client().post(self._url("cod_payment")).status_code, 404)
        for _ in range(2):
            response = self.client.post(self._url("cod_payment"))
            self.assertRedirects(response, self._url("payment_status"), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "cash_on_delivery")
        finish.assert_called_once()

    def test_receipt_uses_saved_status_and_requires_checkout_ownership(self):
        url = self._url("payment_status")
        self.assertEqual(Client().get(url).status_code, 404)
        response = self.client.get(url, {"payment_status": "paid"})
        self.assertEqual(response.context["payment_status"], "processing")

    def _card_attempt(self, session_id="cs_attempt"):
        self.order.payment_method = "card"
        self.order.save(update_fields=["payment_method"])
        return self.order.stripe_checkout_attempts.create(
            session_id=session_id, reference=uuid4(), amount_minor=1050, currency="eur",
        )

    def _deliver_failure(self, attempt, *, decline_code="insufficient_funds", created=None, signed=True):
        now = int(timezone.now().timestamp())
        payload = json.dumps({
            "id": "evt_checkout_failure_test",
            "object": "event",
            "type": "payment_intent.payment_failed",
            "created": now if created is None else created,
            "data": {"object": {
                "object": "payment_intent",
                "id": f"pi_{attempt.session_id}",
                "amount": attempt.amount_minor,
                "currency": attempt.currency,
                "metadata": {"ibands_checkout_attempt": str(attempt.reference)},
                "last_payment_error": {"decline_code": decline_code},
            }},
        }).encode()
        headers = {}
        if signed:
            signature = hmac.digest(b"whsec_checkout_test", f"{now}.".encode() + payload, "sha256").hex()
            headers["HTTP_STRIPE_SIGNATURE"] = f"t={now},v1={signature}"
        return Client(enforce_csrf_checks=True).post(
            reverse("store:stripe_webhook"), data=payload, content_type="application/json", **headers,
        )

    def test_signed_decline_enables_retry_and_appears_in_order_admin(self):
        buyer = get_user_model().objects.create_user(username="buyer", email="buyer@example.com")
        self.order.customer = buyer
        self.order.save(update_fields=["customer"])
        self.client.force_login(buyer)
        attempt = self._card_attempt()

        self.assertEqual(self._deliver_failure(attempt).status_code, 200)
        self.order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.order.payment_status, "failed")
        self.assertEqual(self.order.order_status, "initiated")
        self.assertEqual(attempt.payment_intent_id, "pi_cs_attempt")
        self.assertEqual(attempt.failure_code, "insufficient_funds")

        canceled = self.client.get(self._url("stripe_payment_verify"), {"canceled": "1"}, follow=True)
        self.assertContains(canceled, "Плащането не бе успешно!")
        self.assertContains(canceled, self._url("checkout"))
        self.assertContains(self.client.get(reverse("customer:dashboard")), "Повтори плащането")
        self.assertContains(self.client.get(self._url("checkout")), "Плащането с карта не бе успешно.")

        staff = get_user_model().objects.create_user(username="staff", email="staff@example.com", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label="store", codename="view_order"))
        self.client.force_login(staff)
        admin_page = self.client.get(reverse("admin:store_order_change", args=[self.order.pk]))
        self.assertContains(admin_page, "Stripe checkout attempts")
        self.assertContains(admin_page, "insufficient_funds")
        self.assertContains(admin_page, "pi_cs_attempt")

    def test_cancel_and_unsigned_notification_leave_checkout_processing(self):
        attempt = self._card_attempt()
        response = self.client.get(self._url("stripe_payment_verify"), {"canceled": "1"})
        self.assertRedirects(response, self._url("checkout"), fetch_redirect_response=False)
        self.assertEqual(self._deliver_failure(attempt, signed=False).status_code, 400)
        self.order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.order.payment_status, "processing")
        self.assertIsNone(attempt.last_failed_at)

    def test_old_failures_keep_their_history_without_overwriting_a_new_attempt_or_payment(self):
        old_attempt = self._card_attempt("cs_old")
        latest_attempt = self._card_attempt("cs_latest")
        self.assertEqual(self._deliver_failure(old_attempt).status_code, 200)
        self.order.refresh_from_db()
        old_attempt.refresh_from_db()
        self.assertEqual(self.order.payment_status, "processing")
        self.assertIsNotNone(old_attempt.last_failed_at)

        self.order.payment_status = "paid"
        self.order.order_status = "received"
        self.order.payment_id = "pi_cs_latest"
        self.order.save(update_fields=["payment_status", "order_status", "payment_id"])
        self.assertEqual(self._deliver_failure(latest_attempt).status_code, 200)
        self.assertEqual(self._deliver_failure(latest_attempt, created=1, decline_code="older").status_code, 200)
        self.order.refresh_from_db()
        latest_attempt.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(latest_attempt.failure_code, "insufficient_funds")

    @patch("store.views.stripe.checkout.Session.create")
    @patch("store.views.stripe.checkout.Session.retrieve")
    def test_retry_reuses_an_open_session_or_recovers_its_receipt_when_already_paid(self, retrieve, create):
        attempt = self._card_attempt()
        self.assertEqual(self._deliver_failure(attempt).status_code, 200)
        retrieve.return_value = {
            "id": attempt.session_id, "client_reference_id": str(self.order.pk), "status": "open",
            "payment_status": "unpaid", "amount_total": attempt.amount_minor, "currency": attempt.currency,
        }
        self.assertEqual(self.client.post(self._url("stripe_payment")).json(), {"sessionId": attempt.session_id})

        retrieve.return_value.update(status="complete", payment_status="paid")
        response = self.client.post(self._url("stripe_payment"))
        self.assertEqual(response.json()["returnUrl"], f'{self._url("stripe_payment_verify")}?session_id=cs_attempt')
        create.assert_not_called()

    @patch("store.views.stripe.checkout.Session.create")
    @patch("store.views.stripe.checkout.Session.expire")
    @patch("store.views.stripe.checkout.Session.retrieve")
    def test_retry_closes_a_stale_amount_before_creating_a_new_session(self, retrieve, expire, create):
        attempt = self._card_attempt()
        self.assertEqual(self._deliver_failure(attempt).status_code, 200)
        self.order.total = Decimal("12.50")
        self.order.save(update_fields=["total"])
        retrieve.return_value = {
            "id": attempt.session_id, "client_reference_id": str(self.order.pk), "status": "open",
            "payment_status": "unpaid", "amount_total": attempt.amount_minor, "currency": attempt.currency,
        }
        expire.return_value = {"status": "expired", "payment_status": "unpaid"}
        create.return_value = SimpleNamespace(id="cs_new")

        self.assertEqual(self.client.post(self._url("stripe_payment")).json(), {"sessionId": "cs_new"})
        expire.assert_called_once()
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "processing")
        self.assertEqual(self.order.stripe_checkout_attempts.get(session_id="cs_new").amount_minor, 1250)

    def test_unmatched_return_shows_review_even_after_a_decline(self):
        attempt = self._card_attempt()
        self.assertEqual(self._deliver_failure(attempt).status_code, 200)
        page = self.client.get(self._url("stripe_payment_verify"), {"session_id": "cs_legacy"}, follow=True)
        self.assertContains(page, "Ако сумата е изтеглена")
        self.assertNotContains(page, "Опитайте отново")


class EcontShipmentPriceTests(TestCase):
    def _order(self, lines, saved="0.00", shipping="5.00"):
        goods = sum((Decimal(sub_total) for _name, sub_total in lines), Decimal("0.00"))
        saved_amount = Decimal(saved)
        order = store_models.Order.objects.create(
            sub_total=goods,
            saved=saved_amount,
            shipping=Decimal(shipping),
            total=goods - saved_amount + Decimal(shipping),
            payment_method="cash_on_delivery",
        )
        order.address = customer_models.Address.objects.create(
            name="Test", phone="0888", email="t@example.com",
            delivery_method="econt_office", city="София", office_code="1234",
        )
        order.save(update_fields=["address"])
        created = []
        for index, (name, sub_total) in enumerate(lines, start=1):
            product = store_models.Product.objects.create(
                name=name, sku=f"SKU-E-{index}", description="Band", price=Decimal(sub_total),
            )
            created.append(store_models.OrderItem.objects.create(
                order=order, product=product, qty=1,
                price=Decimal(sub_total), sub_total=Decimal(sub_total),
            ))
        return order, created

    @patch("store.views.requests.post")
    def test_econt_item_prices_include_the_coupon_without_changing_the_order(self, post):
        response = post.return_value
        response.status_code = 200
        response.json.return_value = {"shipmentNumber": "EC1"}
        order, items = self._order([("Band", "30.00"), ("Case", "10.00"), ("Gift", "0.00")], saved="4.00")

        from store.views import send_order_to_econt
        send_order_to_econt(order)

        payload = post.call_args.kwargs["json"]
        prices = {row["name"]: row["totalPrice"] for row in payload["items"]}
        self.assertEqual(prices, {"Band": 27.0, "Case": 9.0, "Gift": 0.0})
        self.assertEqual(payload["orderSum"], 41.0)
        self.assertEqual(payload["cod"], 41.0)
        self.assertEqual(payload["currency"], "EUR")
        for item in items:
            item.refresh_from_db()
        self.assertEqual([item.sub_total for item in items], [Decimal("30.00"), Decimal("10.00"), Decimal("0.00")])

    def test_the_last_paid_line_absorbs_the_rounding(self):
        order, _items = self._order([("One", "10.00"), ("Two", "10.00")], saved="0.01", shipping="0.00")

        from store.views import econt_item_prices
        prices = list(econt_item_prices(order).values())

        self.assertEqual(prices, [Decimal("10.00"), Decimal("9.99")])
        self.assertEqual(sum(prices, Decimal("0.00")), Decimal("19.99"))


class CouponDiscountTests(TestCase):
    def _order(self, sub_total, shipping, price, qty=1):
        product = store_models.Product.objects.create(
            name="Band",
            sku=f"SKU-{sub_total}-{shipping}",
            description="Band",
            price=price,
        )
        order = store_models.Order.objects.create(
            sub_total=sub_total,
            shipping=shipping,
            total=sub_total + shipping,
        )
        item = store_models.OrderItem.objects.create(
            order=order,
            product=product,
            qty=qty,
            price=price,
            sub_total=sub_total,
        )
        return order, item

    def test_applying_a_coupon_reduces_the_order_once_and_leaves_line_prices(self):
        order, item = self._order(Decimal("40.00"), Decimal("5.00"), Decimal("20.00"), qty=2)
        item.product.category = store_models.Category.objects.create(
            title="Bands", sku="CAT-COUPON", slug="bands"
        )
        item.product.save()
        store_models.Coupon.objects.create(code="SAVE10", discount=10)
        session = self.client.session
        session["checkout_order_ids"] = [str(order.order_id)]
        session.save()

        response = self.client.post(
            reverse("store:coupon_apply", args=[order.order_id]),
            {"coupon_code": "SAVE10"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("SAVE10", payload["summary_html"])
        self.assertIn("4.00", payload["summary_html"])
        self.assertIn("41.00", payload["summary_html"])
        self.assertIn("20.00", payload["items_html"])
        self.assertIn("40.00", payload["items_html"])
        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("20.00"))
        self.assertEqual(item.sub_total, Decimal("40.00"))
        self.assertEqual(order.sub_total, Decimal("40.00"))
        self.assertEqual(order.saved, Decimal("4.00"))
        self.assertEqual(order.total, Decimal("41.00"))

    def test_shipping_save_keeps_the_same_discount(self):
        order, item = self._order(Decimal("100.00"), Decimal("5.00"), Decimal("100.00"))
        order.coupons.add(store_models.Coupon.objects.create(code="SAVE10", discount=10))
        session = self.client.session
        session["checkout_order_ids"] = [str(order.order_id)]
        session.save()

        response = self.client.post(
            reverse("store:save_econt_address", args=[order.order_id]),
            data={
                "name": "Test User",
                "phone": "0888123456",
                "email": "test@example.com",
                "city": "София",
                "address": "",
                "office_code": "1234",
                "office_name": "Офис Еконт",
                "post_code": "1000",
                "face": "",
                "shipping_price": 6.20,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("100.00"))
        self.assertEqual(item.sub_total, Decimal("100.00"))
        self.assertEqual(order.shipping, Decimal("0.00"))
        self.assertEqual(order.saved, Decimal("10.00"))
        self.assertEqual(order.total, Decimal("90.00"))

    def test_admin_refresh_applies_the_coupon_to_the_original_line_totals(self):
        order, item = self._order(Decimal("40.00"), Decimal("5.00"), Decimal("20.00"), qty=2)
        order.coupons.add(store_models.Coupon.objects.create(code="SAVE10", discount=10))
        order.saved = Decimal("4.00")
        order.total = Decimal("41.00")
        order.save(update_fields=["saved", "total"])

        order.refresh_totals_from_items()

        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("20.00"))
        self.assertEqual(item.sub_total, Decimal("40.00"))
        self.assertEqual(order.sub_total, Decimal("40.00"))
        self.assertEqual(order.saved, Decimal("4.00"))
        self.assertEqual(order.total, Decimal("41.00"))

    def test_admin_refresh_keeps_a_manual_discount_when_no_coupon_is_attached(self):
        order, _item = self._order(Decimal("40.00"), Decimal("5.00"), Decimal("40.00"))
        order.saved = Decimal("3.00")
        order.save(update_fields=["saved"])

        order.refresh_totals_from_items()

        order.refresh_from_db()
        self.assertEqual(order.sub_total, Decimal("40.00"))
        self.assertEqual(order.saved, Decimal("3.00"))
        self.assertEqual(order.total, Decimal("42.00"))


class CouponRulesTests(TestCase):
    def _user(self, email):
        return get_user_model().objects.create_user(
            email=email,
            username=email.split("@")[0],
            password="secret",
        )

    def _order(self, sub_total="40.00", price="20.00", qty=2, customer=None):
        n = store_models.Product.objects.count() + 1
        category = store_models.Category.objects.create(
            title=f"Bands {n}",
            sku=f"CAT-R-{n}",
            slug=f"bands-r-{n}",
        )
        product = store_models.Product.objects.create(
            name="Band",
            sku=f"SKU-R-{n}",
            description="Band",
            price=Decimal(price),
            category=category,
        )
        order = store_models.Order.objects.create(
            customer=customer,
            sub_total=Decimal(sub_total),
            shipping=Decimal("5.00"),
            total=Decimal(sub_total) + Decimal("5.00"),
        )
        store_models.OrderItem.objects.create(
            order=order,
            product=product,
            qty=qty,
            price=Decimal(price),
            sub_total=Decimal(sub_total),
        )
        return order

    def _apply(self, order, code):
        if order.customer_id is None:
            session = self.client.session
            owned = [str(item) for item in (session.get("checkout_order_ids") or [])]
            token = str(order.order_id)
            if token not in owned:
                owned.append(token)
                session["checkout_order_ids"] = owned
                session.save()
        return self.client.post(
            reverse("store:coupon_apply", args=[order.order_id]),
            {"coupon_code": code},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_lookup_ignores_case_and_spaces(self):
        order = self._order()
        store_models.Coupon.objects.create(code=" save10 ", discount=10)

        response = self._apply(order, "SaVe10")

        self.assertTrue(response.json()["success"])
        order.refresh_from_db()
        self.assertEqual(order.saved, Decimal("4.00"))

    def test_duplicate_codes_cannot_be_stored(self):
        store_models.Coupon.objects.create(code="SAVE10", discount=10)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                store_models.Coupon.objects.create(code="save10", discount=5)

    def test_discount_is_clamped_to_the_percent_range(self):
        high = store_models.Coupon.objects.create(code="HIGH", discount=150)
        low = store_models.Coupon.objects.create(code="LOW", discount=0)
        self.assertEqual(high.discount, 100)
        self.assertEqual(low.discount, 1)

    def test_inactive_expired_and_early_coupons_are_rejected(self):
        order = self._order()
        inactive = store_models.Coupon.objects.create(code="OFF", discount=10, active=False)
        early = store_models.Coupon.objects.create(
            code="EARLY",
            discount=10,
            valid_from=timezone.now() + timedelta(days=1),
        )
        expired = store_models.Coupon.objects.create(
            code="OLD",
            discount=10,
            valid_until=timezone.now() - timedelta(minutes=1),
        )

        self.assertIn("не е активен", self._apply(order, inactive.code).json()["message"])
        self.assertIn("още не е валиден", self._apply(order, early.code).json()["message"])
        self.assertIn("изтекъл", self._apply(order, expired.code).json()["message"])
        order.refresh_from_db()
        self.assertEqual(order.saved, Decimal("0.00"))

    def test_minimum_subtotal_is_required(self):
        order = self._order(sub_total="40.00")
        store_models.Coupon.objects.create(code="MIN50", discount=10, min_subtotal=Decimal("50.00"))

        response = self._apply(order, "min50")

        self.assertIn("50.00", response.json()["message"])
        order.refresh_from_db()
        self.assertFalse(order.coupons.exists())

    def test_a_paid_use_counts_against_the_global_limit(self):
        coupon = store_models.Coupon.objects.create(code="ONCE", discount=10, usage_limit=1)
        first = self._order()
        self.assertTrue(self._apply(first, "ONCE").json()["success"])
        store_models.Coupon.mark_order_redeemed(first)

        second = self._order()
        response = self._apply(second, "ONCE")

        self.assertIn("вече е използван", response.json()["message"])
        self.assertEqual(coupon.redemptions.count(), 1)

    def test_per_customer_limit_lets_another_customer_use_the_code(self):
        store_models.Coupon.objects.create(code="PER", discount=10, per_customer_limit=1)
        first_user = self._user("first@example.com")
        second_user = self._user("second@example.com")
        first = self._order(customer=first_user)
        self.client.force_login(first_user)
        self.assertTrue(self._apply(first, "PER").json()["success"])
        store_models.Coupon.mark_order_redeemed(first)

        again = self._order(customer=first_user)
        self.assertIn("Вече сте използвали", self._apply(again, "PER").json()["message"])

        self.client.force_login(second_user)
        other = self._order(customer=second_user)
        self.assertTrue(self._apply(other, "PER").json()["success"])

    def test_personal_coupon_requires_its_owner(self):
        owner = self._user("owner@example.com")
        other = self._user("other@example.com")
        store_models.Coupon.issue_personal(code="MINE", discount=10, user=owner)
        order = self._order()

        self.assertIn("влезли", self._apply(order, "MINE").json()["message"])
        self.client.force_login(other)
        self.assertIn("вашия акаунт", self._apply(order, "MINE").json()["message"])
        self.client.force_login(owner)
        self.assertTrue(self._apply(order, "MINE").json()["success"])

    def test_single_use_code_leaves_the_previous_open_checkout(self):
        store_models.Coupon.objects.create(code="MOVE", discount=10, usage_limit=1)
        first = self._order()
        second = self._order()
        self.assertTrue(self._apply(first, "MOVE").json()["success"])

        self.assertTrue(self._apply(second, "MOVE").json()["success"])

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.coupons.exists())
        self.assertEqual(first.saved, Decimal("0.00"))
        self.assertEqual(first.total, Decimal("45.00"))
        self.assertTrue(second.coupons.filter(code="MOVE").exists())

    def test_cash_payment_marks_the_coupon_redeemed(self):
        order = self._order()
        order.address = customer_models.Address.objects.create(
            name="Test",
            phone="0888",
            email="t@example.com",
            delivery_method="econt_office",
            city="София",
            office_code="1234",
        )
        order.save(update_fields=["address"])
        store_models.Coupon.objects.create(code="COD", discount=10)
        self.assertTrue(self._apply(order, "COD").json()["success"])

        with patch("store.views.send_order_notification_email"), \
             patch("store.views.send_order_to_econt", return_value=None), \
             patch("store.views.send_meta_purchase_event"):
            response = self.client.post(reverse("store:cod_payment", args=[order.order_id]))

        self.assertEqual(response.status_code, 302)
        redemption = store_models.CouponRedemption.objects.get(order=order)
        self.assertEqual(redemption.coupon.code, "COD")

    def test_spin_and_milestone_codes_carry_their_rules(self):
        user = self._user("spin@example.com")
        self.client.force_login(user)
        store_models.SpinPrize.objects.create(
            label="Отстъпка 10%",
            prize_type="discount_percent",
            discount_percent=10,
            min_order_total=Decimal("25.00"),
            weight=1,
            active=True,
        )
        store_models.SpinMilestone.objects.create(
            threshold_spins=1,
            prize_type="discount_percent",
            discount_percent=15,
            min_order_total=Decimal("30.00"),
            label="Лоялност",
            active=True,
        )

        response = self.client.post(reverse("store:spin_perform"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        coupon = store_models.Coupon.objects.get(code=payload["coupon_code"])
        self.assertEqual(coupon.owner, user)
        self.assertEqual(coupon.discount, 10)
        self.assertEqual(coupon.usage_limit, 1)
        self.assertEqual(coupon.per_customer_limit, 1)
        self.assertEqual(coupon.min_subtotal, Decimal("25.00"))
        self.assertEqual(coupon.valid_until, store_models.Coupon.end_of_local_day(timezone.localdate()))
        milestone = store_models.Coupon.objects.get(code=payload["milestone"]["coupon_code"])
        self.assertEqual(milestone.owner, user)
        self.assertEqual(milestone.discount, 15)
        self.assertEqual(milestone.usage_limit, 1)
        self.assertEqual(milestone.min_subtotal, Decimal("30.00"))
        self.assertIsNone(milestone.valid_until)

    def test_a_code_named_like_a_spin_prize_has_no_special_prefix_rule(self):
        order = self._order()
        store_models.Coupon.objects.create(code="SPIN-9-9", discount=5)

        response = self._apply(order, "spin-9-9")

        self.assertTrue(response.json()["success"])
        order.refresh_from_db()
        self.assertEqual(order.saved, Decimal("2.00"))

    def test_only_the_customer_who_started_an_unpaid_order_can_change_the_code(self):
        store_models.Coupon.objects.create(code="SAVE10", discount=10)
        category = store_models.Category.objects.create(
            title="Bands own", sku="CAT-OWN", slug="bands-own",
        )
        product = store_models.Product.objects.create(
            name="Band", sku="SKU-OWN", description="Band",
            price=Decimal("40.00"), category=category,
        )
        store_models.Cart.objects.create(
            cart_id="guest-cart", product=product, qty=1,
            price=Decimal("40.00"), sub_total=Decimal("40.00"),
        )
        session = self.client.session
        session["cart_id"] = "guest-cart"
        session.save()
        self.client.post(reverse("store:create_order"))
        order = store_models.Order.objects.get()

        stranger = Client()
        denied = stranger.post(
            reverse("store:coupon_apply", args=[order.order_id]),
            {"coupon_code": "SAVE10"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertIn("не е ваша", denied.json()["message"])

        self.assertTrue(self._apply(order, "SAVE10").json()["success"])
        page = self.client.get(reverse("store:checkout", args=[order.order_id]))
        self.assertContains(page, "Премахни кода")
        removed = self.client.post(
            reverse("store:coupon_remove", args=[order.order_id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertTrue(removed.json()["success"])
        self.assertIn("премахнат", removed.json()["message"])
        order.refresh_from_db()
        self.assertFalse(order.coupons.exists())
        self.assertEqual(order.saved, Decimal("0.00"))
        self.assertEqual(order.total, order.sub_total + order.shipping)

        buyer = self._user("buyer@example.com")
        owned = self._order(customer=buyer)
        self.client.force_login(self._user("thief@example.com"))
        self.assertIn("не е ваша", self._apply(owned, "SAVE10").json()["message"])

        self.client.force_login(buyer)
        self.assertTrue(self._apply(owned, "SAVE10").json()["success"])
        owned.order_status = "received"
        owned.save(update_fields=["order_status"])
        blocked = self._apply(owned, "SAVE10")
        self.assertIn("преди плащане", blocked.json()["message"])
        still_on = self.client.post(
            reverse("store:coupon_remove", args=[owned.order_id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertIn("преди плащане", still_on.json()["message"])
        owned.refresh_from_db()
        self.assertTrue(owned.coupons.filter(code="SAVE10").exists())

    def test_another_customer_opening_checkout_does_not_replace_the_address(self):
        owner = self._user("owner-addr@example.com")
        original = customer_models.Address.objects.create(
            user=owner,
            name="Owner",
            phone="0888000001",
            email="owner-addr@example.com",
            city="Пловдив",
            address="ул. Първа 1",
            is_main=True,
        )
        order = self._order(customer=owner)
        order.address = original
        order.save(update_fields=["address"])
        stranger = self._user("stranger-addr@example.com")
        customer_models.Address.objects.create(
            user=stranger,
            name="Stranger",
            phone="0888000002",
            email="stranger-addr@example.com",
            city="София",
            address="ул. Втора 2",
            is_main=True,
        )
        self.client.force_login(stranger)

        page = self.client.get(reverse("store:checkout", args=[order.order_id]))
        saved = self.client.post(
            reverse("store:save_econt_address", args=[order.order_id]),
            data={
                "name": "Stranger",
                "phone": "0888000002",
                "email": "stranger-addr@example.com",
                "city": "София",
                "address": "ул. Втора 2",
                "office_code": "",
                "office_name": "",
                "post_code": "",
                "face": "",
            },
            content_type="application/json",
        )

        self.assertNotContains(page, "0888000002", status_code=404)
        self.assertEqual(saved.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.address_id, original.pk)
        self.assertEqual(order.address.phone, "0888000001")


class UnfinishedOrderLinkTests(TestCase):
    def test_an_unfinished_order_links_back_to_its_checkout(self):
        user = get_user_model().objects.create_user(
            email="buyer@example.com", username="buyer", password="secret",
        )
        open_order = store_models.Order.objects.create(
            customer=user, order_status="initiated", sub_total=Decimal("10.00"), total=Decimal("10.00"),
        )
        open_order.address = customer_models.Address.objects.create(
            name="Test", phone="0888", email="buyer@example.com", city="София",
        )
        open_order.save(update_fields=["address"])
        store_models.Order.objects.create(
            customer=user, order_status="received", sub_total=Decimal("20.00"), total=Decimal("20.00"),
        )
        self.client.force_login(user)
        checkout_url = reverse("store:checkout", args=[open_order.order_id])

        dashboard = self.client.get(reverse("customer:dashboard"))
        detail = self.client.get(reverse("customer:order_detail", args=[open_order.order_id]))

        self.assertContains(dashboard, checkout_url)
        self.assertEqual(dashboard.content.decode().count("Продължи поръчката"), 1)
        self.assertContains(detail, checkout_url)
        self.assertContains(detail, "Продължи поръчката")

    def test_dashboard_counts_skip_unfinished_and_canceled_orders(self):
        user = get_user_model().objects.create_user(
            email="totals@example.com", username="totals", password="secret",
        )
        for status in ["initiated", "canceled", "received", "delivered"]:
            store_models.Order.objects.create(customer=user, order_status=status, total=Decimal("10.00"))
        self.client.force_login(user)

        dashboard = self.client.get(reverse("customer:dashboard"))

        self.assertEqual(dashboard.context["ladder"]["count"], 2)
        self.assertContains(dashboard, "Още 1 поръчка")
        self.assertContains(dashboard, "10% отстъпка")
        self.assertContains(dashboard, "2 / 3")

    def test_a_failed_payment_offers_retry_instead_of_continue(self):
        user = get_user_model().objects.create_user(
            email="retry@example.com", username="retry", password="secret",
        )
        store_models.Order.objects.create(
            customer=user, order_status="initiated", payment_status="failed", total=Decimal("10.00"),
        )
        self.client.force_login(user)

        dashboard = self.client.get(reverse("customer:dashboard"))

        self.assertContains(dashboard, "Повтори плащането")
        self.assertNotContains(dashboard, "Продължи поръчката")

    def test_staff_can_view_another_customers_order_without_changing_it(self):
        User = get_user_model()
        owner = User.objects.create_user(email="owner-view@example.com", username="owner-view", password="secret")
        address = customer_models.Address.objects.create(
            name="Лидия Първанова", phone="0888000001", email="owner-view@example.com", city="София",
        )
        order = store_models.Order.objects.create(
            customer=owner, address=address, order_status="received",
            sub_total=Decimal("10.00"), total=Decimal("10.00"),
        )
        guest_address = customer_models.Address.objects.create(
            name="Атанас Пинков", phone="0888000002", email="guest-view@example.com", city="София",
        )
        guest = store_models.Order.objects.create(
            customer=None, address=guest_address, order_status="received",
            sub_total=Decimal("12.00"), total=Decimal("12.00"),
        )
        stranger = User.objects.create_user(email="stranger-view@example.com", username="stranger-view", password="secret")
        staff = User.objects.create_user(
            email="staff-view@example.com", username="staff-view", password="secret", is_staff=True,
        )
        detail_url = reverse("customer:order_detail", args=[order.order_id])

        self.client.force_login(stranger)
        denied = self.client.get(detail_url)
        self.assertRedirects(denied, reverse("customer:dashboard"))

        self.client.force_login(staff)
        page = self.client.get(detail_url)
        self.assertContains(page, "Лидия Първанова")
        self.assertContains(page, order.order_id)
        order.refresh_from_db()
        self.assertEqual(order.customer_id, owner.id)

        guest_page = self.client.get(reverse("customer:order_detail", args=[guest.order_id]))
        self.assertContains(guest_page, "Атанас Пинков")
        guest.refresh_from_db()
        self.assertIsNone(guest.customer_id)


class EmailPriceRenderingTests(TestCase):
    def test_email_renders_discount_with_strike_when_item_price_below_regular(self):
        # Create product priced at 100; mark as Band of the Week so effective price is 50
        product = store_models.Product.objects.create(name="Band Y", price=Decimal("100.00"), sku="SKU-2")
        today = timezone.localdate()
        week_start = today - timezone.timedelta(days=today.weekday())
        store_models.BandOfTheWeek.objects.create(product=product, week_start=week_start)

        # Create order + item with price equal to effective price (50)
        order = store_models.Order.objects.create(sub_total=Decimal("50.00"), shipping=Decimal("0.00"), total=Decimal("50.00"))
        item = store_models.OrderItem.objects.create(order=order, product=product, qty=1, price=Decimal("50.00"), sub_total=Decimal("50.00"))

        context = {"order": order, "order_items": [item], "email_heading": "Тест", "email_title": "Тест"}
        html = render_to_string("email/order.html", context)

        # Should contain a struck-through regular price (100.00) and the bold discounted price (50.00)
        self.assertIn(pricing_tags.dual_price(Decimal("100.00")), html)
        self.assertIn(pricing_tags.dual_price(Decimal("50.00")), html)


class ServerErrorLogTests(TestCase):
    def _request(self, path, user):
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory

        request = RequestFactory().get(path)
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request.user = user
        return request

    def test_admin_error_returns_to_the_admin_with_a_notice(self):
        from django.contrib.auth import get_user_model
        from django.contrib.messages.storage.fallback import FallbackStorage
        from ibands_site.middleware import ServerErrorMiddleware

        user = get_user_model().objects.create_user(
            email="staff@example.com",
            username="staff",
            password="secret",
            is_staff=True,
        )
        request = self._request("/admin/store/product/", user)
        request._messages = FallbackStorage(request)
        response = ServerErrorMiddleware(lambda req: None).process_exception(
            request, RuntimeError("stock row missing")
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")
        stored = [message.message for message in request._messages]
        self.assertIn("stock row missing", stored[0])
        self.assertIn("See more", stored[0])
        log = store_models.ServerErrorLog.objects.get()
        self.assertEqual(log.exception_type, "RuntimeError")
        self.assertTrue(log.is_staff)
        self.assertEqual(log.user, user)
        self.assertIn("RuntimeError", log.traceback)

    def test_customer_error_is_stored_without_replacing_the_response(self):
        from django.contrib.auth.models import AnonymousUser
        from ibands_site.middleware import ServerErrorMiddleware

        request = self._request("/shop/", AnonymousUser())
        response = ServerErrorMiddleware(lambda req: None).process_exception(
            request, RuntimeError("secret boom")
        )

        self.assertIsNone(response)
        log = store_models.ServerErrorLog.objects.get()
        self.assertEqual(log.message, "secret boom")
        self.assertFalse(log.is_staff)
        self.assertEqual(log.path, "/shop/")

    def test_missing_pages_are_not_stored(self):
        from django.contrib.auth.models import AnonymousUser
        from django.http import Http404
        from ibands_site.middleware import ServerErrorMiddleware

        request = self._request("/missing/", AnonymousUser())
        response = ServerErrorMiddleware(lambda req: None).process_exception(request, Http404())

        self.assertIsNone(response)
        self.assertFalse(store_models.ServerErrorLog.objects.exists())


class SlugStabilityTests(TestCase):
    def test_category_keeps_its_address_when_the_title_changes(self):
        category = store_models.Category.objects.create(title="Mystery Box", sku="MB")
        self.assertEqual(category.slug, "mystery-box")

        category.title = "Мистериозни кутии"
        category.save()
        category.refresh_from_db()

        self.assertEqual(category.slug, "mystery-box")

    def test_product_keeps_its_address_when_the_name_changes(self):
        product = store_models.Product.objects.create(
            name="Classic box",
            sku="MB-CLASSIC",
            description="A box",
        )
        self.assertEqual(product.slug, "classic-box")

        product.name = "Classic Мистериозна кутия"
        product.save()
        product.refresh_from_db()

        self.assertEqual(product.slug, "classic-box")


class OrderAdminProductLabelTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_superuser(
            email="orders@example.com",
            username="orders",
            password="secret",
        )
        self.client.force_login(user)

    def _order_with_item(self, name, sku, qty=2, model="Ultra", size="49mm"):
        product = store_models.Product.objects.create(
            name=name,
            sku=sku,
            description="Band",
        )
        order = store_models.Order.objects.create(total=Decimal("20.00"))
        store_models.OrderItem.objects.create(
            order=order,
            product=product,
            qty=qty,
            model=model,
            size=size,
            price=Decimal("10.00"),
            sub_total=Decimal("20.00"),
        )
        return order, product

    def test_order_list_shows_each_line_without_a_query_per_order(self):
        long_name = "Силиконова каишка за Apple Watch Ultra 2 с много дълго име"
        order, product = self._order_with_item(long_name, "SKU-ULTRA-49")
        order.address = customer_models.Address.objects.create(
            name="Dimitar test",
            phone="0888123456",
        )
        order.save(update_fields=["address"])
        self._order_with_item("Втора каишка", "SKU-TWO", qty=1, model="", size="")

        url = reverse("admin:store_order_changelist")
        with CaptureQueriesContext(connection) as first:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, long_name)
        self.assertContains(response, "SKU-ULTRA-49")
        self.assertContains(response, reverse("admin:store_product_change", args=[product.pk]))
        self.assertContains(response, "Ultra 49mm ×2")
        self.assertContains(response, "Dimitar test")
        self.assertContains(response, "0888123456")
        self.assertContains(response, "field-recipient_name")
        self.assertEqual(
            sum("store_orderitem" in query["sql"] for query in first.captured_queries),
            1,
        )

        self._order_with_item("Трета каишка", "SKU-THREE")
        with CaptureQueriesContext(connection) as second:
            again = self.client.get(url)

        self.assertEqual(again.status_code, 200)
        self.assertContains(again, "SKU-THREE")
        self.assertEqual(len(second.captured_queries), len(first.captured_queries))

        found = self.client.get(url, {"q": "SKU-ULTRA-49"})
        self.assertContains(found, order.order_id)
        self.assertNotContains(found, "SKU-THREE")

    def test_order_page_shows_the_full_product_from_the_loaded_row(self):
        long_name = "Силиконова каишка за Apple Watch Ultra 2 с много дълго име"
        order, first = self._order_with_item(long_name, "SKU-ULTRA-49")
        second = store_models.Product.objects.create(
            name="Найлонова каишка за Garmin Fenix",
            sku="SKU-FENIX",
            description="Band",
        )
        store_models.OrderItem.objects.create(
            order=order,
            product=second,
            qty=1,
            price=Decimal("15.00"),
            sub_total=Decimal("15.00"),
            note="Blue strap if possible",
        )

        url = reverse("admin:store_order_change", args=[order.pk])
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, long_name)
        self.assertContains(response, "SKU-ULTRA-49")
        self.assertContains(response, "SKU-FENIX")
        self.assertNotContains(response, "Blue strap if possible")
        self.assertContains(response, "order_items-0-product")
        self.assertContains(response, "order_items-1-product")
        self.assertContains(response, reverse("admin:store_product_change", args=[first.pk]))
        self.assertContains(response, 'name="order_items-0-model"')
        self.assertContains(response, "<textarea")
        self.assertNotContains(response, "column-note")
        self.assertNotContains(response, "change_id_order_items-0-product")
        self.assertNotContains(response, "add_id_order_items-0-product")
        self.assertNotContains(response, "view_id_order_items-0-product")
        self.assertContains(response, "Address")
        self.assertNotContains(response, 'id="order-items-tab"')
        item_queries = [
            query["sql"]
            for query in ctx.captured_queries
            if "store_orderitem" in query["sql"]
        ]
        self.assertEqual(len(item_queries), 1)
        self.assertIn("store_product", item_queries[0])
        product_lookups = [
            query["sql"]
            for query in ctx.captured_queries
            if 'FROM "store_product"' in query["sql"]
        ]
        self.assertEqual(product_lookups, [])

    def _save_order(self, order, items, delete_pks=(), product_ids=None):
        product_ids = product_ids or {}
        url = reverse("admin:store_order_change", args=[order.pk])
        page = self.client.get(url)
        token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"',
            page.content.decode(),
        ).group(1)
        posted_at = timezone.localtime(order.date)
        data = {
            "csrfmiddlewaretoken": token,
            "order_status": order.order_status,
            "shipping_service": order.shipping_service or "",
            "tracking_id": order.tracking_id or "",
            "total": str(order.total),
            "sub_total": str(order.sub_total),
            "shipping": str(order.shipping),
            "saved": str(order.saved or 0),
            "payment_status": order.payment_status,
            "payment_method": order.payment_method or "",
            "order_id": order.order_id,
            "payment_id": order.payment_id or "",
            "date_0": posted_at.strftime("%Y-%m-%d"),
            "date_1": posted_at.strftime("%H:%M:%S"),
            "order_items-TOTAL_FORMS": str(len(items)),
            "order_items-INITIAL_FORMS": str(len(items)),
            "order_items-MIN_NUM_FORMS": "0",
            "order_items-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        for index, item in enumerate(items):
            prefix = f"order_items-{index}"
            data.update({
                f"{prefix}-id": str(item.pk),
                f"{prefix}-product": str(product_ids.get(item.pk, item.product_id)),
                f"{prefix}-model": item.model or "",
                f"{prefix}-size": item.size or "",
                f"{prefix}-qty": str(item.qty),
                f"{prefix}-price": str(item.price),
                f"{prefix}-sub_total": str(item.sub_total),
            })
            if item.pk in delete_pks:
                data[f"{prefix}-DELETE"] = "on"
        return self.client.post(url, data)

    def test_deleting_a_line_updates_the_order_subtotal(self):
        order, kept = self._order_with_item("Keep", "SKU-KEEP", qty=1)
        kept_item = order.order_items.get()
        kept_item.price = Decimal("20.00")
        kept_item.sub_total = Decimal("20.00")
        kept_item.save()
        removed_product = store_models.Product.objects.create(
            name="Remove", sku="SKU-REMOVE", description="Band", price=Decimal("10.00")
        )
        removed = store_models.OrderItem.objects.create(
            order=order,
            product=removed_product,
            qty=1,
            price=Decimal("10.00"),
            sub_total=Decimal("10.00"),
        )
        order.sub_total = Decimal("30.00")
        order.shipping = Decimal("5.00")
        order.total = Decimal("35.00")
        order.save()

        response = self._save_order(order, [kept_item, removed], delete_pks={removed.pk})

        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:1500])
        order.refresh_from_db()
        self.assertFalse(store_models.OrderItem.objects.filter(pk=removed.pk).exists())
        self.assertEqual(order.sub_total, Decimal("20.00"))
        self.assertEqual(order.total, Decimal("25.00"))

    def test_switching_a_line_uses_the_new_product_price(self):
        order, _old = self._order_with_item("Old band", "SKU-OLD", qty=2)
        item = order.order_items.get()
        item.qty = 2
        item.price = Decimal("10.00")
        item.sub_total = Decimal("20.00")
        item.save()
        order.sub_total = Decimal("20.00")
        order.shipping = Decimal("4.00")
        order.total = Decimal("24.00")
        order.save()
        replacement = store_models.Product.objects.create(
            name="New band", sku="SKU-NEW", description="Band", price=Decimal("15.00")
        )

        response = self._save_order(order, [item], product_ids={item.pk: replacement.pk})

        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:1500])
        item.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(item.product, replacement)
        self.assertEqual(item.price, Decimal("15.00"))
        self.assertEqual(item.sub_total, Decimal("30.00"))
        self.assertEqual(order.sub_total, Decimal("30.00"))
        self.assertEqual(order.total, Decimal("34.00"))


class AvifUploadTests(SimpleTestCase):
    def test_png_upload_becomes_avif_and_stored_files_stay(self):
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, format="PNG")
        product = store_models.Product(name="Band")
        product.image = SimpleUploadedFile("band.png", buf.getvalue(), content_type="image/png")

        convert_uploaded_images(product, "image")

        self.assertTrue(product.image.name.endswith("band.avif"))
        self.assertIn(b"ftyp", product.image.read())

        product.image = "images/already.png"
        convert_uploaded_images(product, "image")
        self.assertEqual(product.image.name, "images/already.png")


class GalleryUploadTests(TestCase):
    def test_new_photos_keep_the_lower_position_first(self):
        product = store_models.Product.objects.create(name="Band", sku="GAL-1", price=Decimal("10.00"))
        store_models.Gallery.objects.create(product=product, position=2)
        store_models.Gallery.objects.create(product=product, position=0)
        png = io.BytesIO()
        Image.new("RGB", (4, 4), (0, 0, 255)).save(png, format="PNG")
        uploads = [
            SimpleUploadedFile("one.png", png.getvalue(), content_type="image/png"),
            SimpleUploadedFile("two.png", png.getvalue(), content_type="image/png"),
        ]

        storage = store_models.Gallery._meta.get_field("image").storage
        with patch.object(storage, "save", side_effect=lambda name, content, max_length=None: name):
            add_gallery_uploads(product, uploads)

        rows = list(product.gallery_images.values_list("position", "image"))
        self.assertEqual([row[0] for row in rows], [0, 2, 3, 4])
        self.assertTrue(rows[2][1].endswith("one.avif"))
        self.assertTrue(rows[3][1].endswith("two.avif"))


class SpinPrizeFulfillmentTests(TestCase):
    def _user(self):
        return get_user_model().objects.create_user(
            email="spin-prize@example.com",
            username="spin-prize",
            password="secret",
        )

    def _order(self, user, sub_total="40.00"):
        return store_models.Order.objects.create(
            customer=user,
            sub_total=Decimal(sub_total),
            shipping=Decimal("5.00"),
            total=Decimal(sub_total) + Decimal("5.00"),
        )

    def _save_shipping(self, order, price="6.20", office=False):
        return self.client.post(
            reverse("store:save_econt_address", args=[order.order_id]),
            data={
                "name": "Test User",
                "phone": "0888123456",
                "email": "test@example.com",
                "city": "София",
                "address": "" if office else "ул. Тест 1",
                "office_code": "1234" if office else "",
                "office_name": "Офис Еконт" if office else "",
                "post_code": "1000",
                "face": "",
                "shipping_price": price,
            },
            content_type="application/json",
        )

    def test_cart_bar_names_the_free_shipping_prize_minimum(self):
        user = self._user()
        self.client.force_login(user)
        store_models.SpinEntry.objects.create(
            user=user,
            date=timezone.localdate(),
            result_label="Безплатна доставка",
            prize_type="free_shipping",
            free_shipping=True,
            min_order_total=Decimal("20.00"),
        )
        category = store_models.Category.objects.create(title="Bands", sku="BAR-CAT", slug="bar-cat")
        product = store_models.Product.objects.create(
            name="Band",
            sku="SKU-BAR",
            description="Band",
            price=Decimal("10.00"),
            category=category,
        )
        store_models.Cart.objects.create(
            cart_id="prize-cart",
            product=product,
            qty=1,
            price=Decimal("10.00"),
            sub_total=Decimal("10.00"),
        )
        session = self.client.session
        session["cart_id"] = "prize-cart"
        session.save()

        page = self.client.get(reverse("store:cart"))

        self.assertContains(page, 'data-office-threshold="40"')
        self.assertContains(page, 'data-prize-minimums="[20.0]"')

    def test_free_shipping_prize_covers_office_below_the_standing_threshold(self):
        user = self._user()
        self.client.force_login(user)
        store_models.SpinEntry.objects.create(
            user=user,
            date=timezone.localdate(),
            result_label="Безплатна доставка",
            prize_type="free_shipping",
            free_shipping=True,
            min_order_total=Decimal("20.00"),
        )
        home = self._order(user, sub_total="30.00")
        self._save_shipping(home)
        home.refresh_from_db()
        self.assertEqual(home.shipping, Decimal("6.20"))
        self.assertFalse(home.prize_free_shipping)

        office = self._order(user, sub_total="30.00")
        response = self._save_shipping(office, office=True)

        self.assertEqual(response.status_code, 200)
        office.refresh_from_db()
        self.assertEqual(office.shipping, Decimal("0.00"))
        self.assertTrue(office.prize_free_shipping)
        self.assertEqual(office.total, Decimal("30.00"))
        page = self.client.get(reverse("store:checkout", args=[office.order_id]))
        self.assertContains(page, 'data-office-threshold="40"')
        self.assertContains(page, 'data-prize-minimums="[20.0]"')

    def test_free_shipping_prize_waits_for_its_minimum(self):
        user = self._user()
        self.client.force_login(user)
        store_models.SpinEntry.objects.create(
            user=user,
            date=timezone.localdate(),
            result_label="Безплатна доставка",
            prize_type="free_shipping",
            free_shipping=True,
            min_order_total=Decimal("25.00"),
        )
        small = self._order(user, sub_total="20.00")

        self._save_shipping(small, office=True)

        small.refresh_from_db()
        self.assertEqual(small.shipping, Decimal("6.20"))
        self.assertFalse(small.prize_free_shipping)
        page = self.client.get(reverse("store:checkout", args=[small.order_id]))
        self.assertContains(page, 'data-office-threshold="40"')
        self.assertContains(page, 'data-prize-minimums="[25.0]"')

        large = self._order(user, sub_total="25.00")
        self._save_shipping(large, office=True)
        large.refresh_from_db()
        self.assertEqual(large.shipping, Decimal("0.00"))
        self.assertTrue(large.prize_free_shipping)

    def test_coupon_changes_whether_the_free_shipping_prize_applies(self):
        user = self._user()
        self.client.force_login(user)
        store_models.SpinEntry.objects.create(
            user=user,
            date=timezone.localdate(),
            result_label="Безплатна доставка",
            prize_type="free_shipping",
            free_shipping=True,
            min_order_total=Decimal("20.00"),
        )
        below = self._order(user, sub_total="25.00")
        below.coupons.add(store_models.Coupon.objects.create(code="PRIZE30", discount=30))

        self._save_shipping(below, office=True)

        below.refresh_from_db()
        self.assertEqual(below.saved, Decimal("7.50"))
        self.assertEqual(below.shipping, Decimal("6.20"))
        self.assertFalse(below.prize_free_shipping)
        self.assertEqual(below.total, Decimal("23.70"))

        above = self._order(user, sub_total="25.00")
        above.coupons.add(store_models.Coupon.objects.create(code="PRIZE10", discount=10))

        self._save_shipping(above, office=True)

        above.refresh_from_db()
        self.assertEqual(above.saved, Decimal("2.50"))
        self.assertEqual(above.shipping, Decimal("0.00"))
        self.assertTrue(above.prize_free_shipping)
        self.assertEqual(above.total, Decimal("22.50"))

    def test_office_threshold_does_not_spend_the_free_shipping_prize(self):
        user = self._user()
        self.client.force_login(user)
        store_models.SpinEntry.objects.create(
            user=user,
            date=timezone.localdate(),
            result_label="Безплатна доставка",
            prize_type="free_shipping",
            free_shipping=True,
        )
        order = self._order(user, sub_total="100.00")

        response = self.client.post(
            reverse("store:save_econt_address", args=[order.order_id]),
            data={
                "name": "Test User",
                "phone": "0888123456",
                "email": "test@example.com",
                "city": "София",
                "address": "",
                "office_code": "1234",
                "office_name": "Офис Еконт",
                "post_code": "1000",
                "face": "",
                "shipping_price": 6.20,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.shipping, Decimal("0.00"))
        self.assertFalse(order.prize_free_shipping)
        self.assertEqual(order.total, Decimal("100.00"))

    def test_yesterdays_free_shipping_prize_is_not_applied(self):
        user = self._user()
        self.client.force_login(user)
        store_models.SpinEntry.objects.create(
            user=user,
            date=timezone.localdate() - timedelta(days=1),
            result_label="Безплатна доставка",
            prize_type="free_shipping",
            free_shipping=True,
        )
        order = self._order(user, sub_total="30.00")

        self._save_shipping(order, office=True)

        order.refresh_from_db()
        self.assertEqual(order.shipping, Decimal("6.20"))
        self.assertFalse(order.prize_free_shipping)
        self.assertEqual(order.total, Decimal("36.20"))

    def test_paying_redeems_free_shipping_for_the_next_order(self):
        store_models.SpinMilestone.objects.filter(counts="orders").update(active=False)
        user = self._user()
        self.client.force_login(user)
        entry = store_models.SpinEntry.objects.create(
            user=user,
            date=timezone.localdate(),
            result_label="Безплатна доставка",
            prize_type="free_shipping",
            free_shipping=True,
        )
        order = self._order(user, sub_total="30.00")
        self._save_shipping(order, office=True)
        order.refresh_from_db()

        with patch("store.views.send_order_notification_email"), \
             patch("store.views.send_order_to_econt", return_value=None), \
             patch("store.views.send_meta_purchase_event"):
            self.client.post(reverse("store:cod_payment", args=[order.order_id]))

        entry.refresh_from_db()
        self.assertEqual(entry.redeemed_order, order)
        later = self._order(user, sub_total="30.00")
        self._save_shipping(later, office=True)
        later.refresh_from_db()
        self.assertEqual(later.shipping, Decimal("6.20"))
        self.assertFalse(later.prize_free_shipping)

    def _cart(self, cart_id, price):
        product = store_models.Product.objects.create(
            name="Band",
            sku=f"SKU-{cart_id}",
            description="Band",
            price=price,
        )
        store_models.Cart.objects.create(
            cart_id=cart_id,
            product=product,
            qty=1,
            price=price,
            sub_total=price,
        )

    def _start_order(self, cart_id):
        session = self.client.session
        session["cart_id"] = cart_id
        session.save()
        return self.client.post(reverse("store:create_order"))

    def test_mystery_box_is_added_only_when_the_merchandise_total_qualifies(self):
        user = self._user()
        self.client.force_login(user)
        store_models.SpinEntry.objects.create(
            user=user,
            date=timezone.localdate(),
            result_label="Mystery Box",
            prize_type="mystery_box_min_total",
            min_order_total=Decimal("20.00"),
        )
        box = store_models.Product.objects.create(
            name="Мистериозен продукт",
            slug="mystery-gift",
            sku="SKU-MYSTERY",
            description="Gift",
            price=Decimal("9.99"),
        )
        self._cart("under", Decimal("10.00"))

        self._start_order("under")

        small = store_models.Order.objects.get(customer=user)
        self.assertEqual(small.sub_total, Decimal("10.00"))
        self.assertFalse(small.order_items.filter(product=box).exists())

        self._cart("over", Decimal("30.00"))
        self._start_order("over")
        large = store_models.Order.objects.exclude(pk=small.pk).get(customer=user)
        prize = large.order_items.get(product=box)
        self.assertEqual(prize.price, Decimal("0.00"))
        self.assertEqual(prize.sub_total, Decimal("0.00"))
        self.assertEqual(prize.qty, 1)
        self.assertTrue(prize.note.startswith("prize:spin:"))
        self.assertEqual(large.sub_total, Decimal("30.00"))
        self.assertEqual(large.total, Decimal("30.00"))

    def test_milestone_mystery_box_uses_its_own_minimum(self):
        user = self._user()
        self.client.force_login(user)
        milestone = store_models.SpinMilestone.objects.create(
            threshold_spins=5,
            prize_type="mystery_box_min_total",
            min_order_total=Decimal("25.00"),
            label="Кутия",
        )
        award = store_models.SpinMilestoneAward.objects.create(user=user, milestone=milestone)
        category = store_models.Category.objects.create(title="Мистериозни кутии", sku="MS-BOX", slug="mystery-box")
        store_models.Product.objects.create(
            name="Mini Мистериозна кутия",
            sku="SKU-MS-BOX",
            description="Box",
            price=Decimal("24.99"),
            category=category,
        )
        self._cart("milestone", Decimal("25.00"))

        self._start_order("milestone")

        order = store_models.Order.objects.get(customer=user)
        prize = order.order_items.get(note=f"prize:milestone:{award.pk}")
        self.assertEqual(prize.product.name, "Mini Мистериозна кутия")
        self.assertEqual(prize.price, Decimal("0.00"))
        self.assertEqual(prize.sub_total, Decimal("0.00"))
        self.assertEqual(order.sub_total, Decimal("25.00"))

    def test_milestone_adds_the_shop_box_closest_to_its_minimum(self):
        user = self._user()
        self.client.force_login(user)
        milestone = store_models.SpinMilestone.objects.create(
            threshold_spins=100,
            prize_type="mystery_box_min_total",
            min_order_total=Decimal("75.00"),
            label="Premium",
        )
        award = store_models.SpinMilestoneAward.objects.create(user=user, milestone=milestone)
        category = store_models.Category.objects.create(title="Мистериозни кутии", sku="MS-ALL", slug="mystery-box")
        for name, sku, price in (
            ("Mini", "SKU-MINI", "24.99"),
            ("Classic", "SKU-CLASSIC", "49.99"),
            ("Premium", "SKU-PREMIUM", "99.99"),
        ):
            store_models.Product.objects.create(
                name=name,
                sku=sku,
                description="Box",
                price=Decimal(price),
                category=category,
            )
        self._cart("closest", Decimal("75.00"))

        self._start_order("closest")

        prize = store_models.Order.objects.get(customer=user).order_items.get(note=f"prize:milestone:{award.pk}")
        self.assertEqual(prize.product.name, "Premium")
        self.assertEqual(prize.price, Decimal("0.00"))


class CategoryAllSubTests(TestCase):
    def test_all_page_includes_child_products_when_tree_cache_is_empty(self):
        from store.context_processors import invalidate_category_tree_cache

        parent = store_models.Category.objects.create(title="Bands", sku="ALL-P", slug="bands")
        child = store_models.Category.objects.create(title="Silicone", sku="ALL-C", slug="silicone", parent=parent)
        store_models.Product.objects.create(
            name="Blue Band",
            sku="ALL-PROD",
            description="Band",
            category=child,
        )
        invalidate_category_tree_cache()

        response = Client().get(reverse("store:category_all_sub", kwargs={"category_path": "bands"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Blue Band")


class CategoryStatusTests(TestCase):
    def test_disabled_category_is_hidden_from_the_shop(self):
        from store.context_processors import get_category_tree, invalidate_category_tree_cache
        from store.sitemaps import CategorySitemap

        parent = store_models.Category.objects.create(title="Bands", sku="DIS-P", slug="bands")
        child = store_models.Category.objects.create(
            title="Retired", sku="DIS-C", slug="retired", parent=parent, status="disabled",
        )
        store_models.Category.objects.create(title="Gone", sku="DIS-G", slug="gone", status="disabled")
        product = store_models.Product.objects.create(
            name="Blue Band", sku="DIS-PROD", description="Band", category=child, slug="blue-band",
        )
        invalidate_category_tree_cache()

        tree = get_category_tree()
        self.assertEqual([category.slug for category in tree], ["bands"])
        self.assertEqual(tree[0].children, [])

        client = Client()
        self.assertEqual(client.get(reverse("store:category", kwargs={"category_path": "bands/retired"})).status_code, 404)
        self.assertEqual(client.get(product.get_absolute_url()).status_code, 404)
        parent_page = client.get(reverse("store:category", kwargs={"category_path": "bands"}))
        self.assertNotContains(parent_page, "Retired")
        shop = client.get(reverse("store:shop"))
        self.assertNotContains(shop, "Blue Band")
        roots = list(shop.context["categories"])
        self.assertEqual([category.slug for category in roots], ["bands"])
        self.assertEqual(list(roots[0].subcategories.all()), [])

        listed = [category.slug for category in CategorySitemap().items()]
        self.assertIn("bands", listed)
        self.assertNotIn("retired", listed)
        self.assertNotIn("gone", listed)

        staff = get_user_model().objects.create_superuser(
            email="cat-status@example.com", username="cat-status", password="secret",
        )
        staff_client = Client()
        staff_client.force_login(staff)
        self.assertEqual(
            staff_client.get(reverse("store:category", kwargs={"category_path": "bands/retired"})).status_code,
            200,
        )
        self.assertEqual(staff_client.get(product.get_absolute_url()).status_code, 200)

    def test_disabling_a_category_disables_its_subcategories_and_products(self):
        parent = store_models.Category.objects.create(title="Bands", sku="CAS-P", slug="cas-bands")
        child = store_models.Category.objects.create(title="Silicone", sku="CAS-C", slug="cas-silicone", parent=parent)
        grandchild = store_models.Category.objects.create(title="Sport", sku="CAS-G", slug="cas-sport", parent=child)
        own = store_models.Product.objects.create(
            name="Own", sku="CAS-OWN", description="Band", category=parent, slug="cas-own",
        )
        nested = store_models.Product.objects.create(
            name="Nested", sku="CAS-NEST", description="Band", category=grandchild, slug="cas-nested",
        )
        other = store_models.Category.objects.create(title="Cases", sku="CAS-O", slug="cas-cases")
        outsider = store_models.Product.objects.create(
            name="Out", sku="CAS-OUT", description="Case", category=other, slug="cas-out",
        )

        parent.status = "disabled"
        parent.save()

        for obj in (child, grandchild, own, nested):
            obj.refresh_from_db()
        other.refresh_from_db()
        outsider.refresh_from_db()
        self.assertEqual(child.status, "disabled")
        self.assertEqual(grandchild.status, "disabled")
        self.assertEqual(own.status, "disabled")
        self.assertEqual(nested.status, "disabled")
        self.assertEqual(other.status, "published")
        self.assertEqual(outsider.status, "published")

        own.status = "published"
        own.save()
        self.assertEqual(own.status, "disabled")

        parent.status = "published"
        parent.save()
        child.refresh_from_db()
        own.refresh_from_db()
        self.assertEqual(child.status, "disabled")
        self.assertEqual(own.status, "disabled")


class StaffUpdateTests(TestCase):
    def _staff(self):
        return get_user_model().objects.create_superuser(
            email="staff-note@example.com",
            username="staff-note",
            password="secret",
        )

    def test_the_dashboard_lists_the_latest_updates_beside_recent_actions(self):
        user = self._staff()
        user.full_name = "Dimitar"
        user.save(update_fields=["full_name"])
        base = timezone.now()
        for index in range(21):
            note = store_models.StaffUpdate.objects.create(
                summary=f"Update {index}",
                details="- Check the coupon page.\n- Confirm the redemption list.",
                created_by=user,
            )
            store_models.StaffUpdate.objects.filter(pk=note.pk).update(
                created_at=base - timedelta(minutes=index)
            )

        client = Client()
        client.force_login(user)
        response = client.get(reverse("admin:index"), HTTP_HOST="127.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "admin-home")
        self.assertContains(response, "Recent actions")
        self.assertContains(response, "What's new")
        self.assertContains(response, "Update 0")
        self.assertContains(response, "Check the coupon page.")
        self.assertContains(response, "Dimitar")
        self.assertNotContains(response, "Update 20")
        self.assertContains(response, "updates_page=2")

        older = client.get(reverse("admin:index") + "?updates_page=2", HTTP_HOST="127.0.0.1")
        self.assertContains(older, "Update 20")
        self.assertNotContains(older, "Update 0")

    def test_an_empty_update_list_says_so(self):
        store_models.StaffUpdate.objects.all().delete()
        client = Client()
        client.force_login(self._staff())
        response = client.get(reverse("admin:index"), HTTP_HOST="127.0.0.1")

        self.assertContains(response, "Nothing here yet.")


class ProductDuplicateTests(TestCase):
    def test_a_full_length_sku_still_copies_the_product(self):
        user = get_user_model().objects.create_superuser(
            email="copies@example.com",
            username="copies",
            password="secret",
        )
        self.client.force_login(user)
        category = store_models.Category.objects.create(title="Bands", sku="DUP-CAT", slug="dup-bands")
        variant = store_models.Variant.objects.create(name="Sport")
        size = store_models.Size.objects.create(name="49mm-dup")
        device = store_models.DeviceModel.objects.create(name="Ultra dup")
        product = store_models.Product.objects.create(
            name="A" * 255,
            sku="B" * 50,
            description="Band",
            category=category,
            price=Decimal("12.00"),
            status="published",
            stock=4,
            promo_type="buy_x_get_y",
            promo_buy_qty=2,
            promo_get_qty=1,
            is_mystery_box=True,
        )
        product.variants.add(variant)
        item = store_models.ProductItem.objects.create(
            product=product, size=size, quantity=4, price_delta=Decimal("1.50"), sku="ITEM-DUP",
        )
        item.device_models.add(device)

        response = self.client.post(
            reverse("admin:store_product_changelist"),
            {"action": "duplicate_product", "number_of_copies": "1", "_selected_action": [str(product.pk)]},
        )

        self.assertEqual(response.status_code, 302)
        copy = store_models.Product.objects.exclude(pk=product.pk).get()
        self.assertLessEqual(len(copy.sku), 50)
        self.assertTrue(copy.sku.endswith("-copy-1"))
        self.assertLessEqual(len(copy.name), 255)
        self.assertTrue(copy.name.endswith(" (Copy 1)"))
        self.assertEqual(copy.status, "disabled")
        self.assertEqual(copy.stock, 0)
        self.assertEqual(copy.promo_buy_qty, 2)
        self.assertTrue(copy.is_mystery_box)
        self.assertEqual(list(copy.variants.all()), [variant])
        copied_item = copy.items.get()
        self.assertEqual(copied_item.quantity, 0)
        self.assertEqual(copied_item.price_delta, Decimal("1.50"))
        self.assertEqual(copied_item.size, size)
        self.assertEqual(list(copied_item.device_models.all()), [device])
        self.assertIsNone(copied_item.sku)
        product.refresh_from_db()
        self.assertEqual(product.sku, "B" * 50)
        self.assertEqual(product.stock, 4)


class SavedDestinationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            email="buyer@example.com", username="buyer", password="secret",
            full_name="Иван Петров", mobile="0888123456",
        )
        self.client.force_login(self.user)

    def _order(self, customer=None):
        return store_models.Order.objects.create(
            customer=self.user if customer is None else customer,
            sub_total=Decimal("10.00"),
            shipping=Decimal("5.00"),
            total=Decimal("15.00"),
        )

    def _save_speedy(self, order, **extra):
        payload = {
            "name": "Test User",
            "phone": "0888123456",
            "email": "buyer@example.com",
            "city": "София",
            "address": "",
            "office_code": "5678",
            "office_name": "Офис Спиди",
            "site_id": "12345",
            "shipping_price": 5.90,
        }
        payload.update(extra)
        return self.client.post(
            reverse("store:save_speedy_address", args=[order.order_id]),
            data=payload,
            content_type="application/json",
        )

    def test_a_place_is_saved_once_and_contact_changes_update_it(self):
        order = self._order()
        incomplete = self._save_speedy(order, office_code="", office_name="", city="", address="", site_id="")
        self.assertFalse(incomplete.json()["success"])
        self.assertEqual(customer_models.Address.objects.count(), 0)

        self.assertTrue(self._save_speedy(order).json()["success"])
        order.refresh_from_db()
        saved = customer_models.Address.objects.get(saved=True)
        snapshot_id = order.address_id
        self.assertFalse(order.address.saved)
        self.assertNotEqual(snapshot_id, saved.pk)
        self.assertEqual(saved.site_id, "12345")
        self.assertEqual(saved.post_code, "")

        self.assertTrue(self._save_speedy(order, phone="0888000000").json()["success"])
        order.refresh_from_db()
        saved.refresh_from_db()
        self.assertEqual(order.address_id, snapshot_id)
        self.assertEqual(order.address.phone, "0888000000")
        self.assertEqual(saved.phone, "0888000000")
        self.assertEqual(customer_models.Address.objects.filter(saved=True).count(), 1)

        other = self._order()
        self.assertTrue(self._save_speedy(other, phone="0888111111").json()["success"])
        saved.refresh_from_db()
        self.assertEqual(saved.phone, "0888111111")
        self.assertEqual(customer_models.Address.objects.filter(saved=True).count(), 1)
        self.assertNotEqual(other.address_id, saved.pk)

        past = self._order()
        past.order_status = "received"
        past.address = saved
        past.save()
        self.assertTrue(self._save_speedy(order, phone="0888222222").json()["success"])
        saved.refresh_from_db()
        self.assertFalse(saved.saved)
        self.assertEqual(saved.phone, "0888111111")
        current = customer_models.Address.objects.get(saved=True)
        self.assertEqual(current.phone, "0888222222")
        self.assertTrue(current.is_main)
        self.assertFalse(saved.is_main)
        past.refresh_from_db()
        self.assertEqual(past.address_id, saved.pk)

    def test_the_first_saved_address_is_main_and_the_next_place_is_not(self):
        order = self._order()
        self.assertTrue(self._save_speedy(order).json()["success"])
        first = customer_models.Address.objects.get(saved=True)
        self.assertTrue(first.is_main)

        self.assertTrue(self._save_speedy(order, office_code="9999", office_name="Друг").json()["success"])
        first.refresh_from_db()
        second = customer_models.Address.objects.get(saved=True, office_code="9999")
        self.assertTrue(first.is_main)
        self.assertFalse(second.is_main)

    @patch("store.views.cache.get", return_value=[{"id": 41, "name": "София", "postal_code": "1000"}])
    def test_econt_city_search_filters_the_cached_list(self, _cache):
        response = self.client.get(reverse("store:econt_find_cities"), {"q": "соф"})
        self.assertEqual(response.json()["cities"][0]["id"], 41)

    @patch("store.views.econt_request")
    def test_econt_quote_prices_the_selected_office(self, econt_request):
        econt_request.return_value = {"receiverDueAmount": 3.35, "currency": "EUR"}
        order = self._order()
        response = self.client.get(reverse("store:econt_quote", args=[order.order_id]), {
            "office_id": "1127", "city": "София", "post_code": "1000", "payment": "cod",
        })
        self.assertEqual(response.json()["quote"]["price"], 3.35)
        body = econt_request.call_args[0][1]
        self.assertEqual(body["customerInfo"]["officeCode"], "1127")
        self.assertTrue(body["cod"])
        self.assertFalse(body["payAfterTest"])

    @patch("store.views.speedy_v1_calculate")
    def test_speedy_quote_is_private_and_returns_only_normalized_pricing(self, calculate):
        order = self._order()
        url = reverse("store:speedy_quote", args=[order.order_id])
        self.assertEqual(Client().get(url).status_code, 404)
        calculate.assert_not_called()

        calculate.return_value = {
            "calculations": [{"serviceId": 505, "price": {"total": 5.90, "currency": "EUR"}}],
            "internal": "provider response",
        }
        response = self.client.get(url, {"office_id": "1234"})
        self.assertEqual(response.json(), {
            "success": True,
            "quote": {"serviceId": 505, "price": 5.90, "currency": "EUR"},
        })

    def test_the_oldest_saved_address_is_chosen_when_none_is_main(self):
        older = customer_models.Address.objects.create(
            user=self.user, saved=True, phone="0888", delivery_method="speedy_office",
            city="София", office_code="1", office_name="Първи",
        )
        customer_models.Address.objects.create(
            user=self.user, saved=True, phone="0888", delivery_method="speedy_office",
            city="София", office_code="2", office_name="Втори",
        )
        picked = customer_models.earliest_saved_without_main(
            customer_models.Address.objects.filter(user=self.user)
        )
        self.assertEqual([row.pk for row in picked], [older.pk])
        older.is_main = True
        older.save(update_fields=["is_main"])
        self.assertEqual(
            customer_models.earliest_saved_without_main(
                customer_models.Address.objects.filter(user=self.user)
            ),
            [],
        )

    def test_a_guest_checkout_reuses_one_snapshot_and_skips_the_book(self):
        self.client.logout()
        order = store_models.Order.objects.create(sub_total=Decimal("10.00"), total=Decimal("10.00"))
        session = self.client.session
        session["checkout_order_ids"] = [str(order.order_id)]
        session.save()
        self.assertTrue(self._save_speedy(order).json()["success"])
        self.assertTrue(self._save_speedy(order, phone="0888000000").json()["success"])
        order.refresh_from_db()
        self.assertEqual(customer_models.Address.objects.count(), 1)
        self.assertFalse(order.address.saved)
        self.assertIsNone(order.address.user_id)
        self.assertEqual(order.address.phone, "0888000000")

    def test_one_complete_place_is_the_saved_winner(self):
        older = customer_models.Address.objects.create(
            user=self.user, phone="0888", delivery_method="speedy_office",
            city="София", office_code="1", office_name="Стар",
        )
        main = customer_models.Address.objects.create(
            user=self.user, phone="0888", delivery_method="speedy_office",
            city="София", office_code="1", office_name="Основен", is_main=True,
        )
        customer_models.Address.objects.create(
            user=self.user, phone="0888", delivery_method="speedy_office",
            city="София", office_name="Без код",
        )
        door = customer_models.Address.objects.create(
            user=self.user, phone="0888", delivery_method="speedy",
            city="София", address="ул. Витоша 1",
        )
        same_door = customer_models.Address.objects.create(
            user=self.user, phone="0888", delivery_method="speedy",
            city="софия", address="ул. витоша 1",
        )
        winners = customer_models.saved_destination_winners(
            customer_models.Address.objects.filter(user=self.user)
        )
        self.assertEqual({item.pk for item in winners}, {main.pk, same_door.pk})
        self.assertNotIn(older.pk, {item.pk for item in winners})
        self.assertNotEqual(door.pk, same_door.pk)

    def test_checkout_offers_saved_destinations_and_account_hides_the_rest(self):
        customer_models.Address.objects.create(
            user=self.user, saved=True, is_main=True, name="Иван", phone="0888123456",
            email="buyer@example.com", delivery_method="speedy_office", city="Пловдив",
            office_code="42", office_name="Офис Пловдив", site_id="99",
        )
        customer_models.Address.objects.create(
            user=self.user, saved=False, name="Снимка", phone="0888000099",
            delivery_method="speedy", city="Варна", address="ул. Скрита 2",
        )
        order = self._order()
        page = self.client.get(reverse("store:checkout", args=[order.order_id]))
        self.assertContains(page, "speedy-saved")
        self.assertContains(page, "pigeon-saved")
        self.assertContains(page, "econt-saved")
        self.assertContains(page, "delivery_form.js")
        self.assertContains(page, "speedy_city_search")
        self.assertContains(page, "pigeon_street_search")
        self.assertContains(page, "econt_street_search")
        self.assertNotContains(page, "econt-delivery-iframe")
        self.assertContains(page, '"office_code": "42"')
        self.assertContains(page, '"site_id": "99"')
        self.assertNotContains(page, "0888000099")

        account = self.client.get(reverse("customer:addresses"))
        self.assertContains(account, "Офис Пловдив")
        self.assertNotContains(account, "Снимка")
        self.assertNotContains(account, "Създай адрес")
        self.assertNotContains(account, "address-detail")
        self.assertRedirects(
            self.client.get(reverse("customer:address_create")),
            reverse("customer:addresses"),
        )

        kept = customer_models.Address.objects.get(office_code="42")
        order.address = kept
        order.save(update_fields=["address"])
        self.client.get(reverse("customer:delete_address", args=[kept.id]))
        kept.refresh_from_db()
        self.assertFalse(kept.saved)
        order.refresh_from_db()
        self.assertEqual(order.address_id, kept.pk)

    @patch("store.views.pigeon_request")
    @patch("store.views.cache.get", return_value={})
    def test_pigeon_shipment_reads_ids_from_the_address_when_cache_is_empty(self, _cache, pigeon_request):
        pigeon_request.return_value = {"success": True, "data": {"reference_number": "PG1"}}
        order = self._order()
        order.address = customer_models.Address.objects.create(
            user=self.user, name="Иван", phone="0888123456", email="buyer@example.com",
            delivery_method="pigeon", city="София", address="ул. Витоша 5",
            city_id="759", street_id="12", street_number="5",
        )
        order.save(update_fields=["address"])
        from store.views import send_order_to_pigeon
        send_order_to_pigeon(order)
        body = pigeon_request.call_args[0][2]
        self.assertEqual(body["delivery_address"]["city_id"], 759)
        self.assertEqual(body["delivery_address"]["street_id"], 12)
        self.assertEqual(body["delivery_address"]["street_number"], "5")

