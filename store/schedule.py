import logging
import os
import sys
import threading
import time
from datetime import timedelta

from django.core.cache import cache
from django.db import close_old_connections
from django.utils import timezone

from store.tracking import sync_open_orders

logger = logging.getLogger(__name__)

HOURS = (11, 18)
_started = False


def next_run(now):
    local = timezone.localtime(now)
    for hour in HOURS:
        slot = local.replace(hour=hour, minute=0, second=0, microsecond=0)
        if slot >= local:
            return slot
    return (local + timedelta(days=1)).replace(hour=HOURS[0], minute=0, second=0, microsecond=0)


def slot_key(when):
    return timezone.localtime(when).strftime("shipment-sync-%Y%m%d-%H")


def run_slot(when):
    """One worker wins the Redis key for this hour. The others skip."""
    close_old_connections()
    try:
        if cache.add(slot_key(when), "1", timeout=20 * 60 * 60) is not True:
            return 0
        updated = sync_open_orders()
        logger.info("Shipment sync %s updated %s orders", slot_key(when), updated)
        return updated
    finally:
        close_old_connections()


def _loop():
    while True:
        try:
            when = next_run(timezone.now())
            delay = (when - timezone.now()).total_seconds()
            time.sleep(delay if delay > 0 else 0)
            run_slot(when)
        except Exception:
            logger.exception("Shipment sync loop failed")
            time.sleep(60)


def start_shipment_scheduler():
    global _started
    if _started or os.environ.get("ENVIRONMENT") != "prod":
        return
    if not any("gunicorn" in arg for arg in sys.argv):
        return
    _started = True
    threading.Thread(target=_loop, name="shipment-sync", daemon=True).start()
