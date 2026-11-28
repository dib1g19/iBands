from django.db import models
from django.core.cache import cache
from shortuuid.django_fields import ShortUUIDField
from django.utils import timezone
from slugify import slugify
from django_ckeditor_5.fields import CKEditor5Field
from userauths import models as user_models
from django.urls import reverse
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from ibands_site.images import convert_uploaded_images
from store.utils import floor_to_cent

STATUS = (
    ("published", "Published"),
    ("disabled", "Disabled"),
)

PAYMENT_STATUS = (
    ("processing", "Очаква потвърждение"),
    ("paid", "Платено"),
    ("failed", "Неуспешно плащане"),
    ("cash_on_delivery", "Потвърден наложен платеж"),
)

PAYMENT_METHOD = (
    ("card", "Карта"),
    ("cash_on_delivery", "Наложен платеж"),
)

ORDER_STATUS = (
    ("initiated", "Незавършена"),
    ("received", "Получена"),
    ("shipped", "Изпратена"),
    ("ready", "Готова за взимане"),
    ("completed", "Завършена"),
    ("canceled", "Отказана"),
)
PLACED_ORDER_STATUSES = ("received", "shipped", "ready", "completed")

SHIPPING_SERVICE = (
    ("econt", "Еконт"),
    ("speedy", "Спиди"),
    ("pigeon", "Pigeon Express"),
)

VARIANT_TYPE_CHOICES = (
    ("specification", "Specification"),
    ("length", "Length"),
)

PROMO_TYPE_CHOICES = (
    ("none", "No promotion"),
    ("buy_x_get_y", "Buy X Get Y Free"),
)

PRIZE_TYPE_CHOICES = (
    ("none", "No prize"),
    ("discount_percent", "Percentage discount"),
    ("free_shipping", "Free shipping"),
    ("mystery_box_min_total", "Mystery box over minimum total"),
)


class Category(models.Model):
    title = models.CharField(max_length=255)
    description = CKEditor5Field(config_name="extends", blank=True)
    sku = models.CharField(max_length=50, unique=True, null=True, verbose_name="SKU")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="subcategories",
        blank=True,
        null=True,
    )
    marketing_image = models.FileField(
        upload_to="images", blank=True, null=True, verbose_name="Маркетинг снимка"
    )
    hover_image = models.FileField(
        upload_to="images",
        blank=True,
        null=True,
        verbose_name="Втора снимка (показва се при задържане)",
    )
    show_banner = models.BooleanField(
        default=True,
        verbose_name="Показвай банера в категория",
    )
    slug = models.SlugField()
    meta_title = models.CharField(max_length=150, blank=True, null=True)
    meta_description = models.CharField(max_length=300, blank=True, null=True)
    is_popular = models.BooleanField(default=False, verbose_name="Популярна категория")
    status = models.CharField(choices=STATUS, max_length=50, default="published")

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["sku"]
        unique_together = ("parent", "slug")

    def get_full_path(self):
        parts = []
        current = self
        while current:
            parts.insert(0, current.slug)
            current = current.parent
        return "/".join(parts)

    def get_full_name_path(self):
        """
        Returns a human-readable category path, e.g. "Parent / Child / Subcategory".
        """
        names = []
        current = self
        while current:
            names.insert(0, current.title)
            current = current.parent
        return " - ".join(names)

    def __str__(self):
        return self.sku

    def products(self):
        return Product.objects.filter(category=self)

    def get_absolute_url(self):
        return reverse("store:category", args=[self.get_full_path()])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if self.status != "disabled" and self.parent_id and Category.branch_disabled(self.parent_id):
            self.status = "disabled"
        convert_uploaded_images(self, "marketing_image", "hover_image")
        super().save(*args, **kwargs)
        if self.status == "disabled":
            self._disable_branch()

    @staticmethod
    def branch_disabled(category_id):
        seen = set()
        current = category_id
        while current and current not in seen:
            seen.add(current)
            row = Category.objects.filter(pk=current).values_list("status", "parent_id").first()
            if not row:
                return False
            status, current = row
            if status == "disabled":
                return True
        return False

    def _disable_branch(self):
        ids = []
        frontier = [self.pk]
        while frontier:
            frontier = list(Category.objects.filter(parent_id__in=frontier).values_list("pk", flat=True))
            ids.extend(frontier)
        if ids:
            Category.objects.filter(pk__in=ids).exclude(status="disabled").update(status="disabled")
        Product.objects.filter(category_id__in=[self.pk, *ids]).exclude(status="disabled").update(status="disabled")

    @property
    def root(self):
        cat = self
        while cat.parent:
            cat = cat.parent
        return cat


