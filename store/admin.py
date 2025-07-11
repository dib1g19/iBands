from django.contrib import admin
from store import models as store_models
from store.admin_forms import DuplicateProductForm
from django.db import models
from ibands_site.middleware import OperationalErrorCounterMiddleware
from django.urls import path
from django.template.response import TemplateResponse
from django.http import HttpResponseRedirect
from django.urls import reverse


class GalleryInline(admin.TabularInline):
    model = store_models.Gallery
    extra = 1


class VariantInline(admin.TabularInline):
    model = store_models.Product.variants.through
    extra = 1


class VariantItemInline(admin.TabularInline):
    model = store_models.VariantItem
    extra = 1


class CategoryAdmin(admin.ModelAdmin):
    list_display = ["title", "sku", "image", "marketing_image", "hover_image", "is_popular", "parent"]
    list_editable = ["sku", "image", "marketing_image", "hover_image", "is_popular", "parent"]
    search_fields = ["title", "sku"]
    prepopulated_fields = {"slug": ("title",)}


class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "category",
        "sku",
        "name",
        "image",
        "price",
        "regular_price",
        "featured",
    ]
    list_editable = ["sku", "name", "image", "price", "regular_price", "featured"]
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


class VariantAdmin(admin.ModelAdmin):
    list_display = ["name", "variant_type", "get_products"]
    search_fields = ["products__name", "name"]
    inlines = [VariantItemInline]

    def get_products(self, obj):
        return ", ".join([product.name for product in obj.products.all()])

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


class OrderItemInline(admin.TabularInline):
    model = store_models.OrderItem
    extra = 0
    fields = ["product", "product_category_path", "model", "size", "qty", "price", "sub_total"]
    readonly_fields = ["product", "product_category_path", "model", "size", "qty", "price", "sub_total"]


from django.utils.html import format_html

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
            return format_html(
                "<b>Име:</b> {}<br>"
                "<b>Телефон:</b> {}<br>"
                "<b>Email:</b> {}<br>"
                "<b>Доставка:</b> {}<br>"
                "<b>Град:</b> {}<br>"
                "<b>Адрес:</b> {}",
                addr.full_name or "-",
                addr.mobile or "-",
                addr.email or "-",
                addr.get_delivery_method_display() if hasattr(addr, "get_delivery_method_display") else addr.delivery_method or "-",
                addr.city or "-",
                addr.address or "-"
            )
        return "-"
    address_display.short_description = "Address"


class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "product", "product_category_path", "qty", "price", "sub_total"]
    search_fields = ["id", "order__order_id", "product__name"]
    list_filter = ["order__date"]
    readonly_fields = ["product_category_path"]
    fields = [
        "order",
        "product",
        "product_category_path",
        "model",
        "size",
        "price",
        "sub_total",
    ]


class ReviewAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "rating", "active", "date"]
    search_fields = ["user__username", "product__name"]
    list_filter = ["active", "rating"]


class MiddlewareStatsAdmin(admin.ModelAdmin):
    # Redirect the changelist view (default admin page for this model) to the stats view.
    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse('admin:middleware_stats'))

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('stats/', self.admin_site.admin_view(self.stats_view), name='middleware_stats'),
        ]
        return custom_urls + urls

    def stats_view(self, request):
        stats = {
            "user_request_count": OperationalErrorCounterMiddleware.user_request_count,
            "user_request_unique_count": OperationalErrorCounterMiddleware.user_request_unique_count,
            "bot_request_count": OperationalErrorCounterMiddleware.bot_request_count,
            "bot_request_unique_count": OperationalErrorCounterMiddleware.bot_request_unique_count,
            "user_error_count": OperationalErrorCounterMiddleware.user_error_count,
            "user_error_unique_count": OperationalErrorCounterMiddleware.user_error_unique_count,
            "bot_error_count": OperationalErrorCounterMiddleware.bot_error_count,
            "bot_error_unique_count": OperationalErrorCounterMiddleware.bot_error_unique_count,
        }
        context = dict(
            self.admin_site.each_context(request),
            stats=stats,
        )
        return TemplateResponse(request, "admin/middleware_stats.html", context)

class MiddlewareStats(models.Model):
    class Meta:
        verbose_name = "Middleware Stats"
        verbose_name_plural = "Middleware Stats"
        managed = False  # No DB table

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
admin.site.register(MiddlewareStats, MiddlewareStatsAdmin)
