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
            "index",
            "shop",
            "about",
            "contact",
            "faqs",
            "privacy_policy",
            "returns_and_exchanges",
            "terms_conditions",
        ]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        if item == "index":
            return 1.0
        if item == "shop":
            return 0.9
        return 0.5

    def changefreq(self, item):
        if item in ("index", "shop"):
            return "daily"
        return "yearly"