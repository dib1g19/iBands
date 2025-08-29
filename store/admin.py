from django.contrib import admin
from django.db import models
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from ibands_site.admin import iBandsModelAdmin
from store import models as store_models
from store.admin_forms import DuplicateProductForm
from store.admin_helpers import product_path_label
from itertools import product as cartesian_product


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
    list_display = ["category", "sku", "name", "image", "price", "sale_price", "on_sale", "featured"]
    list_editable = ["sku", "name", "image", "price", "sale_price", "on_sale", "featured"]
    list_filter = ["status", "featured", "on_sale", "category"]
    search_fields = ["name", "category__title"]
    list_select_related = ["category"]

    inlines = [GalleryInline]
    prepopulated_fields = {"slug": ("name",)}
    
    action_form = DuplicateProductForm
    actions = ["duplicate_product", "generate_product_items_from_groups"]

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
                    sale_price=product.sale_price,
                    featured=product.featured,
                    status=product.status,
                )
                new_product.save()
                new_product.variants.set(product.variants.all())
                count += 1

        self.message_user(request, f"{count} product copies created successfully.")

    duplicate_product.short_description = "Duplicate selected Products"

    def generate_product_items_from_groups(self, request, queryset):
        created_total = 0
        for product in queryset.prefetch_related("model_groups__device_models", "size_group__sizes"):
            sizes_qs = getattr(product.size_group, "sizes", None)
            sizes = list(sizes_qs.all()) if sizes_qs else []

            # Separate model groups that should collapse into a single SKU per size
            collapsing_groups = [mg for mg in product.model_groups.all() if getattr(mg, "generate_as_single_sku", False)]
            regular_groups = [mg for mg in product.model_groups.all() if not getattr(mg, "generate_as_single_sku", False)]

            # Regular models → individual SKU per (size, model)
            regular_models = set()
            for mg in regular_groups:
                regular_models.update(list(mg.device_models.all()))
            regular_models = list(regular_models)

            # Collapsing models → attach all models of that group to the same SKU per size
            collapsing_models_by_group = {mg.id: list(mg.device_models.all()) for mg in collapsing_groups}

            # Create one SKU per unique (size, model) combination for regular models
            if sizes and regular_models:
                for size_obj, model_obj in cartesian_product(sizes, regular_models):
                    existing = (
                        store_models.ProductItem.objects
                        .filter(product=product, size=size_obj, device_models=model_obj)
                        .first()
                    )
                    if existing:
                        continue
                    sku_obj = store_models.ProductItem.objects.create(product=product, size=size_obj)
                    sku_obj.device_models.add(model_obj)
                    created_total += 1
                # continue processing collapsing groups below

            # Only sizes defined and no regular models → create one SKU per size (no model)
            if sizes:
                if not regular_models and not collapsing_groups:
                    for size_obj in sizes:
                        _, created = store_models.ProductItem.objects.get_or_create(product=product, size=size_obj)
                        if created:
                            created_total += 1

            # Only models defined (no sizes): regular models → one SKU per model with size=None
            if not sizes and regular_models:
                for model_obj in regular_models:
                    existing = (
                        store_models.ProductItem.objects
                        .filter(product=product, size=None, device_models=model_obj)
                        .first()
                    )
                    if existing:
                        continue
                    sku_obj = store_models.ProductItem.objects.create(product=product, size=None)
                    sku_obj.device_models.add(model_obj)
                    created_total += 1

            # Handle collapsing groups: per size, one SKU attaching all models in that group
            if sizes and collapsing_groups:
                for size_obj in sizes:
                    for mg in collapsing_groups:
                        models_in_group = collapsing_models_by_group.get(mg.id, [])
                        if not models_in_group:
                            continue
                        # If any SKU already exists with this size and any of these models, skip creating new one
                        existing = (
                            store_models.ProductItem.objects
                            .filter(product=product, size=size_obj, device_models__in=models_in_group)
                            .distinct()
                            .first()
                        )
                        if existing:
                            # Ensure it has all models in the group
                            existing.device_models.add(*models_in_group)
                            continue
                        sku_obj = store_models.ProductItem.objects.create(product=product, size=size_obj)
                        sku_obj.device_models.add(*models_in_group)
                        created_total += 1

            # Collapsing groups without sizes → one SKU per group with size=None
            if not sizes and collapsing_groups:
                for mg in collapsing_groups:
                    models_in_group = collapsing_models_by_group.get(mg.id, [])
                    if not models_in_group:
                        continue
                    existing = (
                        store_models.ProductItem.objects
                        .filter(product=product, size=None, device_models__in=models_in_group)
                        .distinct()
                        .first()
                    )
                    if existing:
                        existing.device_models.add(*models_in_group)
                        continue
                    sku_obj = store_models.ProductItem.objects.create(product=product, size=None)
                    sku_obj.device_models.add(*models_in_group)
                    created_total += 1

        self.message_user(request, f"Generated {created_total} ProductItem rows.")

    generate_product_items_from_groups.short_description = "Generate SKUs from size/model groups"

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


@admin.register(store_models.BandOfTheDay)
class BandOfTheDayAdmin(iBandsModelAdmin):
    list_display = ["date", "product_path"]
    list_filter = ["date"]
    search_fields = ["product__name", "product__sku"]
    list_select_related = ["product__category__parent__parent"]
    

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "product":
            kwargs["queryset"] = store_models.Product.objects.select_related(
                "category", "category__parent", "category__parent__parent"
            )
            formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)

            def label_from_instance(obj):
                try:
                    category_path = obj.category.get_full_name_path()
                except Exception:
                    category_path = getattr(obj.category, "title", "")
                return f"{category_path} — {obj.name}"

            formfield.label_from_instance = label_from_instance
            return formfield
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Product")
    def product_path(self, obj):
        return product_path_label(obj.product, link=True)


# -----------------------------
# New admin registrations for SKU refactor
# -----------------------------


class ProductItemInline(admin.TabularInline):
    model = store_models.ProductItem
    extra = 0
    fields = ["sku", "quantity", "price_delta", "device_models", "size"]
    autocomplete_fields = ["size", "device_models"]


# Extend Product admin to include ProductItem inline
ProductAdmin.inlines = [GalleryInline, ProductItemInline]


@admin.register(store_models.DeviceModel)
class DeviceModelAdmin(iBandsModelAdmin):
    list_display = ["name", "sort_order"]
    list_editable = ["sort_order"]
    search_fields = ["name"]


@admin.register(store_models.Size)
class SizeAdmin(iBandsModelAdmin):
    list_display = ["name", "sort_order"]
    list_editable = ["sort_order"]
    search_fields = ["name"]


@admin.register(store_models.SizeGroup)
class SizeGroupAdmin(iBandsModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    filter_horizontal = ["sizes"]


@admin.register(store_models.ModelGroup)
class ModelGroupAdmin(iBandsModelAdmin):
    list_display = ["name", "generate_as_single_sku"]
    list_editable = ["generate_as_single_sku"]
    search_fields = ["name"]
    filter_horizontal = ["device_models"]


@admin.register(store_models.ProductItem)
class ProductItemAdmin(iBandsModelAdmin):
    list_display = ["product", "size", "device_models_display", "quantity", "sku", "price_delta"]
    list_editable = ["quantity", "sku", "price_delta"]
    list_filter = ["product", "size"]
    search_fields = ["product__name", "product__sku"]
    list_select_related = ["product", "size"]
    autocomplete_fields = ["product", "size", "device_models"]

    @admin.display(description="Device models")
    def device_models_display(self, obj):
        names = [dm.name for dm in obj.device_models.all()]
        return ", ".join(names) if names else "-"