class CategoryLink(models.Model):
    parent = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="linked_children",
    )
    child = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="linked_parents",
    )

    class Meta:
        unique_together = ("parent", "child")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("child")),
                name="catlink_parent_not_child",
            )
        ]
        verbose_name = "Category link (alias)"
        verbose_name_plural = "Category links (aliases)"

    def __str__(self):
        return f"{self.parent.title} → {self.child.title}"


class Product(models.Model):
    name = models.CharField(max_length=255)
    # Optional override for the H1 title on the product detail page
    h1_override = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="When set, this will replace the dynamic product detail H1"
    )
    image = models.FileField(
        upload_to="images", blank=True, null=True, default="default/default-image.avif"
    )
    description = CKEditor5Field(config_name="extends")
    meta_description = models.CharField(
        max_length=300, blank=True, null=True, help_text="Meta description for SEO"
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    # Regular/base price for the product
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        null=True,
        blank=True,
        verbose_name="Price",
    )
    # Optional sale price; when present and lower than price, it is used for purchase
    sale_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        null=True,
        blank=True,
        verbose_name="Sale Price",
    )
    stock = models.PositiveIntegerField(default=0, null=True, blank=True)
    shipping = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        null=True,
        blank=True,
        verbose_name="Shipping Amount",
    )
    status = models.CharField(choices=STATUS, max_length=50, default="published")
    featured = models.BooleanField(default=False, verbose_name="Marketplace Featured")
    sku = models.CharField(max_length=50, unique=True, verbose_name="SKU")
    slug = models.SlugField(max_length=255, null=True, blank=True)
    # Special product type that allows custom note and multi-device selection
    is_mystery_box = models.BooleanField(default=False, db_index=True)
    date = models.DateTimeField(default=timezone.now)
    variants = models.ManyToManyField("Variant", blank=True, related_name="products")
    colors = models.ManyToManyField("Color", blank=True, related_name="products")
    on_sale = models.BooleanField(default=False, db_index=True)
    # --- Product-specific promotion (e.g., Buy X Get Y Free) ---
    promo_type = models.CharField(
        max_length=20,
        choices=PROMO_TYPE_CHOICES,
        default="none",
        db_index=True,
        help_text="Type of product-level promotion."
    )
    promo_buy_qty = models.PositiveIntegerField(
        default=0,
        help_text="X in 'Buy X Get Y Free'."
    )
    promo_get_qty = models.PositiveIntegerField(
        default=0,
        help_text="Y in 'Buy X Get Y Free'."
    )
    promo_label_override = models.CharField(
        max_length=120,
        null=True,
        blank=True,
        help_text="Optional custom label for the promotion badge."
    )
    # New optional relations to drive SKU generation by sets
    size_group = models.ForeignKey(
        "SizeGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    model_groups = models.ManyToManyField(
        "ModelGroup",
        blank=True,
        related_name="products",
        help_text="Select one or more groups of compatible device models",
    )
    additional_categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name="extra_products",
        help_text="Optional extra categories where this product should also appear",
    )

    class Meta:
        ordering = ["sku"]
        verbose_name_plural = "Products"

    def __str__(self):
        return f"{self.name} ({self.sku})" if self.sku else self.name

    def gallery(self):
        return Gallery.objects.filter(product=self)

    @property
    def effective_price(self):
        """Price used for purchase: applies Band of the Week 50% discount if active,
        otherwise uses sale_price if valid, otherwise price.
        """
        # Apply Band of the Week discount (50% of base price) if this product is this week's band
        BandOfTheWeek = globals().get("BandOfTheWeek")
        if BandOfTheWeek and self.price:
            try:
                current_week_deal = BandOfTheWeek.get_current_week()
                if current_week_deal and current_week_deal.product_id == self.id:
                    half_price = self.price * Decimal("0.5")
                    return floor_to_cent(half_price)
            except Exception:
                pass

        # Fallback to regular sale logic
        if self.sale_price and self.price and self.sale_price < self.price:
            return self.sale_price
        return self.price

    @property
    def discount_percent(self):
        if self.price and self.sale_price and self.sale_price < self.price:
            discount = ((self.price - self.sale_price) / self.price) * 100
            return int(discount)
        return 0

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if self.status != "disabled" and self.category_id and Category.branch_disabled(self.category_id):
            self.status = "disabled"
        convert_uploaded_images(self, "image")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse(
            "store:product_detail", args=[self.category.get_full_path(), self.slug]
        )

    # --- Promotion helpers ---
    def has_active_promo(self) -> bool:
        try:
            return (
                self.promo_type == "buy_x_get_y"
                and int(self.promo_buy_qty or 0) > 0
                and int(self.promo_get_qty or 0) > 0
            )
        except Exception:
            return False

    def promo_label(self) -> str:
        if not self.has_active_promo():
            return ""
        if self.promo_label_override:
            return self.promo_label_override
        return f"Купи {int(self.promo_buy_qty)} вземи {int(self.promo_buy_qty) + int(self.promo_get_qty)}"

    def compute_promo_free_units(self, qty: int) -> int:
        try:
            q = max(0, int(qty or 0))
        except Exception:
            q = 0
        if not self.has_active_promo():
            return 0
        x = int(self.promo_buy_qty)
        y = int(self.promo_get_qty)
        group = x + y
        if group <= 0:
            return 0
        full_groups = q // group
        remainder = q % group
        extra_free = max(0, remainder - x)
        return full_groups * y + extra_free

    def compute_promo_paid_units(self, qty: int) -> int:
        try:
            q = max(0, int(qty or 0))
        except Exception:
            q = 0
        free_units = self.compute_promo_free_units(q)
        return max(0, q - free_units)


