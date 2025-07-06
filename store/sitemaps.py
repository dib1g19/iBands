from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Product, Category


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return Product.objects.filter(status="published")

    def location(self, obj):
        return obj.get_absolute_url()


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return Category.objects.all()

    def location(self, obj):
        return obj.get_absolute_url()


class StaticViewSitemap(Sitemap):
    def items(self):
        return [
            "store:index",
            "store:shop",
            "store:about",
            "store:contact",
            "store:faqs",
            "store:privacy_policy",
            "store:returns_and_exchanges",
            "store:terms_conditions",
        ]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        if item == "store:index":
            return 1.0
        if item == "store:shop":
            return 0.9
        return 0.5

    def changefreq(self, item):
        if item in ("store:index", "store:shop"):
            return "daily"
        return "yearly"