from django.contrib import admin
from django.db import models
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from ibands_site.middleware import RequestCounterMiddleware
from store import models as store_models
from store.admin_forms import DuplicateProductForm
from store.utils import get_500_error_stats


class CategoryAdmin(admin.ModelAdmin):
    list_display = ["title", "sku", "image", "marketing_image", "hover_image", "is_popular", "parent"]
    list_per_page = 20
    list_editable = ["sku", "image", "marketing_image", "hover_image", "is_popular", "parent"]
    search_fields = ["title", "sku"]
    prepopulated_fields = {"slug": ("title",)}

    class Media:
        js = ('admin/js/vendor/jquery/jquery.js', 'assets/js/admin_char_count.js',)


class GalleryInline(admin.TabularInline):
    model = store_models.Gallery
    extra = 1


class VariantInline(admin.TabularInline):
    model = store_models.Product.variants.through
    extra = 1


class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "category",
        "sku",
        "name",
        "description",
        "meta_description",
        "image",
        "price",
        "regular_price",
        "featured",
    ]
    list_per_page = 20
    list_editable = ["sku", "name", "description", "meta_description", "image", "price", "regular_price", "featured"]
    search_fields = ["name", "category__title"]
    list_filter = ["status", "featured", "category"]
    inlines = [GalleryInline, VariantInline]
    prepopulated_fields = {"slug": ("name",)}

    action_form = DuplicateProductForm
    actions = ["duplicate_product"]

    def duplicate_product(self, request, queryset):
        number = int(request.POST.get("number_of_copies", 1))
        count = 0

        for product in queryset:
            for i in range(number):
                new_product = store_models.Product.objects.get(pk=product.pk)
                new_product.id = None
                new_product.name = f"{product.name} (Copy {i+1})"
                new_product.slug = None
                new_product.sku = f"{product.sku}-copy-{i+1}-{count}"
                new_product.save()
                new_product.variants.set(product.variants.all())
                count += 1

        self.message_user(request, f"{count} product copies created successfully.")

    duplicate_product.short_description = "Duplicate selected Products"

    class Media:
        js = ('admin/js/vendor/jquery/jquery.js', 'assets/js/admin_char_count.js',)


class VariantItemInline(admin.TabularInline):
    model = store_models.VariantItem
    extra = 1


class VariantAdmin(admin.ModelAdmin):
    list_display = ["name", "variant_type", "get_products"]
    list_per_page = 20
    search_fields = ["products__name", "name"]
    list_filter = ["variant_type"]
    inlines = [VariantItemInline]

    def get_products(self, obj):
        products = [
            format_html(
                '<a href="{}">{}</a>',
                reverse("admin:store_product_change", args=[product.pk]),
                str(product)
            )
            for product in obj.products.all()
        ]
        return format_html("<br>".join(products))
    get_products.short_description = "Products"


class VariantItemAdmin(admin.ModelAdmin):
    list_display = ["variant", "title", "content"]
    search_fields = ["variant__name", "title"]


class GalleryAdmin(admin.ModelAdmin):
    list_display = ["product", "gallery_id"]
    search_fields = ["product__name", "gallery_id"]


class CartAdmin(admin.ModelAdmin):
    list_display = ["cart_id", "product", "user", "qty", "price", "sub_total", "date"]
    search_fields = ["cart_id", "product__name", "user__username"]
    list_filter = ["date", "product"]


class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "discount"]
    search_fields = ["code"]


class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "product", "qty", "price", "sub_total"]
    search_fields = ["id", "order__order_id", "product__name"]
    list_filter = ["order__date"]


class OrderItemInline(admin.TabularInline):
    model = store_models.OrderItem
    extra = 0
    fields = ["product", "model", "size", "qty", "price", "sub_total"]
    readonly_fields = ["product", "model", "size", "qty", "price", "sub_total"]


class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "address",
        "total",
        "order_status",
        "shipping_service",
        "tracking_id",
        "payment_method",
        "date",
    ]
    list_editable = [
        "order_status",
        "shipping_service",
        "tracking_id",
    ]
    search_fields = ["order_id", "customer__username"]
    list_filter = ["payment_status", "order_status"]
    inlines = [OrderItemInline]
    readonly_fields = [
        "address_display",
    ]
    fields = [
        "customer",
        "address_display",
        "order_status",
        "shipping_service",
        "tracking_id",
        "total",
        "sub_total",
        "shipping",
        "saved",
        "payment_status",
        "payment_method",
        "coupons",
        "order_id",
        "payment_id",
        "date",
    ]

    def address_display(self, obj):
        if obj.address:
            addr = obj.address
            address = None
            if getattr(addr, "office_name", None):
                address = addr.office_name
            elif getattr(addr, "address", None):
                address = addr.address
            if not address:
                address = "-"
            return format_html(
                "<b>Име:</b> {}<br>"
                "<b>Телефон:</b> {}<br>"
                "<b>Email:</b> {}<br>"
                "<b>Доставка:</b> {}<br>"
                "<b>Град:</b> {}<br>"
                "<b>Адрес:</b> {}",
                addr.name or "-",
                addr.phone or "-",
                addr.email or "-",
                addr.get_delivery_method_display() if hasattr(addr, "get_delivery_method_display") else addr.delivery_method or "-",
                addr.city or "-",
                address
            )
        return "-"
    address_display.short_description = "Address"


class ReviewAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "rating", "active", "date"]
    search_fields = ["user__username", "product__name"]
    list_filter = ["active", "rating"]


class StatsAdmin(admin.ModelAdmin):
    # Redirect the changelist view (default admin page for this model) to the stats view.
    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse('admin:stats'))

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('stats/', self.admin_site.admin_view(self.stats_view), name='stats'),
        ]
        return custom_urls + urls

    def stats_view(self, request):
        stats = {
            "user_request_count": RequestCounterMiddleware.get_user_request_count(),
            "user_request_unique_count": RequestCounterMiddleware.get_user_request_unique_count(),
            "bot_request_count": RequestCounterMiddleware.get_bot_request_count(),
            "bot_request_unique_count": RequestCounterMiddleware.get_bot_request_unique_count(),
        }
        stats.update(get_500_error_stats())
        context = dict(
            self.admin_site.each_context(request),
            stats=stats,
        )
        return TemplateResponse(request, "admin/stats.html", context)


class Stats(models.Model):
    class Meta:
        verbose_name = "Stats"
        verbose_name_plural = "Stats"
        managed = False  # No DB table


class ColorGroupAdmin(admin.ModelAdmin):
    list_display = ["name_en", "name_bg", "hex_code"]
    list_editable = ["name_bg", "hex_code"]


class ColorAdmin(admin.ModelAdmin):
    list_display = ["group", "name_en", "name_bg"]
    list_editable = ["name_en", "name_bg"]


admin.site.register(store_models.Category, CategoryAdmin)
admin.site.register(store_models.Product, ProductAdmin)
admin.site.register(store_models.Variant, VariantAdmin)
admin.site.register(store_models.VariantItem, VariantItemAdmin)
admin.site.register(store_models.Gallery, GalleryAdmin)
admin.site.register(store_models.Cart, CartAdmin)
admin.site.register(store_models.Coupon, CouponAdmin)
admin.site.register(store_models.Order, OrderAdmin)
admin.site.register(store_models.OrderItem, OrderItemAdmin)
admin.site.register(store_models.Review, ReviewAdmin)
admin.site.register(Stats, StatsAdmin)
admin.site.register(store_models.Color, ColorAdmin)
admin.site.register(store_models.ColorGroup, ColorGroupAdmin)