class Variant(models.Model):
    name = models.CharField(
        max_length=1000, verbose_name="Variant Name", null=True, blank=True
    )
    variant_type = models.CharField(
        max_length=32,
        choices=VARIANT_TYPE_CHOICES,
        default="specification",
        verbose_name="Variant Type",
    )

    def __str__(self):
        return f"{self.get_variant_type_display()}: {self.name}"


class VariantItem(models.Model):
    variant = models.ForeignKey(
        Variant, on_delete=models.CASCADE, related_name="variant_items"
    )
    title = models.CharField(
        max_length=1000, verbose_name="Item Title", null=True, blank=True
    )
    content = models.CharField(
        max_length=1000, verbose_name="Item Content", null=True, blank=True
    )

    def __str__(self):
        return self.title


class Gallery(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, related_name='gallery_images')
    image = models.FileField(upload_to="images", default="gallery.jpg")
    position = models.PositiveIntegerField(default=0, verbose_name="Position")
    gallery_id = ShortUUIDField(length=6, max_length=10, alphabet="1234567890")

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product.name} - image"

    def save(self, *args, **kwargs):
        convert_uploaded_images(self, "image")
        super().save(*args, **kwargs)


class Cart(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    user = models.ForeignKey(
        user_models.User, on_delete=models.SET_NULL, null=True, blank=True
    )
    qty = models.PositiveIntegerField(default=0, null=True, blank=True)
    price = models.DecimalField(
        decimal_places=2, max_digits=12, default=0.00, null=True, blank=True
    )
    sub_total = models.DecimalField(
        decimal_places=2, max_digits=12, default=0.00, null=True, blank=True
    )
    size = models.CharField(max_length=100, null=True, blank=True)
    model = models.CharField(max_length=100, null=True, blank=True)
    cart_id = models.CharField(max_length=1000, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    # Optional customer note and selected devices for mystery box lines
    note = models.TextField(null=True, blank=True)
    mystery_device_models = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.cart_id} - {self.product.name}"

    @property
    def promo_paid_units(self):
        try:
            unit = Decimal(str(self.price or 0))
            sub_total = Decimal(str(self.sub_total or 0))
            if unit and unit > 0:
                paid = (sub_total / unit).quantize(Decimal('1'), rounding=ROUND_FLOOR)
                paid_int = int(paid)
                return max(0, min(int(self.qty or 0), paid_int))
        except Exception:
            pass
        return int(self.qty or 0)

    @property
    def promo_free_units(self):
        try:
            return max(0, int(self.qty or 0) - int(self.promo_paid_units))
        except Exception:
            return 0


class Coupon(models.Model):
    code = models.CharField(max_length=100, unique=True)
    discount = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    min_subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum merchandise subtotal required to use this coupon.",
    )
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many paid orders can use this coupon. Blank means unlimited.",
    )
    per_customer_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many paid orders one customer can use this coupon on. Blank means unlimited.",
    )
    owner = models.ForeignKey(
        user_models.User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_coupons",
    )

    def __str__(self):
        return self.code

    @staticmethod
    def normalize_code(code):
        return (code or "").strip().upper()

    @classmethod
    def end_of_local_day(cls, day):
        from datetime import datetime, time, timedelta

        tz = timezone.get_current_timezone()
        start = datetime.combine(day + timedelta(days=1), time.min)
        return timezone.make_aware(start, tz)

    @classmethod
    def issue_personal(cls, *, code, discount, user, valid_until=None, min_subtotal=None):
        """A one-use coupon that only its owner can redeem."""
        return cls.objects.create(
            code=code,
            discount=discount,
            owner=user,
            valid_until=valid_until,
            min_subtotal=min_subtotal,
            usage_limit=1,
            per_customer_limit=1,
        )

    def clamp_discount(self):
        try:
            discount = int(self.discount)
        except (TypeError, ValueError):
            discount = 1
        self.discount = min(100, max(1, discount))

    def clean(self):
        super().clean()
        self.code = self.normalize_code(self.code)
        self.clamp_discount()

    def save(self, *args, **kwargs):
        self.code = self.normalize_code(self.code)
        self.clamp_discount()
        super().save(*args, **kwargs)

    def rejection_reason(self, order, user):
        """Why this coupon cannot be applied, or None when it can."""
        now = timezone.now()
        if not self.active:
            return "Този купон не е активен."
        if self.valid_from and now < self.valid_from:
            return "Този купон още не е валиден."
        if self.valid_until and now >= self.valid_until:
            return "Този купон е изтекъл."

        authenticated = user is not None and getattr(user, "is_authenticated", False)
        if self.owner_id or self.per_customer_limit is not None:
            if not authenticated:
                return "Трябва да сте влезли, за да използвате този купон."
        if self.owner_id and self.owner_id != user.pk:
            return "Този купон не е валиден за вашия акаунт."

        if self.min_subtotal is not None:
            required = Order.as_money(self.min_subtotal)
            if Order.as_money(order.sub_total) < required:
                return f"Купонът е валиден при междинна сума от поне {required} €."

        already = self.redemptions.exclude(order=order)
        if self.usage_limit is not None and already.count() >= self.usage_limit:
            return "Този купон вече е използван."
        if self.per_customer_limit is not None:
            used_by_customer = already.filter(user=user).count()
            if used_by_customer >= self.per_customer_limit:
                return "Вече сте използвали този купон."
        return None

    def mark_redeemed(self, order):
        redemption, _created = CouponRedemption.objects.get_or_create(
            order=order,
            defaults={"coupon": self, "user": order.customer},
        )
        return redemption

    @classmethod
    def mark_order_redeemed(cls, order):
        coupon = order.coupons.order_by("id").first()
        if coupon is None:
            return None
        return coupon.mark_redeemed(order)


