from decimal import Decimal

from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, RelatedFieldWidgetWrapper
from django.db import models
from django.db.models import Prefetch
from django import forms
from django.http import HttpResponseRedirect
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from ibands_site.admin import iBandsModelAdmin
from store import models as store_models
from store.admin_forms import DuplicateProductForm
from store.admin_helpers import order_product_label, product_path_label
from itertools import product as cartesian_product


class ColorSwatchMixin:
    @admin.display(description="Цвят")
    def color_swatch(self, obj):
        return format_html(
            '<span style="display:inline-block;width:32px;height:32px;border-radius:50%;background:{};border:1px solid #bbb;box-shadow:0 1px 4px rgba(0,0,0,0.08);"></span>',
            obj.hex_code or "#fff"
        )


class MultiFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultiFileInput(attrs={"multiple": True, "accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        return [super().clean(item, initial) for item in data if item]


class ProductAdminForm(forms.ModelForm):
    extra_images = MultiFileField(
        required=False,
        label="Extra photos",
        help_text="Може да се изберат няколко файла наведнъж. Първият получава най-малката позиция, която е втора снимка и при задържане. В таб Gallerys могат да се редактират и преподреждат.",
    )

    class Meta:
        model = store_models.Product
        fields = "__all__"


def add_gallery_uploads(product, files):
    if not files:
        return
    last = product.gallery_images.order_by("-position").values_list("position", flat=True).first()
    start = 0 if last is None else last + 1
    for offset, uploaded in enumerate(files):
        store_models.Gallery.objects.create(
            product=product,
            image=uploaded,
            position=start + offset,
        )


class GalleryInline(admin.TabularInline):
    model = store_models.Gallery
    extra = 0
    fields = ["image", "position"]


@admin.register(store_models.Product)
class ProductAdmin(iBandsModelAdmin):
    list_display = ["category", "sku", "name", "view_on_site_link", "image", "price", "sale_price", "on_sale", "featured", "promo_type", "promo_buy_qty", "promo_get_qty"]
    list_editable = ["sku", "name", "image", "price", "sale_price", "on_sale", "featured", "promo_type", "promo_buy_qty", "promo_get_qty"]
    list_filter = ["status", "featured", "on_sale", "promo_type", "category"]
    search_fields = ["name", "sku", "category__title"]
    list_select_related = ["category", "category__parent", "category__parent__parent"]
    readonly_fields = ["view_on_site_link"]

    form = ProductAdminForm
    inlines = [GalleryInline]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["additional_categories", "variants", "colors", "model_groups"]

    fieldsets = (
        (None, {
            "fields": ("view_on_site_link", "category", "sku", "name", "slug", "image", "extra_images", "description", "price", "sale_price", "stock", "shipping", "on_sale", "featured", "is_mystery_box", "status", "date")
        }),
        ("Promotion", {
            "fields": ("promo_type", "promo_buy_qty", "promo_get_qty", "promo_label_override"),
        }),
        ("SEO", {
            "fields": ("h1_override", "meta_description",)
        }),
        ("Relations", {
            "fields": ("additional_categories", "variants", "colors", "size_group", "model_groups")
        }),
    )
    
    action_form = DuplicateProductForm
    actions = ["duplicate_product", "generate_product_items_from_groups"]

    def _storefront_path(self, obj):
        if not obj or not obj.pk or not obj.category_id or not obj.slug:
            return None
        try:
            return obj.get_absolute_url()
        except Exception:
            return None

    def view_on_site(self, obj):
        return self._storefront_path(obj)

    @admin.display(description="Site")
    def view_on_site_link(self, obj):
        url = self._storefront_path(obj)
        if not url:
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">View</a>',
            url,
        )

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

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        add_gallery_uploads(form.instance, form.cleaned_data.get("extra_images"))

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
    list_display = ["title", "view_on_site_link", "sku", "marketing_image", "hover_image", "is_popular", "parent"]
    list_editable = ["sku", "marketing_image", "hover_image", "is_popular"]
    list_filter = ["parent", "is_popular"]
    search_fields = ["title", "sku"]
    list_select_related = ["parent", "parent__parent"]
    readonly_fields = ["view_on_site_link"]
    fields = (
        "view_on_site_link",
        "title",
        "description",
        "sku",
        "parent",
        "marketing_image",
        "hover_image",
        "show_banner",
        "slug",
        "meta_title",
        "meta_description",
        "is_popular",
    )

    prepopulated_fields = {"slug": ("title",)}

    class Media:
        js = ('assets/js/admin_char_count.js',)

    def _storefront_path(self, obj):
        if not obj or not obj.pk or not obj.slug:
            return None
        try:
            return obj.get_absolute_url()
        except Exception:
            return None

    def view_on_site(self, obj):
        return self._storefront_path(obj)

    @admin.display(description="Site")
    def view_on_site_link(self, obj):
        url = self._storefront_path(obj)
        if not url:
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">View</a>',
            url,
        )


