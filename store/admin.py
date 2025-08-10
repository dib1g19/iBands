from django.contrib import admin
from django.db import models
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from ibands_site.admin import iBandsModelAdmin
from store import models as store_models
from store.admin_forms import DuplicateProductForm
from store.admin_helpers import product_path_label


class ColorSwatchMixin:
    @admin.display(description="Цвят")
    def color_swatch(self, obj):
        return format_html(
            '<span style="display:inline-block;width:32px;height:32px;border-radius:50%;background:{};border:1px solid #bbb;box-shadow:0 1px 4px rgba(0,0,0,0.08);"></span>',
            obj.hex_code or "#fff"
        )


class GalleryInline(admin.TabularInline):
    model = store_models.Gallery
    extra = 0


@admin.register(store_models.Product)
class ProductAdmin(iBandsModelAdmin):
    list_display = ["category", "sku", "name", "image", "price", "regular_price", "featured"]
    list_editable = ["sku", "name", "image", "price", "regular_price", "featured"]
    list_filter = ["status", "featured", "category"]
    search_fields = ["name", "category__title"]
    list_select_related = ["category"]

    inlines = [GalleryInline]
    prepopulated_fields = {"slug": ("name",)}
    
    action_form = DuplicateProductForm
    actions = ["duplicate_product"]

    def duplicate_product(self, request, queryset):
        number = int(request.POST.get("number_of_copies", 1))
        qs = queryset.select_related("category").prefetch_related("variants")
        count = 0

        for product in qs:
            for i in range(number):
                new_product = store_models.Product(
                    category=product.category,
                    sku=f"{product.sku}-copy-{i+1}-{count}",
                    name=f"{product.name} (Copy {i+1})",
                    description=product.description,
                    meta_description=product.meta_description,
                    image=product.image,
                    price=product.price,
                    regular_price=product.regular_price,
                    featured=product.featured,
                    status=product.status,
                )
                new_product.save()
                new_product.variants.set(product.variants.all())
                count += 1

        self.message_user(request, f"{count} product copies created successfully.")

    duplicate_product.short_description = "Duplicate selected Products"

    class Media:
        js = ('assets/js/admin_char_count.js',)


@admin.register(store_models.Category)
class CategoryAdmin(iBandsModelAdmin):
    list_display = ["title", "sku", "image", "marketing_image", "hover_image", "is_popular", "parent"]
    list_editable = ["sku", "image", "marketing_image", "hover_image", "is_popular"]
    list_filter = ["parent"]
    search_fields = ["title", "sku"]
    list_select_related = ["parent"]

    prepopulated_fields = {"slug": ("title",)}

    class Media:
        js = ('assets/js/admin_char_count.js',)


@admin.register(store_models.Cart)
class CartAdmin(iBandsModelAdmin):
    list_display = ["cart_id", "product_path", "model", "size", "qty", "price", "sub_total", "user", "date"]
    list_filter = ["date"]
    search_fields = ["cart_id", "product__name", "user__username"]
    list_select_related = ["user", "product__category__parent__parent"]

    @admin.display(description="Product")
    def product_path(self, obj):
        return product_path_label(obj.product, link=True)


class OrderItemInline(admin.TabularInline):
    model = store_models.OrderItem
    fields = ["product_path", "model", "size", "qty", "price", "sub_total"]
    readonly_fields = fields
    extra = 0

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("product__category__parent__parent")
        )
        
    @admin.display(description="Product")
    def product_path(self, obj):
        return product_path_label(obj.product, link=True)


@admin.register(store_models.Order)
class OrderAdmin(iBandsModelAdmin):
    list_display = ["address", "total", "order_status", "shipping_service", "tracking_id", "payment_method", "date"]
    list_editable = [ "order_status", "shipping_service", "tracking_id"]
    list_filter = ["payment_status", "order_status"]
    search_fields = ["order_id", "customer__username"]
    list_select_related = ["address"]

    inlines = [OrderItemInline]
    readonly_fields = ["address_display",]
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


@admin.register(store_models.OrderItem)
class OrderItemAdmin(iBandsModelAdmin):
    list_display = ["order", "product_path", "model", "size" ,"qty", "price", "sub_total"]
    list_filter = ["order__date"]
    search_fields = ["order__order_id", "product__name"]
    list_select_related = ["order", "product__category__parent__parent"]

    @admin.display(description="Product")
    def product_path(self, obj):
        return product_path_label(obj.product, link=True)


class VariantItemInline(admin.TabularInline):
    model = store_models.VariantItem
    extra = 0


@admin.register(store_models.Variant)
class VariantAdmin(iBandsModelAdmin):
    list_display = ["name", "variant_type", "products_path"]
    list_filter = ["variant_type"]
    search_fields = ["products__name", "name"]
    inlines = [VariantItemInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("products__category__parent__parent")
        )

    @admin.display(description="Products")
    def products_path(self, obj):
        return format_html("<br>".join(
            product_path_label(product, link=True) 
            for product in obj.products.all()
        ))


@admin.register(store_models.VariantItem)
class VariantItemAdmin(iBandsModelAdmin):
    list_display = ["variant", "title", "content"]
    search_fields = ["variant__name", "title"]


@admin.register(store_models.Gallery)
class GalleryAdmin(iBandsModelAdmin):
    list_display = ["product", "gallery_id"]
    search_fields = ["product__name", "gallery_id"]
    list_select_related = ["product"]


@admin.register(store_models.Coupon)
class CouponAdmin(iBandsModelAdmin):
    list_display = ["code", "discount"]
    search_fields = ["code"]


@admin.register(store_models.Review)
class ReviewAdmin(iBandsModelAdmin):
    list_display = ["user", "product", "rating", "active", "date"]
    search_fields = ["user__username", "product__name"]
    list_filter = ["active", "rating"]


@admin.register(store_models.ColorGroup)
class ColorGroupAdmin(ColorSwatchMixin, iBandsModelAdmin):
    list_display = ["name_en", "name_bg", "hex_code", "color_swatch"]
    list_editable = ["name_bg", "hex_code"]


@admin.register(store_models.Color)
class ColorAdmin(ColorSwatchMixin, iBandsModelAdmin):
    list_display = ["group", "name_en", "name_bg", "hex_code", "color_swatch"]
    list_editable = ["name_en", "name_bg", "hex_code"]