class CouponRedemption(models.Model):
    """A coupon was used on an order whose payment succeeded."""

    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    order = models.OneToOneField("Order", on_delete=models.CASCADE, related_name="coupon_redemption")
    user = models.ForeignKey(
        user_models.User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_redemptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.coupon.code} on {self.order.order_id}"


class Order(models.Model):
    customer = models.ForeignKey(
        user_models.User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="customer",
        blank=True,
    )
    address = models.ForeignKey(
        "customer.Address", on_delete=models.SET_NULL, null=True
    )

    order_id = ShortUUIDField(length=6, max_length=25, alphabet="1234567890")
    date = models.DateTimeField(default=timezone.now)

    order_status = models.CharField(
        max_length=100, choices=ORDER_STATUS, default="initiated"
    )
    payment_status = models.CharField(
        max_length=100, choices=PAYMENT_STATUS, default="processing"
    )
    payment_method = models.CharField(
        max_length=100, choices=PAYMENT_METHOD, default=None, null=True, blank=True
    )

    shipping_service = models.CharField(
        max_length=100, choices=SHIPPING_SERVICE, default=None, null=True, blank=True
    )
    tracking_id = models.CharField(max_length=100, null=True, blank=True)

    sub_total = models.DecimalField(default=0.00, max_digits=12, decimal_places=2)
    shipping = models.DecimalField(default=0.00, max_digits=12, decimal_places=2)
    prize_free_shipping = models.BooleanField(
        default=False,
        help_text="Shipping was set to zero because of a spin or milestone prize.",
    )
    total = models.DecimalField(default=0.00, max_digits=12, decimal_places=2)
    saved = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        null=True,
        blank=True,
        help_text="Amount saved by customer",
    )
    coupons = models.ManyToManyField(Coupon, blank=True)
    payment_id = models.CharField(null=True, blank=True, max_length=1000)

    class Meta:
        verbose_name_plural = "Order"
        ordering = ["-date"]
        indexes = [models.Index(fields=["payment_id"], name="store_order_payment_idx")]

    def __str__(self):
        return self.order_id

    @staticmethod
    def as_money(value):
        return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def discount_for_subtotal(self, sub_total, *, without_coupon):
        """Percent off the merchandise subtotal for the first coupon.

        ``without_coupon`` is the amount to keep when no coupon is attached.
        Checkout passes 0 so clearing a code removes the reduction. The admin
        refresh passes the current ``saved`` so a hand-entered amount stays.
        """
        coupon = self.coupons.order_by("id").first()
        if coupon is None:
            return self.as_money(without_coupon)
        return self.as_money(
            self.as_money(sub_total) * Decimal(coupon.discount) / Decimal("100")
        )

    def totals_for_merchandise(self, sub_total, saved):
        """Merchandise subtotal, the single reduction, and the amount due."""
        sub_total = self.as_money(sub_total)
        saved = self.as_money(saved)
        shipping = self.as_money(self.shipping)
        total = self.as_money(sub_total + shipping - saved)
        return sub_total, saved, total

    def refresh_totals_from_items(self):
        """Set subtotal and total from the lines still on the order.

        Line prices stay as stored. A coupon reduces the order once, through saved.
        """
        sub_total = self.as_money(
            self.order_items.aggregate(amount=models.Sum("sub_total"))["amount"]
        )
        saved = self.discount_for_subtotal(sub_total, without_coupon=self.saved)
        sub_total, saved, total = self.totals_for_merchandise(sub_total, saved)
        self.sub_total = sub_total
        self.saved = saved
        self.total = total
        type(self).objects.filter(pk=self.pk).update(
            sub_total=sub_total,
            saved=saved,
            total=total,
        )

    def order_items(self):
        return OrderItem.objects.filter(order=self)