@admin.register(store_models.CategoryLink)
class CategoryLinkAdmin(iBandsModelAdmin):
    list_display = ["parent", "child"]
    list_select_related = ["parent", "child"]
    search_fields = ["parent__title", "child__title", "parent__sku", "child__sku"]


@admin.register(store_models.Cart)
class CartAdmin(iBandsModelAdmin):
    list_display = ["cart_id", "product_path", "model", "size", "qty", "price", "sub_total", "user", "date"]
    list_filter = ["date"]
    search_fields = ["cart_id", "product__name", "user__username"]
    list_select_related = ["user", "product__category__parent__parent"]

    @admin.display(description="Product")
    def product_path(self, obj):
        return product_path_label(obj.product, link=True)


class CachedProductAutocompleteSelect(AutocompleteSelect):
    """Use the product already loaded on the order line."""

    cached_obj = None

    def optgroups(self, name, value, attr=None):
        cached = self.cached_obj
        selected_choices = {
            str(v) for v in value if str(v) not in self.choices.field.empty_values
        }
        if cached is not None and selected_choices == {str(cached.pk)}:
            label = self.choices.field.label_from_instance(cached)
            option = self.create_option(name, cached.pk, label, selected_choices, 0)
            return [(None, [option], 0)]
        return super().optgroups(name, value, attr)

    def render(self, name, value, attrs=None, renderer=None):
        rendered = super().render(name, value, attrs, renderer)
        if self.cached_obj is None:
            return rendered
        return format_html(
            '<div class="order-line-product">{}{}</div>',
            order_product_label(self.cached_obj, link=True),
            rendered,
        )


class OrderItemInlineForm(forms.ModelForm):
    class Meta:
        model = store_models.OrderItem
        fields = ("product", "model", "size", "qty", "price", "sub_total")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        product_field = self.fields.get("product")
        widget = getattr(product_field, "widget", None)
        if not isinstance(widget, CachedProductAutocompleteSelect):
            return
        if not getattr(self.instance, "product_id", None):
            return
        try:
            widget.cached_obj = self.instance._meta.get_field("product").get_cached_value(self.instance)
        except KeyError:
            return

    def save(self, commit=True):
        changed = set(self.changed_data)
        instance = super().save(commit=False)
        if instance.product_id and "product" in changed and "price" not in changed:
            instance.price = Decimal(str(instance.product.effective_price or 0))
        if "sub_total" not in changed and changed.intersection({"product", "price", "qty"}):
            instance.sub_total = Decimal(str(instance.price or 0)) * Decimal(instance.qty or 0)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class OrderItemInline(admin.TabularInline):
    model = store_models.OrderItem
    form = OrderItemInlineForm
    fields = OrderItemInlineForm.Meta.fields
    autocomplete_fields = ["product"]
    extra = 0

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "product":
            kwargs["widget"] = CachedProductAutocompleteSelect(
                db_field, self.admin_site, using=kwargs.get("using")
            )
        elif db_field.name in ("model", "size"):
            kwargs["widget"] = forms.Textarea(attrs={"rows": 2})
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if isinstance(getattr(formfield, "widget", None), RelatedFieldWidgetWrapper):
            formfield.widget = formfield.widget.widget
        return formfield


