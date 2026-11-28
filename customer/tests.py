from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from store.models import Category, Coupon, Order, OrderItem, Product
from store.templatetags.pricing import dual_price


class OrderDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = get_user_model().objects.create_user(
            email="details@example.com", username="details", password="secret",
        )
        cls.order = Order.objects.create(customer=cls.buyer)
        cls.detail_url = reverse("customer:order_detail", args=[cls.order.order_id])
        cls.method_url = reverse("store:set_payment_method", args=[cls.order.order_id])

    def setUp(self):
        self.client.force_login(self.buyer)

    def test_selected_method_is_visible_while_awaiting_confirmation(self):
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, ">Няма записан метод</dd>")
        self.assertContains(detail, "Очаква потвърждение")

        for method, label in (("card", "Карта"), ("cash_on_delivery", "Наложен платеж")):
            with self.subTest(method=method):
                response = self.client.post(self.method_url, {"payment_method": method}, content_type="application/json")
                self.assertEqual(response.status_code, 200)
                detail = self.client.get(self.detail_url)
                self.assertContains(detail, f">{label}</dd>")
                self.assertContains(detail, "Очаква потвърждение")

    def test_order_detail_displays_the_saved_payment_status(self):
        for method, status, label, badge_style in (
            ("card", "paid", "Платено", "bg-light-primary text-primary"),
            ("cash_on_delivery", "cash_on_delivery", "Потвърден наложен платеж", "bg-light-primary text-primary"),
            ("card", "failed", "Неуспешно плащане", "alert-danger"),
        ):
            with self.subTest(status=status):
                self.order.payment_method = method
                self.order.payment_status = status
                self.order.order_status = "initiated" if status == "failed" else "received"
                self.order.save(update_fields=["payment_method", "payment_status", "order_status"])
                detail = self.client.get(self.detail_url)
                self.assertContains(detail, f'{badge_style}">{label}</span>')

    def test_promo_code_is_shown_with_the_saved_discount(self):
        coupon = Coupon.objects.create(code="DETAIL-SAVE10", discount=10)
        self.order.coupons.add(coupon)
        self.assertNotContains(self.client.get(self.detail_url), "Промокод")

        self.order.saved = Decimal("10.00")
        self.order.save(update_fields=["saved"])
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, "Промокод")
        self.assertContains(detail, coupon.code)
        self.assertContains(detail, f"-{dual_price(self.order.saved)}")

        self.order.coupons.remove(coupon)
        detail = self.client.get(self.detail_url)
        self.assertNotContains(detail, "Промокод")
        self.assertContains(detail, f"-{dual_price(self.order.saved)}")

    def test_item_rows_use_saved_quantities_and_amounts(self):
        category = Category.objects.create(title="Mystery boxes", slug="boxes")
        product = Product.objects.create(
            name="Mystery box", sku="DETAIL-BOX", price=Decimal("43.70"), sale_price=Decimal("35.00"),
            category=category,
        )
        item = OrderItem.objects.create(
            order=self.order, product=product, qty=3, price=Decimal("12.00"), sub_total=Decimal("24.00"),
            mystery_device_models=["Apple Watch Series 9", "Apple Watch Ultra"],
        )
        older_product = Product.objects.create(name="Older band", sku="DETAIL-OLD")
        OrderItem.objects.create(order=self.order, product=older_product, qty=1)

        detail = self.client.get(self.detail_url)
        for label, value in (
            ("Количество", item.qty),
            ("Единична цена", dual_price(item.price)),
            ("Общо за артикула", dual_price(item.sub_total)),
        ):
            self.assertContains(
                detail,
                f'<div class="col-4"><p class="mb-1 text-muted">{label}</p><p class="mb-0 fw-semibold">{value}</p></div>',
                html=True,
                count=1,
            )
        self.assertContains(detail, "Apple Watch Series 9, Apple Watch Ultra")
        self.assertContains(detail, "Older band")
        self.assertNotContains(detail, dual_price(product.price))
        for label in ("Статус на поръчката", "Метод на плащане", "Платежен статус"):
            self.assertContains(detail, f">{label}</dt>", count=1)
