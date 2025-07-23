from django.db import models
from shortuuid.django_fields import ShortUUIDField
from django.utils import timezone
from slugify import slugify
from django_ckeditor_5.fields import CKEditor5Field
from userauths import models as user_models
from django.urls import reverse

STATUS = (
    ("published", "Published"),
    ("draft", "Draft"),
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
    ("size", "Size"),
    ("length", "Length"),
    ("model", "Model"),
)

RATING = (
    (1, "★☆☆☆☆"),
    (2, "★★☆☆☆"),
    (3, "★★★☆☆"),
    (4, "★★★★☆"),
    (5, "★★★★★"),
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
    image = models.FileField(
        upload_to="images", default="default/default-image.avif", null=True, blank=True
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


class Product(models.Model):
    name = models.CharField(max_length=100)
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
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        null=True,
        blank=True,
        verbose_name="Sale Price",
    )
    regular_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        null=True,
        blank=True,
        verbose_name="Regular Price",
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

    class Meta:
        ordering = ["sku"]
        verbose_name_plural = "Products"

    def __str__(self):
        if self.category:
            return f"{self.category.get_full_name_path()} - {self.name}"
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
    def discount_percent(self):
        if self.regular_price and self.regular_price > self.price:
            discount = ((self.regular_price - self.price) / self.regular_price) * 100
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

    def items(self):
        return VariantItem.objects.filter(variant=self)

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
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True)
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
        max_length=100, choices=ORDER_STATUS, default="received"
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
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
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
        return f"{self.name_bg} ({self.group.name_bg})"