@admin.register(store_models.Order)
class OrderAdmin(iBandsModelAdmin):
    list_display = ["order_id", "items_summary", "recipient_name", "total", "order_status", "shipping_service", "tracking_id", "date"]
    list_editable = [ "order_status", "shipping_service", "tracking_id"]
    list_filter = ["payment_status", "order_status"]
    search_fields = ["order_id", "customer__username", "customer__email", "order_items__product__name", "order_items__product__sku"]
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
                "<b>Лице за контакт:</b> {}<br>"
                "<b>Телефон:</b> {}<br>"
                "<b>Email:</b> {}<br>"
                "<b>Доставка:</b> {}<br>"
                "<b>Населено място:</b> {}<br>"
                "<b>Адрес:</b> {}",
                addr.name or "-",
                addr.face or "-",
                addr.phone or "-",
                addr.email or "-",
                addr.get_delivery_method_display() if hasattr(addr, "get_delivery_method_display") else addr.delivery_method or "-",
                addr.city or "-",
                address
            )
        return "-"
    address_display.short_description = "Address"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        match = getattr(request, "resolver_match", None)
        if match and match.url_name == "store_order_changelist":
            qs = qs.prefetch_related(
                Prefetch(
                    "order_items",
                    queryset=store_models.OrderItem.objects.select_related("product"),
                )
            )
        return qs

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        items_changed = any(
            formset.model is store_models.OrderItem
            and (formset.new_objects or formset.changed_objects or formset.deleted_objects)
            for formset in formsets
        )
        if items_changed:
            form.instance.refresh_totals_from_items()

    @admin.display(description="Name")
    def recipient_name(self, obj):
        address = obj.address
        if address is None:
            return "-"
        name = (address.name or "").strip()
        phone = (address.phone or "").strip()
        if name and phone:
            return format_html(
                '{}<br><span class="order-product-meta">{}</span>',
                name,
                phone,
            )
        return name or phone or "-"

    @admin.display(description="Items")
    def items_summary(self, obj):
        lines = []
        for item in obj.order_items.all():
            variant = " ".join(part for part in (item.model or "", item.size or "") if part)
            qty = f"×{item.qty}" if item.qty else ""
            extra = " ".join(part for part in (variant, qty) if part)
            lines.append((order_product_label(item.product, link=True), extra))
        if not lines:
            return "-"
        return format_html_join(
            mark_safe("<br>"),
            '{} <span class="order-product-meta">{}</span>',
            lines,
        )


@admin.register(store_models.OrderItem)
class OrderItemAdmin(iBandsModelAdmin):
    list_display = ["order", "product_label", "model", "size" ,"qty", "price", "sub_total", "note"]
    list_filter = ["order__date"]
    search_fields = ["order__order_id", "product__name", "product__sku"]
    list_select_related = ["order", "product"]

    @admin.display(description="Product")
    def product_label(self, obj):
        return order_product_label(obj.product, link=True)


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
    list_display = ["product", "position", "gallery_id"]
    list_editable = ["position"]
    search_fields = ["product__name", "gallery_id"]
    list_select_related = ["product"]


@admin.register(store_models.Coupon)
class CouponAdmin(iBandsModelAdmin):
    list_display = [
        "code",
        "discount",
        "active",
        "min_subtotal",
        "usage_limit",
        "per_customer_limit",
        "valid_from",
        "valid_until",
        "owner",
        "redemption_count",
    ]
    list_filter = ["active"]
    search_fields = ["code", "owner__email"]
    autocomplete_fields = ["owner"]
    list_select_related = ["owner"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_redemptions=models.Count("redemptions"))

    @admin.display(description="Redeemed")
    def redemption_count(self, obj):
        return obj._redemptions


@admin.register(store_models.CouponRedemption)
class CouponRedemptionAdmin(iBandsModelAdmin):
    list_display = ["coupon", "order", "user", "created_at"]
    search_fields = ["coupon__code", "order__order_id", "user__email"]
    list_select_related = ["coupon", "order", "user"]


