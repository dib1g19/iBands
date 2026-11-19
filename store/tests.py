import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, Client, SimpleTestCase
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

    def test_econt_office_free_shipping_applies_when_subtotal_over_threshold(self):
        order = store_models.Order.objects.create(sub_total=Decimal("100.00"), shipping=Decimal("5.00"), total=Decimal("105.00"))
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

    def _save_office(self, order, price=6.20):
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
            delivery_method="econt",
            city="София",
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

