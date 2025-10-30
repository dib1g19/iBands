from django.db import models
from shortuuid.django_fields import ShortUUIDField
from django.utils import timezone
from slugify import slugify
from django_ckeditor_5.fields import CKEditor5Field
from userauths import models as user_models
from django.urls import reverse
from decimal import Decimal, ROUND_FLOOR
from store.utils import floor_to_cent

STATUS = (
    ("published", "Published"),
    ("disabled", "Disabled"),
)

PAYMENT_STATUS = (
    ("processing", "Обработка"),
    ("paid", "Платено"),
    ("failed", "Неуспешно плащане"),
    ("cash_on_delivery", "Наложен платеж"),
)

PAYMENT_METHOD = (
    ("card", "карта"),
    ("cash_on_delivery", "Наложен платеж"),
)

ORDER_STATUS = (
    ("initiated", "Незавършена"),
    ("received", "Приета"),
    ("shipped", "Изпратена"),
    ("delivered", "Доставена"),
    ("completed", "Завършена"),
    ("canceled", "Отказана"),
)

SHIPPING_SERVICE = (
    ("econt", "Еконт"),
    ("speedy", "Спиди"),
)

VARIANT_TYPE_CHOICES = (
    ("specification", "Specification"),
    ("length", "Length"),
)

RATING = (
    (1, "★☆☆☆☆"),
    (2, "★★☆☆☆"),
    (3, "★★★☆☆"),
    (4, "★★★★☆"),
    (5, "★★★★★"),
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
        if self.pk:
            orig = Category.objects.get(pk=self.pk)
            if orig.title != self.title:
                self.slug = slugify(self.title)
        else:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

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
                check=~models.Q(parent=models.F("child")),
                name="catlink_parent_not_child",
            )
        ]
        verbose_name = "Category link (alias)"
        verbose_name_plural = "Category links (aliases)"

    def __str__(self):
        return f"{self.parent.title} → {self.child.title}"


class Product(models.Model):
    name = models.CharField(max_length=100)
    # Optional override for the H1 title on the product detail page
    h1_override = models.CharField(
        max_length=150,
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
    slug = models.SlugField(null=True, blank=True)
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
        return self.name

    def average_rating(self):
        return Review.objects.filter(product=self).aggregate(
            avg_rating=models.Avg("rating")
        )["avg_rating"]

    def reviews(self):
        return Review.objects.filter(product=self)

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
        if self.pk:
            orig = Product.objects.get(pk=self.pk)
            if orig.name != self.name:
                self.slug = slugify(self.name)
        else:
            self.slug = slugify(self.name)
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
    gallery_id = ShortUUIDField(length=6, max_length=10, alphabet="1234567890")

    def __str__(self):
        return f"{self.product.name} - image"


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
    code = models.CharField(max_length=100)
    discount = models.IntegerField(default=1)

    def __str__(self):
        return self.code


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

    def __str__(self):
        return self.order_id

    def order_items(self):
        return OrderItem.objects.filter(order=self)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="order_items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    qty = models.IntegerField(default=0)
    model = models.CharField(max_length=100, null=True, blank=True)
    size = models.CharField(max_length=100, null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    sub_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def order_id(self):
        return f"{self.order.order_id}"

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


class Review(models.Model):
    user = models.ForeignKey(
        user_models.User, on_delete=models.SET_NULL, blank=True, null=True
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviews",
    )
    review = models.TextField(null=True, blank=True)
    reply = models.TextField(null=True, blank=True)
    rating = models.IntegerField(choices=RATING, default=None)
    active = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} review on {self.product.name}"


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

    class Meta:
        ordering = ["name"]
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


class SpinMilestone(models.Model):
    """Configurable milestones for number of spins, e.g., 100 spins → grant prize."""
    threshold_spins = models.PositiveIntegerField(db_index=True, help_text="Award triggers when user reaches this total spin count")
    prize_type = models.CharField(max_length=32, choices=PRIZE_TYPE_CHOICES, default="none")
    discount_percent = models.PositiveIntegerField(null=True, blank=True)
    min_order_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    label = models.CharField(max_length=120, default="Награда за лоялност")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["threshold_spins", "id"]
        unique_together = ("threshold_spins", "prize_type", "discount_percent", "min_order_total")

    def __str__(self):
        return f"#{self.threshold_spins} spins → {self.label}"


class SpinMilestoneAward(models.Model):
    """Records that a user has received a milestone award to avoid duplicates."""
    user = models.ForeignKey(user_models.User, on_delete=models.CASCADE, related_name="spin_milestone_awards")
    milestone = models.ForeignKey(SpinMilestone, on_delete=models.CASCADE, related_name="awards")
    awarded_at = models.DateTimeField(auto_now_add=True)
    coupon_code = models.CharField(max_length=100, null=True, blank=True, db_index=True)

    class Meta:
        unique_together = ("user", "milestone")
        ordering = ["-awarded_at"]

    def __str__(self):
        return f"{self.user.email} → milestone {self.milestone.threshold_spins}"
