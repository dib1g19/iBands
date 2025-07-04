from django.contrib import admin
from store import models as store_models
from store.admin_forms import DuplicateProductForm


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
    list_display = ["title", "sku", "image", "parent"]
    list_editable = ["sku", "image", "parent"]
    prepopulated_fields = {"slug": ("title",)}


class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "category",
        "sku",
        "name",
        "image",
        "price",
        "regular_price",
        "stock",
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


class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_id",
        "customer",
        "total",
        "payment_status",
        "order_status",
        "payment_method",
        "date",
    ]
    list_editable = ["payment_status", "order_status", "payment_method"]
    search_fields = ["order_id", "customer__username"]
    list_filter = ["payment_status", "order_status"]


class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["item_id", "order", "product", "qty", "price", "sub_total"]
    search_fields = ["item_id", "order__order_id", "product__name"]
    list_filter = ["order__date"]


class ReviewAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "rating", "active", "date"]
    search_fields = ["user__username", "product__name"]
    list_filter = ["active", "rating"]


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
