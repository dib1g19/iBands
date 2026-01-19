from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction

from store import models as store_models


class Command(BaseCommand):
    help = "Convert monetary fields between BGN and EUR using a fixed rate."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rate",
            type=str,
            default="1.95583",
            help="BGN per EUR exchange rate (default: 1.95583).",
        )
        parser.add_argument(
            "--direction",
            choices=["bgn-to-eur", "eur-to-bgn"],
            default="bgn-to-eur",
            help="Conversion direction (default: bgn-to-eur).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Bulk update batch size (default: 500).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show counts without writing changes.",
        )

    def handle(self, *args, **options):
        rate = Decimal(str(options["rate"]))
        direction = options["direction"]
        batch_size = int(options["batch_size"])
        dry_run = options["dry_run"]

        quant = Decimal("0.01")

        def convert_value(value):
            if value is None:
                return None
            amount = Decimal(str(value))
            if direction == "bgn-to-eur":
                converted = amount / rate
            else:
                converted = amount * rate
            return converted.quantize(quant, rounding=ROUND_HALF_UP)

        model_specs = [
            (store_models.Product, ["price", "sale_price", "shipping"]),
            (store_models.Cart, ["price", "sub_total"]),
            (store_models.Order, ["sub_total", "shipping", "total", "saved"]),
            (store_models.OrderItem, ["price", "sub_total"]),
            (store_models.ProductItem, ["price_delta"]),
            (store_models.SpinEntry, ["min_order_total"]),
            (store_models.SpinPrize, ["min_order_total"]),
            (store_models.SpinMilestone, ["min_order_total"]),
        ]

        total_updates = 0
        with transaction.atomic():
            for model, fields in model_specs:
                updated_count = 0
                batch = []
                for obj in model.objects.all().iterator():
                    changed = False
                    for field in fields:
                        value = getattr(obj, field, None)
                        if value is None:
                            continue
                        new_value = convert_value(value)
                        if new_value != value:
                            setattr(obj, field, new_value)
                            changed = True
                    if changed:
                        batch.append(obj)
                        updated_count += 1
                    if len(batch) >= batch_size:
                        if not dry_run:
                            model.objects.bulk_update(batch, fields)
                        batch = []
                if batch and not dry_run:
                    model.objects.bulk_update(batch, fields)
                total_updates += updated_count
                self.stdout.write(
                    f"{model.__name__}: {updated_count} rows updated"
                )

            if dry_run:
                self.stdout.write(self.style.WARNING("Dry run only; no changes saved."))

        self.stdout.write(
            self.style.SUCCESS(f"Done. Total rows updated: {total_updates}")
        )

