from unittest.mock import patch

from django.test import TestCase

from django_recaptcha.client import RecaptchaResponse
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

    @patch("django_recaptcha.fields.client.submit", return_value=RecaptchaResponse(is_valid=True))
    def test_phone_keeps_the_digits(self, _submit):
        form = UserRegisterForm(data={
            "full_name": "Иван Петров",
            "mobile": "0888 123 456",
            "email": "ivan@example.com",
            "password1": "A-strong-pass-1",
            "password2": "A-strong-pass-1",
            "g-recaptcha-response": "ok",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["mobile"], "0888123456")

    @patch("django_recaptcha.fields.client.submit", return_value=RecaptchaResponse(is_valid=True))
    def test_signup_saves_name_and_phone_on_the_user(self, _submit):
        form = UserRegisterForm(data={
            "full_name": "Иван Петров",
            "mobile": "+359 88 812 3456",
            "email": "saved@example.com",
            "password1": "A-strong-pass-1",
            "password2": "A-strong-pass-1",
            "g-recaptcha-response": "ok",
        })

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        user.refresh_from_db()
        self.assertEqual(user.full_name, "Иван Петров")
        self.assertEqual(user.mobile, "+359888123456")
        self.assertEqual(user.image, "default/default-user.avif")

    def test_signup_without_captcha_does_not_create_an_account(self):
        response = self.client.post("/auth/sign-up/", {
            "full_name": "Иван Петров",
            "mobile": "0888123456",
            "email": "no-captcha@example.com",
            "password1": "A-strong-pass-1",
            "password2": "A-strong-pass-1",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Моля, потвърдете, че не сте робот.")
        self.assertFalse(User.objects.filter(email="no-captcha@example.com").exists())


class LoginValidationTests(TestCase):
    def test_empty_login_asks_for_both_fields(self):
        form = LoginForm(data={})

        self.assertFalse(form.is_valid())
        self.assertIn("Моля, въведете имейл адрес.", form.errors["email"])
        self.assertIn("Моля, въведете парола.", form.errors["password"])
