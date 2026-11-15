from django.db import connection
from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
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
        self._order_with_item("Втора каишка", "SKU-TWO", qty=1, model="", size="")

        url = reverse("admin:store_order_changelist")
        with CaptureQueriesContext(connection) as first:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, long_name)
        self.assertContains(response, "SKU-ULTRA-49")
        self.assertContains(response, reverse("admin:store_product_change", args=[product.pk]))
        self.assertContains(response, "×2")
        self.assertContains(response, "Ultra")
        self.assertContains(response, "49mm")
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

