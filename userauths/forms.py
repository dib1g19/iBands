import re

from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Checkbox
from django import forms
from django.contrib.auth.forms import UserCreationForm

from userauths.models import User

CAPTCHA_ERRORS = {
    "required": "Моля, потвърдете, че не сте робот.",
    "captcha_invalid": "Проверката не мина. Моля, опитайте отново.",
    "captcha_error": "Проверката не мина. Моля, опитайте отново.",
}


class UserRegisterForm(UserCreationForm):
    full_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": "form-control rounded", "placeholder": "Пълно име"}
        ),
        required=True,
        error_messages={"max_length": "Името трябва да е до 255 символа."},
    )
    mobile = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": "form-control rounded", "placeholder": "Мобилен номер"}
        ),
        required=True,
        error_messages={"max_length": "Телефонът трябва да е до 255 символа."},
    )
    email = forms.EmailField(
        widget=forms.TextInput(
            attrs={"class": "form-control rounded", "placeholder": "Имейл адрес"}
        ),
        required=True,
    )
    password1 = forms.CharField(
        strip=False,
        max_length=4096,
        widget=forms.PasswordInput(
            attrs={"class": "form-control rounded", "placeholder": "Парола"}
        ),
        required=True,
    )
    password2 = forms.CharField(
        strip=False,
        max_length=4096,
        widget=forms.PasswordInput(
            attrs={"class": "form-control rounded", "placeholder": "Потвърди парола"}
        ),
        required=True,
    )
    captcha = ReCaptchaField(
        widget=ReCaptchaV2Checkbox(),
        error_messages=CAPTCHA_ERRORS,
    )

    class Meta:
        model = User
        fields = ["full_name", "mobile", "email", "password1", "password2", "captcha"]

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise forms.ValidationError("Имейл адресът е задължителен.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Този имейл вече е регистриран.")
        return email

    def clean_full_name(self):
        full_name = " ".join((self.cleaned_data.get("full_name") or "").split())
        if len(full_name) < 2:
            raise forms.ValidationError("Моля, въведете име и фамилия.")
        return full_name

    def clean_mobile(self):
        mobile = (self.cleaned_data.get("mobile") or "").strip()
        if not mobile:
            raise forms.ValidationError("Моля, въведете телефон.")
        digits = re.sub(r"\D", "", mobile)
        if not 8 <= len(digits) <= 15:
            raise forms.ValidationError("Моля, въведете валиден телефонен номер.")
        if mobile.startswith("+"):
            return f"+{digits}"
        return digits


class LoginForm(forms.Form):
    email = forms.EmailField(
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "class": "form-control rounded",
                "name": "email",
                "placeholder": "Имейл адрес",
                "autocomplete": "email",
            }
        ),
        required=True,
        error_messages={
            "required": "Моля, въведете имейл адрес.",
            "invalid": "Моля, въведете валиден имейл адрес.",
        },
    )
    password = forms.CharField(
        strip=False,
        max_length=4096,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control rounded",
                "name": "password",
                "placeholder": "Парола",
                "autocomplete": "current-password",
            }
        ),
        required=True,
        error_messages={"required": "Моля, въведете парола."},
    )
    captcha = ReCaptchaField(
        widget=ReCaptchaV2Checkbox(),
        error_messages=CAPTCHA_ERRORS,
    )

    class Meta:
        model = User
        fields = ["email", "password", "captcha"]

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()
