import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from store import models as store_models
from userauths.models import NewsletterSubscription


class _Form:
    def __init__(self, instance, changed, initial):
        self.instance = instance
        self.changed_data = changed
        self.initial = initial


class AdminUndoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="undo@example.com",
            username="undo",
            password="secret",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _request(self):
        request = RequestFactory().post("/admin/")
        request.user = self.user
        return request

    def test_an_admin_save_can_be_undone_from_the_home_page(self):
        sub = NewsletterSubscription.objects.create(email="old@example.com")
        response = self.client.post(
            reverse("admin:userauths_newslettersubscription_change", args=[sub.pk]),
            {"email": "new@example.com", "is_active": "on"},
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(response.status_code, 302)
        sub.refresh_from_db()
        self.assertEqual(sub.email, "new@example.com")

        entry = LogEntry.objects.get(object_id=str(sub.pk))
        home = self.client.get(reverse("admin:index"), HTTP_HOST="127.0.0.1")
        self.assertContains(home, reverse("admin-undo", args=[entry.pk]))
        self.assertNotContains(home, "old@example.com")

        undone = self.client.post(reverse("admin-undo", args=[entry.pk]), HTTP_HOST="127.0.0.1")
        self.assertEqual(undone.status_code, 302)
        sub.refresh_from_db()
        self.assertEqual(sub.email, "old@example.com")

    def test_undo_puts_back_columns_and_selections_and_stops_after_a_later_edit(self):
        main = store_models.Category.objects.create(title="Main", sku="UNDO-MAIN", slug="undo-main")
        other = store_models.Category.objects.create(title="Other", sku="UNDO-OTHER", slug="undo-other")
        extra = store_models.Category.objects.create(title="Extra", sku="UNDO-EXTRA", slug="undo-extra")
        product = store_models.Product.objects.create(
            name="Old name", sku="UNDO-1", price=Decimal("10.00"), category=main,
        )
        product.additional_categories.add(extra)
        product.name = "New name"
        product.price = Decimal("20.00")
        product.category = other
        form = _Form(
            product,
            ["name", "price", "category", "image", "extra_images", "additional_categories"],
            {
                "name": "Old name",
                "price": Decimal("10.00"),
                "category": main.pk,
                "image": "images/old.avif",
                "additional_categories": [extra.pk],
            },
        )
        model_admin = admin.site._registry[store_models.Product]
        request = self._request()
        model_admin.save_model(request, product, form, True)
        product.additional_categories.clear()
        model_admin.log_change(
            request,
            product,
            [{"changed": {"fields": ["Name", "Price", "Category", "Image", "Extra photos", "colors"]}}],
        )
        entry = LogEntry.objects.get(object_id=str(product.pk))
        snapshot = json.loads(entry.change_message)[-1]["undo"]
        self.assertEqual(snapshot["fields"]["name"], "Old name")
        self.assertEqual(snapshot["fields"]["price"], "10.00")
        self.assertEqual(snapshot["fields"]["category_id"], main.pk)
        self.assertNotIn("image", snapshot["fields"])
        self.assertEqual(snapshot["m2m"]["additional_categories"], [extra.pk])

        self.client.post(reverse("admin-undo", args=[entry.pk]), HTTP_HOST="127.0.0.1")
        product.refresh_from_db()
        self.assertEqual(product.name, "Old name")
        self.assertEqual(product.price, Decimal("10.00"))
        self.assertEqual(product.category_id, main.pk)
        self.assertEqual(list(product.additional_categories.values_list("pk", flat=True)), [extra.pk])

        product.name = "Third name"
        later = _Form(product, ["name"], {"name": "Old name"})
        request = self._request()
        model_admin.save_model(request, product, later, True)
        model_admin.log_change(request, product, [{"changed": {"fields": ["Name"]}}])
        entry.refresh_from_db()
        self.assertIn("10.00", entry.change_message)
        self.client.post(reverse("admin-undo", args=[entry.pk]), HTTP_HOST="127.0.0.1")
        product.refresh_from_db()
        self.assertEqual(product.name, "Third name")

    def test_undoing_a_shipped_order_does_not_send_the_email_again(self):
        order = store_models.Order.objects.create(order_status="shipped")
        order.order_status = "processing"
        form = _Form(order, ["order_status"], {"order_status": "shipped"})
        model_admin = admin.site._registry[store_models.Order]
        request = self._request()
        model_admin.save_model(request, order, form, True)
        model_admin.log_change(request, order, [{"changed": {"fields": ["Order status"]}}])
        entry = LogEntry.objects.get(object_id=str(order.pk))

        with patch("store.signals.send_order_notification_email") as send:
            self.client.post(reverse("admin-undo", args=[entry.pk]), HTTP_HOST="127.0.0.1")

        send.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.order_status, "shipped")

    def test_a_description_is_dropped_after_a_day(self):
        previous = "previous description " * 40
        product = store_models.Product.objects.create(
            name="Band", sku="UNDO-DAY", description="current description",
        )
        product.description = "current description"
        form = _Form(product, ["description"], {"description": previous})
        model_admin = admin.site._registry[store_models.Product]
        request = self._request()
        model_admin.save_model(request, product, form, True)
        model_admin.log_change(request, product, [{"changed": {"fields": ["Description"]}}])
        entry = LogEntry.objects.get(object_id=str(product.pk))
        LogEntry.objects.filter(pk=entry.pk).update(action_time=timezone.now() - timedelta(hours=25))

        home = self.client.get(reverse("admin:index"), HTTP_HOST="127.0.0.1")

        self.assertNotContains(home, "previous description")
        entry.refresh_from_db()
        self.assertNotIn('"undo"', entry.change_message)
        self.assertIn("Description", entry.change_message)
        self.client.post(reverse("admin-undo", args=[entry.pk]), HTTP_HOST="127.0.0.1")
        product.refresh_from_db()
        self.assertEqual(product.description, "current description")
