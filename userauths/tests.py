from django.test import TestCase

from userauths.forms import LoginForm, UserRegisterForm
from userauths.models import User


class SignUpValidationTests(TestCase):
    def test_long_name_stays_on_the_form(self):
        response = self.client.post("/auth/sign-up/", {
            "full_name": "а" * 300,
            "mobile": "0888123456",
            "email": "long-name@example.com",
            "password1": "A-strong-pass-1",
            "password2": "A-strong-pass-1",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Името трябва да е до 255 символа.")
        self.assertFalse(User.objects.filter(email="long-name@example.com").exists())

    def test_phone_must_contain_a_real_number(self):
        form = UserRegisterForm(data={
            "full_name": "Иван Петров",
            "mobile": "not a phone",
            "email": "ivan@example.com",
            "password1": "A-strong-pass-1",
            "password2": "A-strong-pass-1",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("Моля, въведете валиден телефонен номер.", form.errors["mobile"])

    def test_phone_keeps_the_digits(self):
        form = UserRegisterForm(data={
            "full_name": "Иван Петров",
            "mobile": "0888 123 456",
            "email": "ivan@example.com",
            "password1": "A-strong-pass-1",
            "password2": "A-strong-pass-1",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["mobile"], "0888123456")


class LoginValidationTests(TestCase):
    def test_empty_login_asks_for_both_fields(self):
        form = LoginForm(data={})

        self.assertFalse(form.is_valid())
        self.assertIn("Моля, въведете имейл адрес.", form.errors["email"])
        self.assertIn("Моля, въведете парола.", form.errors["password"])