@admin.register(store_models.SpinEntry)
class SpinEntryAdmin(iBandsModelAdmin):
    list_display = ["user", "date", "result_label", "prize_type", "coupon_discount_percent", "min_order_total", "free_shipping", "redeemed_order", "created_at"]
    list_filter = ["date", "prize_type"]
    search_fields = ["user__email", "result_label"]


@admin.register(store_models.SpinPrize)
class SpinPrizeAdmin(iBandsModelAdmin):
    list_display = ["label", "prize_type", "discount_percent", "min_order_total", "weight", "active", "sort_order", "color"]
    list_editable = ["weight", "active", "sort_order", "color", "discount_percent", "min_order_total"]
    list_filter = ["prize_type", "active"]
    search_fields = ["label"]


@admin.register(store_models.SpinMilestone)
class SpinMilestoneAdmin(iBandsModelAdmin):
    list_display = ["threshold_spins", "label", "prize_type", "discount_percent", "min_order_total", "active"]
    list_editable = ["label", "prize_type", "discount_percent", "min_order_total", "active"]
    list_filter = ["active", "prize_type"]
    search_fields = ["label"]


@admin.register(store_models.SpinMilestoneAward)
class SpinMilestoneAwardAdmin(iBandsModelAdmin):
    list_display = ["user", "milestone", "coupon_code", "redeemed_order", "awarded_at"]
    list_filter = ["awarded_at", "milestone__threshold_spins"]
    search_fields = ["user__email", "coupon_code", "milestone__label"]


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


@admin.register(store_models.StaffUpdate)
class StaffUpdateAdmin(iBandsModelAdmin):
    list_display = ["summary", "created_by", "created_at"]
    search_fields = ["summary", "details", "created_by__email"]
    list_select_related = ["created_by"]
    readonly_fields = ["created_by", "created_at"]

    def get_fields(self, request, obj=None):
        if obj:
            return ["summary", "details", "created_by", "created_at"]
        return ["summary", "details"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(store_models.StoreThemeSettings)
class StoreThemeSettingsAdmin(iBandsModelAdmin):
    list_display = ["active_campaign"]
    radio_fields = {"active_campaign": admin.VERTICAL}

    def has_add_permission(self, request):
        # Allow adding only if no settings row exists
        exists = store_models.StoreThemeSettings.objects.exists()
        return not exists

    def changelist_view(self, request, extra_context=None):
        # Redirect the changelist to the single settings object's change form for convenience
        obj = store_models.StoreThemeSettings.objects.first()
        if obj:
            return HttpResponseRedirect(f"./{obj.pk}/change/")
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(store_models.BandOfTheWeek)
class BandOfTheWeekAdmin(iBandsModelAdmin):
    list_display = ["week_start", "product_path"]
    list_filter = ["week_start"]
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
    list_display = ["name", "sort_order", "generate_as_single_sku"]
    list_editable = ["sort_order", "generate_as_single_sku"]
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


@admin.register(store_models.ServerErrorLog)
class ServerErrorLogAdmin(iBandsModelAdmin):
    list_display = ["created_at", "exception_type", "short_message", "path", "user_label", "is_staff", "is_bot"]
    list_filter = ["is_staff", "is_bot", "exception_type", "created_at"]
    search_fields = ["exception_type", "message", "path", "user_label", "user__email"]
    date_hierarchy = "created_at"
    list_select_related = ["user"]
    readonly_fields = [
        "created_at", "exception_type", "message", "traceback_display", "method", "path",
        "query_string", "user", "user_label", "is_staff", "is_bot", "ip_address", "user_agent",
    ]
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    @admin.display(description="Message")
    def short_message(self, obj):
        text = obj.message or ""
        return text if len(text) <= 80 else f"{text[:77]}..."

    @admin.display(description="Traceback")
    def traceback_display(self, obj):
        return format_html("<pre style='white-space:pre-wrap;margin:0'>{}</pre>", obj.traceback or "")