class StripeCheckoutAttempt(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="stripe_checkout_attempts")
    session_id = models.CharField(max_length=255, unique=True)
    reference = models.UUIDField(unique=True, null=True, editable=False)
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    payment_intent_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="order_items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    qty = models.IntegerField(default=0)
    model = models.CharField(max_length=100, null=True, blank=True)
    size = models.CharField(max_length=100, null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    sub_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    # Snapshot of mystery box customizations
    note = models.TextField(null=True, blank=True)
    mystery_device_models = models.JSONField(null=True, blank=True)

    def order_id(self):
        return f"{self.order.order_id}"

    @property
    def is_prize(self):
        note = self.note or ""
        return note.startswith("prize:spin:") or note.startswith("prize:milestone:")

    def __str__(self):
        return str(self.id)

    class Meta:
        ordering = ["id"]

    @property
    def promo_paid_units(self):
        try:
            unit = Decimal(str(self.price or 0))
            if unit and unit > 0:
                paid = (Decimal(str(self.sub_total or 0)) / unit)
                paid_int = int(paid)
                return max(0, min(int(self.qty or 0), paid_int))
        except Exception:
            pass
        return int(self.qty or 0)

    @property
    def promo_free_units(self):
        try:
            return max(0, int(self.qty or 0) - int(self.promo_paid_units))
        except Exception:
            return 0


class ColorGroup(models.Model):
    name_bg = models.CharField(max_length=100, unique=True)
    name_en = models.CharField(max_length=100, unique=True)
    hex_code = models.CharField(max_length=7)

    def __str__(self):
        return f"{self.name_bg} ({self.name_en})"


class Color(models.Model):
    name_bg = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    hex_code = models.CharField(max_length=7)
    group = models.ForeignKey(ColorGroup, on_delete=models.CASCADE, related_name="colors")

    def __str__(self):
        return f"{self.name_bg} ({self.name_en})"


class BandOfTheWeek(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="weekly_deals")
    week_start = models.DateField(db_index=True, unique=True, help_text="May be any date in the week; it will auto-normalize to Monday.")

    class Meta:
        verbose_name = "Band of the Week"
        verbose_name_plural = "Band of the Week"
        ordering = ["-week_start"]

    def __str__(self):
        return f"{self.week_start} - {self.product.name}"

    @staticmethod
    def _to_week_start(d):
        try:
            # Monday as start of week
            return d - timezone.timedelta(days=d.weekday())
        except Exception:
            # Fallback: treat given date as already week start
            return d

    @classmethod
    def get_current_week(cls):
        try:
            today = timezone.localdate()
            week_start = cls._to_week_start(today)
            return cls.objects.select_related("product").get(week_start=week_start)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_for_date(cls, date_obj):
        try:
            week_start = cls._to_week_start(date_obj)
            return cls.objects.select_related("product").get(week_start=week_start)
        except cls.DoesNotExist:
            return None

    def save(self, *args, **kwargs):
        # Ensure week_start is normalized to Monday regardless of input date
        try:
            from datetime import date as _date
            if isinstance(self.week_start, _date):
                self.week_start = self._to_week_start(self.week_start)
        except Exception:
            pass
        super().save(*args, **kwargs)


class DeviceModel(models.Model):
    name = models.CharField(max_length=150, unique=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Size(models.Model):
    name = models.CharField(max_length=50, unique=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class SizeGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sizes = models.ManyToManyField(Size, related_name="size_groups", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Size group"
        verbose_name_plural = "Size groups"

    def __str__(self):
        return self.name


class ModelGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    device_models = models.ManyToManyField(DeviceModel, related_name="model_groups", blank=True)
    generate_as_single_sku = models.BooleanField(
        default=False,
        help_text="When true, SKU generation will create one SKU per size and attach all models in this group to it."
    )
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Model group"
        verbose_name_plural = "Model groups"

    def __str__(self):
        return self.name


class ProductItem(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="items")
    size = models.ForeignKey(Size, on_delete=models.SET_NULL, null=True, blank=True, related_name="items")
    device_models = models.ManyToManyField(DeviceModel, related_name="product_items", blank=True)
    sku = models.CharField(max_length=64, unique=True, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    price_delta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional delta to add to product price/sale price (e.g., 3.00)"
    )

    class Meta:
        verbose_name = "Product item (SKU)"
        verbose_name_plural = "Product items (SKUs)"
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["product", "size"]),
        ]

    def __str__(self):
        parts = [self.product.name]
        if self.size:
            parts.append(str(self.size))
        return " / ".join(parts)

    @property
    def effective_price(self):
        base = self.product.effective_price
        try:
            delta = self.price_delta or 0
        except Exception:
            delta = 0
        return (base or 0) + delta


class SpinEntry(models.Model):
    """Stores a record of a user's spin result for a specific day.

    One spin per user per day is enforced via a unique constraint.
    Rewards are modeled simply for now: a percentage coupon or free shipping flag.
    """
    user = models.ForeignKey(user_models.User, on_delete=models.CASCADE, related_name="spin_entries")
    date = models.DateField(db_index=True, default=timezone.localdate)
    # Result labels are for analytics/visibility (e.g., "5%", "Free Shipping", "No Win")
    result_label = models.CharField(max_length=64)
    # Prize metadata
    prize_type = models.CharField(max_length=32, choices=PRIZE_TYPE_CHOICES, default="none", db_index=True)
    coupon_discount_percent = models.PositiveIntegerField(null=True, blank=True)
    free_shipping = models.BooleanField(default=False)
    min_order_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    coupon_code = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    redeemed_order = models.ForeignKey(
        "Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redeemed_spin_prizes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Daily spin entry"
        verbose_name_plural = "Daily spin entries"
        unique_together = ("user", "date")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} — {self.date} — {self.result_label}"


class SpinPrize(models.Model):
    """Admin-configurable prize shown on the wheel and used for selection."""
    label = models.CharField(max_length=64)
    prize_type = models.CharField(max_length=32, choices=PRIZE_TYPE_CHOICES, default="none", db_index=True)
    # Optional parameters depending on type
    discount_percent = models.PositiveIntegerField(null=True, blank=True)
    min_order_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Selection and display
    weight = models.FloatField(default=0.0, help_text="Relative probability weight; higher means more likely.")
    color = models.CharField(max_length=7, null=True, blank=True, help_text="Slice color hex code (e.g., #FFE082)")
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Spin prize"
        verbose_name_plural = "Spin prizes"

    def __str__(self):
        return f"{self.label} ({self.prize_type})"


MILESTONE_COUNTS = (
    ("spins", "Spins"),
    ("orders", "Placed orders"),
)


class SpinMilestone(models.Model):
    """A reward for reaching a number of daily spins or placed orders."""
    counts = models.CharField(max_length=10, choices=MILESTONE_COUNTS, default="spins", db_index=True)
    threshold_spins = models.PositiveIntegerField(
        "threshold",
        db_index=True,
        help_text="Award triggers when the customer reaches this many spins or placed orders.",
    )
    prize_type = models.CharField(max_length=32, choices=PRIZE_TYPE_CHOICES, default="none")
    discount_percent = models.PositiveIntegerField(null=True, blank=True)
    min_order_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    label = models.CharField(max_length=120, default="Награда за лоялност")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["counts", "threshold_spins", "id"]
        unique_together = ("counts", "threshold_spins", "prize_type", "discount_percent", "min_order_total")
        verbose_name = "milestone"

    def __str__(self):
        return f"#{self.threshold_spins} {self.counts} → {self.label}"

    @property
    def title(self):
        return reward_title(self.label, self.min_order_total)


def reward_title(label, minimum):
    """The reward's name with its minimum order, so the condition is never hidden."""
    if minimum is None:
        return label
    return f"{label} при поръчка от поне {Order.as_money(minimum)} €"


class SpinMilestoneAward(models.Model):
    """A milestone reward a customer earned, with its terms copied at that moment."""
    user = models.ForeignKey(user_models.User, on_delete=models.CASCADE, related_name="spin_milestone_awards")
    milestone = models.ForeignKey(SpinMilestone, on_delete=models.CASCADE, related_name="awards")
    label = models.CharField(max_length=120, blank=True, default="")
    prize_type = models.CharField(max_length=32, choices=PRIZE_TYPE_CHOICES, default="none")
    discount_percent = models.PositiveIntegerField(null=True, blank=True)
    min_order_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    awarded_at = models.DateTimeField(auto_now_add=True)
    coupon_code = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    redeemed_order = models.ForeignKey(
        "Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redeemed_milestone_prizes",
    )
    earned_order = models.ForeignKey(
        "Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="earned_milestone_awards",
    )

    class Meta:
        unique_together = ("user", "milestone")
        ordering = ["-awarded_at"]
        verbose_name = "milestone award"

    def __str__(self):
        return f"{self.user.email} → {self.milestone}"

    @property
    def title(self):
        return reward_title(self.label, self.min_order_total)

    def save(self, *args, **kwargs):
        if self._state.adding and not self.label:
            self.label = self.milestone.label
            self.prize_type = self.milestone.prize_type
            self.discount_percent = self.milestone.discount_percent
            self.min_order_total = self.milestone.min_order_total
        super().save(*args, **kwargs)


# -----------------------------
# Store theme / campaign settings
# -----------------------------
class StoreThemeSettings(models.Model):
    """Singleton-style settings to control the active seasonal campaign manually.

    Admin sets the currently active campaign (e.g., default, halloween). Views and
    templates read this value to conditionally render seasonal labels, icons and
    decorative elements. Not date-driven by design (manual toggle only).
    """

    CAMPAIGN_DEFAULT = "default"
    CAMPAIGN_HALLOWEEN = "halloween"
    CAMPAIGN_BLACK_FRIDAY = "black-friday"  # reserved for future use
    CAMPAIGN_VALENTINE = "valentine"

    CAMPAIGN_CHOICES = (
        (CAMPAIGN_DEFAULT, "Default"),
        (CAMPAIGN_HALLOWEEN, "Halloween"),
        (CAMPAIGN_BLACK_FRIDAY, "Black Friday"),
        (CAMPAIGN_VALENTINE, "Valentine"),
    )

    active_campaign = models.CharField(
        max_length=32,
        choices=CAMPAIGN_CHOICES,
        default=CAMPAIGN_DEFAULT,
        db_index=True,
    )

    class Meta:
        verbose_name = "Store theme settings"
        verbose_name_plural = "Store theme settings"

    def __str__(self) -> str:
        return f"Active: {self.active_campaign}"

    @classmethod
    def get_solo(cls):
        """Return the single settings row, creating one with defaults if missing."""
        obj = cls.objects.first()
        if obj:
            return obj
        return cls.objects.create(active_campaign=cls.CAMPAIGN_DEFAULT)

    # Cached getter for active campaign (single DB hit, then cache)
    CACHE_KEY = "store.active_campaign"
    _local_active_campaign = None

    @classmethod
    def get_active_campaign(cls) -> str:
        if cls._local_active_campaign:
            return cls._local_active_campaign
        cached = cache.get(cls.CACHE_KEY)
        if cached:
            cls._local_active_campaign = cached
            return cached
        try:
            obj = cls.get_solo()
            value = getattr(obj, "active_campaign", cls.CAMPAIGN_DEFAULT)
        except Exception:
            value = cls.CAMPAIGN_DEFAULT
        cls._local_active_campaign = value
        cache.set(cls.CACHE_KEY, value, timeout=None)
        return value

    @classmethod
    def invalidate_active_campaign_cache(cls):
        cls._local_active_campaign = None
        try:
            cache.delete(cls.CACHE_KEY)
        except Exception:
            pass

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.invalidate_active_campaign_cache()


class StaffUpdate(models.Model):
    """One shipped change, so employees can see what is different and how to test it."""

    summary = models.CharField(max_length=200)
    details = models.TextField(
        blank=True,
        help_text="What to try. One point per line.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        user_models.User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_updates",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "What's new"
        verbose_name_plural = "What's new"

    def __str__(self):
        return self.summary


class ServerErrorLog(models.Model):
    """One row for each unhandled server error, including customer and admin requests."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    exception_type = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    method = models.CharField(max_length=10, blank=True)
    path = models.CharField(max_length=500, blank=True)
    query_string = models.CharField(max_length=1000, blank=True)
    user = models.ForeignKey(
        user_models.User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="server_error_logs",
    )
    user_label = models.CharField(max_length=255, blank=True)
    is_staff = models.BooleanField(default=False)
    is_bot = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Server error"
        verbose_name_plural = "Server errors"

    def __str__(self):
        return f"{self.exception_type} on {self.path}"
