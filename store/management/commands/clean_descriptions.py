import re
from django.core.management.base import BaseCommand
from store.models import Product


class Command(BaseCommand):
    help = "Keep only <strong> tags and plain text in product descriptions"

    def handle(self, *args, **options):
        products = Product.objects.all()
        count = 0
        for product in products:
            original = product.description

            # Remove all tags except <strong>
            # Replace all <strong ...> with <strong>
            cleaned = re.sub(r"<strong[^>]*>", "<strong>", original)
            # Remove all tags except <strong> and </strong>
            cleaned = re.sub(r"<(?!/?strong\b)[^>]+>", "", cleaned)
            # Remove MS Office tags (like <o:p>)
            cleaned = re.sub(r"<o:p>.*?</o:p>", "", cleaned, flags=re.DOTALL)
            # Clean up excessive spaces
            cleaned = re.sub(r"\s{2,}", " ", cleaned)

            if cleaned != original:
                product.description = cleaned
                product.save()
                count += 1
                self.stdout.write(self.style.SUCCESS(f"Cleaned: {product.name}"))
        self.stdout.write(
            self.style.SUCCESS(f"Done. Cleaned {count} product descriptions.")
        )
