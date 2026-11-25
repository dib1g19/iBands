from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from customer import models as customer_models
from store import models as store_models
from store.prizes import customer_rewards, order_ladder, sync_order_milestones


class OrderLadderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="ladder@example.com", username="ladder", password="secret",
        )

    def _order(self, status="initiated", customer=None, email="ladder@example.com", sub_total=Decimal("20.00")):
        order = store_models.Order.objects.create(
            customer=customer, order_status=status, sub_total=sub_total, total=sub_total,
        )
        order.address = customer_models.Address.objects.create(
            name="Test", phone="0888", email=email, delivery_method="econt_office", city="София",
        )
        order.save(update_fields=["address"])
        return order

    def _pay_cash(self, order):
        with patch("store.views.send_order_notification_email") as send, \
             patch("store.views.send_order_to_econt", return_value=None), \
             patch("store.views.send_meta_purchase_event"):
            response = self.client.post(reverse("store:cod_payment", args=[order.order_id]))
        return response, send

    def _ship_to_office(self, order):
        self.client.post(
            reverse("store:save_econt_address", args=[order.order_id]),
            data={
                "name": "Test", "phone": "0888123456", "email": "ladder@example.com", "city": "София",
                "address": "", "office_code": "1234", "office_name": "Офис Еконт", "post_code": "1000",
                "face": "", "shipping_price": 6.20,
            },
            content_type="application/json",
        )
        order.refresh_from_db()
        return order

    def _awards(self):
        return store_models.SpinMilestoneAward.objects.filter(user=self.user, milestone__counts="orders")

    def test_the_first_order_unlocks_free_shipping_on_the_success_page_and_in_the_email(self):
        self.client.force_login(self.user)
        order = self._order(customer=self.user)

        response, send = self._pay_cash(order)
        page = self.client.get(response["Location"])

        award = self._awards().get()
        self.assertEqual(award.prize_type, "free_shipping")
        self.assertEqual(award.min_order_total, Decimal("10.00"))
        self.assertEqual(award.earned_order, order)
        self.assertEqual(send.call_args_list[0].kwargs["unlocked"], [award])
        self.assertContains(page, "Тази поръчка отключи")
        self.assertContains(page, "Безплатна доставка до офис при поръчка от поне 10.00 €")

    def test_the_third_order_issues_a_personal_ten_percent_coupon(self):
        for _ in range(3):
            self._order(status="received", customer=self.user)

        sync_order_milestones(self.user)

        award = self._awards().get(milestone__prize_type="discount_percent")
        coupon = store_models.Coupon.objects.get(code=award.coupon_code)
        self.assertTrue(coupon.code.startswith("LO-"))
        self.assertEqual(coupon.owner, self.user)
        self.assertEqual(coupon.discount, 10)
        self.assertEqual(coupon.usage_limit, 1)

    def test_canceling_takes_back_rewards_that_were_not_used(self):
        orders = [self._order(status="received", customer=self.user) for _ in range(3)]
        sync_order_milestones(self.user)
        code = self._awards().get(milestone__prize_type="discount_percent").coupon_code

        orders[2].order_status = "canceled"
        orders[2].save()

        self.assertFalse(self._awards().filter(milestone__threshold_spins=3).exists())
        self.assertFalse(store_models.Coupon.objects.filter(code=code).exists())
        self.assertTrue(self._awards().filter(milestone__threshold_spins=1).exists())

    def test_canceling_keeps_a_reward_that_was_already_used(self):
        self._order(status="received", customer=self.user)
        sync_order_milestones(self.user)
        award = self._awards().get()
        award.redeemed_order = self._order(status="received", customer=self.user)
        award.save(update_fields=["redeemed_order"])

        for order in store_models.Order.objects.filter(customer=self.user):
            order.order_status = "canceled"
            order.save()

        self.assertTrue(self._awards().filter(pk=award.pk).exists())

    def test_the_next_office_order_ships_free_after_the_first(self):
        self.client.force_login(self.user)
        self._pay_cash(self._order(customer=self.user))

        later = self._ship_to_office(self._order(customer=self.user))

        self.assertEqual(later.shipping, Decimal("0.00"))
        self.assertTrue(later.prize_free_shipping)

    def test_free_shipping_needs_an_order_of_at_least_ten_euro(self):
        self.client.force_login(self.user)
        self._pay_cash(self._order(customer=self.user))

        small = self._ship_to_office(self._order(customer=self.user, sub_total=Decimal("9.99")))

        self.assertEqual(small.shipping, Decimal("6.20"))
        self.assertFalse(small.prize_free_shipping)

    def test_an_earned_reward_keeps_its_terms_when_the_milestone_changes(self):
        self.client.force_login(self.user)
        self._pay_cash(self._order(customer=self.user))
        store_models.SpinMilestone.objects.filter(counts="orders", threshold_spins=1).update(
            label="Безплатна доставка", min_order_total=Decimal("50.00"),
        )

        later = self._ship_to_office(self._order(customer=self.user))
        shipping = next(r for r in customer_rewards(self.user) if r["source"] == "Награда за 1 поръчка")

        self.assertTrue(later.prize_free_shipping)
        self.assertEqual(shipping["label"], "Безплатна доставка до офис")
        self.assertIn("поне 10.00 €", shipping["how"])

    def test_starting_a_checkout_grants_rewards_from_past_orders(self):
        self._order(status="received", customer=self.user)
        product = store_models.Product.objects.create(name="Band", sku="SKU-LADDER", description="Band", price=Decimal("10.00"))
        store_models.Cart.objects.create(
            cart_id="ladder-cart", product=product, qty=1, price=Decimal("10.00"), sub_total=Decimal("10.00"),
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["cart_id"] = "ladder-cart"
        session.save()

        self.client.post(reverse("store:create_order"))

        self.assertTrue(self._awards().filter(milestone__prize_type="free_shipping").exists())

    def test_a_claimed_guest_order_counts(self):
        guest = self._order(status="received")
        self.client.force_login(self.user)

        self.client.get(reverse("customer:order_detail", args=[guest.order_id]))

        self.assertEqual(self._awards().get().earned_order, guest)

    def test_a_guest_is_invited_to_sign_up_for_rewards(self):
        guest = self._order()

        response, _send = self._pay_cash(guest)
        page = self.client.get(response["Location"])

        self.assertContains(page, "Създай профил")
        self.assertContains(page, "Първата: Безплатна доставка до офис при поръчка от поне 10.00 €.")

    def test_spins_do_not_reach_order_milestones(self):
        self.client.force_login(self.user)

        self.client.post(reverse("store:spin_perform"))

        self.assertFalse(self._awards().exists())

    def test_rewards_say_where_they_came_from_how_they_apply_and_until_when(self):
        self._order(status="received", customer=self.user)
        sync_order_milestones(self.user)
        spin_box = store_models.SpinMilestone.objects.create(
            threshold_spins=10, prize_type="mystery_box_min_total", min_order_total=Decimal("25.00"), label="Mini кутия",
        )
        store_models.SpinMilestoneAward.objects.create(user=self.user, milestone=spin_box)
        store_models.SpinEntry.objects.create(
            user=self.user, result_label="Отстъпка 5%", prize_type="discount_percent", coupon_code="SPIN-1-1",
        )

        rewards = {reward["source"]: reward for reward in customer_rewards(self.user)}

        today = rewards["Колелото на късмета днес"]
        self.assertEqual(today["valid"], "Важи до края на деня")
        self.assertEqual(today["code"], "SPIN-1-1")
        self.assertIn("Код за отстъпка", today["how"])
        shipping = rewards["Награда за 1 поръчка"]
        self.assertEqual(shipping["label"], "Безплатна доставка до офис")
        self.assertEqual(shipping["valid"], "")
        box = rewards["Награда за 10 завъртания"]
        self.assertEqual(box["how"], "Добавя се сама в поръчка от поне 25.00 €.")

    def test_a_coupon_reward_shows_the_minimum_the_coupon_enforces(self):
        for _ in range(3):
            self._order(status="received", customer=self.user)
        sync_order_milestones(self.user)
        store_models.SpinMilestone.objects.filter(counts="orders", threshold_spins=3).update(min_order_total=Decimal("30.00"))

        coupon = next(r for r in customer_rewards(self.user) if r["code"])

        self.assertEqual(coupon["how"], "Въведете кода в полето „Код за отстъпка“ при поръчка.")

    def test_the_ladder_points_at_the_next_reward(self):
        for _ in range(2):
            self._order(status="received", customer=self.user)
        self._order(status="initiated", customer=self.user)

        ladder = order_ladder(self.user)

        self.assertEqual(ladder["count"], 2)
        self.assertEqual(ladder["next"].threshold_spins, 3)
        self.assertEqual(ladder["remaining"], 1)
        self.assertEqual(ladder["progress"], 66)

    def test_the_dashboard_names_the_minimum_of_the_next_reward(self):
        for _ in range(4):
            self._order(status="received", customer=self.user)
        self.client.force_login(self.user)

        page = self.client.get(reverse("customer:dashboard"))

        self.assertContains(page, "и отключвате: Mini мистериозна кутия при поръчка от поне 25.00 €")
