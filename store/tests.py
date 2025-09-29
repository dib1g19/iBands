from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from decimal import Decimal
from django.template.loader import render_to_string

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
    def test_send_order_to_speedy_uses_order_total_for_cod(self, mock_create_shipment):
        # Minimal product and order to generate a shipment
        product = store_models.Product.objects.create(name="Band X", price=Decimal("100.00"), sku="SKU-1")
        order = store_models.Order.objects.create(sub_total=Decimal("100.00"), shipping=Decimal("0.00"), total=Decimal("100.00"), payment_method="cash_on_delivery")
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
        self.assertEqual(cod_block.get("amount"), float(order.total))


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
        self.assertIn("100.00 лв.", html)
        self.assertIn("50.00 лв.", html)

