from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from customer.models import Address
from store.models import Order
from store.schedule import next_run, run_slot
from store.tracking import econt_level, next_status, pigeon_level, speedy_level, sync_open_orders

SOFIA = ZoneInfo("Europe/Sofia")


class TrackingLevelTests(TestCase):
    def test_speedy_label_pickup_delivery_and_return(self):
        self.assertIsNone(speedy_level(148))
        self.assertEqual(speedy_level(39), "shipped")
        self.assertEqual(speedy_level(134), "ready")
        self.assertEqual(speedy_level(1134), "ready")
        self.assertEqual(speedy_level(-14), "completed")
        self.assertIsNone(speedy_level(124))
        self.assertIsNone(speedy_level(39, return_shipment_id="999"))

    def test_econt_prepared_sent_delivered_and_return(self):
        self.assertIsNone(econt_level({"shortDeliveryStatus": "Подготвена в eEcont"}))
        self.assertEqual(econt_level({"sendTime": "2026-11-23 18:00:00"}), "shipped")
        self.assertEqual(econt_level({"shortDeliveryStatus": "В офис на получателя"}), "ready")
        self.assertEqual(econt_level({"shortDeliveryStatus": "В офис"}), "shipped")
        self.assertEqual(econt_level({"shortDeliveryStatusEn": "Delivered"}), "completed")
        self.assertIsNone(econt_level({"shortDeliveryStatus": "Връща се към подател", "deliveryTime": "x"}))

    def test_pigeon_registered_accepted_delivered_and_return(self):
        self.assertIsNone(pigeon_level({"found": True, "status_code": "shipment_registered"}))
        self.assertEqual(pigeon_level({"found": True, "status_code": "shipment_accepted_in_office"}), "shipped")
        self.assertEqual(pigeon_level({"found": True, "status_code": "shipment_delivered_to_office"}), "ready")
        self.assertEqual(pigeon_level({"found": True, "status_code": "shipment_delivered_to_recipient"}), "completed")
        self.assertIsNone(pigeon_level({"found": True, "status_code": "shipment_returning_to_sender", "delivery_date": "x"}))

    def test_next_status_does_not_move_backward(self):
        self.assertEqual(next_status("received", "shipped"), "shipped")
        self.assertEqual(next_status("received", "ready"), "ready")
        self.assertEqual(next_status("shipped", "ready"), "ready")
        self.assertEqual(next_status("ready", "completed"), "completed")
        self.assertEqual(next_status("shipped", "completed"), "completed")
        self.assertIsNone(next_status("shipped", "shipped"))
        self.assertIsNone(next_status("completed", "shipped"))
        self.assertIsNone(next_status("completed", "ready"))


class SyncShipmentStatusTests(TestCase):
    def _order(self, **kwargs):
        address = Address.objects.create(name="Test", phone="0888", email="buyer@example.com", city="София")
        defaults = {
            "address": address,
            "order_status": "received",
            "shipping_service": "speedy",
            "tracking_id": "SP1",
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    @patch("store.signals.send_order_notification_email")
    @patch("store.tracking.fetch_levels")
    def test_updates_open_orders_and_skips_a_failed_carrier(self, fetch_levels, send_email):
        shipped = self._order(tracking_id="SP1")
        delivered = self._order(tracking_id="EC1", shipping_service="econt", order_status="shipped")
        waiting = self._order(tracking_id="PG1", shipping_service="pigeon")
        old = self._order(tracking_id="SP-OLD")
        Order.objects.filter(pk=old.pk).update(date=timezone.now() - timedelta(days=40))
        self._order(tracking_id="", shipping_service="speedy")
        self._order(tracking_id="SP-DONE", order_status="completed")

        def levels(service, tracking_ids):
            if service == "speedy":
                raise RuntimeError("down")
            if service == "econt":
                return {"EC1": "completed"}
            return {"PG1": "ready"}

        fetch_levels.side_effect = levels
        self.assertEqual(sync_open_orders(), 2)

        shipped.refresh_from_db()
        delivered.refresh_from_db()
        waiting.refresh_from_db()
        self.assertEqual(shipped.order_status, "received")
        self.assertEqual(delivered.order_status, "completed")
        self.assertEqual(waiting.order_status, "ready")
        self.assertEqual(send_email.call_count, 1)
        self.assertIn("готова за взимане", send_email.call_args.args[1])


class ShipmentScheduleTests(TestCase):
    def test_next_run_is_11_then_18_then_the_next_morning(self):
        morning = datetime(2026, 11, 24, 10, 0, tzinfo=SOFIA)
        self.assertEqual(next_run(morning), morning.replace(hour=11))
        self.assertEqual(next_run(morning.replace(hour=12)), morning.replace(hour=18))
        following = next_run(morning.replace(hour=18, minute=1))
        self.assertEqual(following, datetime(2026, 11, 25, 11, 0, tzinfo=SOFIA))

    @patch("store.schedule.sync_open_orders", return_value=1)
    @patch("store.schedule.cache.add", return_value=False)
    def test_a_second_process_does_not_sync_again(self, add, sync):
        run_slot(datetime(2026, 11, 24, 11, 0, tzinfo=SOFIA))
        sync.assert_not_called()
        add.assert_called_once()
