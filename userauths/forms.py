from django import forms
from django.contrib.auth.forms import UserCreationForm

# Captcha temporarily disabled
# from captcha.fields import ReCaptchaField
# from captcha.widgets import ReCaptchaV2Checkbox

from userauths.models import User


class UserRegisterForm(UserCreationForm):
    full_name = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control rounded", "placeholder": "Пълно име"}
        ),
        required=True,
    )
    mobile = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control rounded", "placeholder": "Мобилен номер"}
        ),
        required=True,
    )
    email = forms.EmailField(
        widget=forms.TextInput(
            attrs={"class": "form-control rounded", "placeholder": "Имейл адрес"}
        ),
        required=True,
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control rounded", "placeholder": "Парола"}
        ),
        required=True,
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control rounded", "placeholder": "Потвърди парола"}
        ),
        required=True,
    )
    # captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox())

    class Meta:
        model = User
        fields = ["full_name", "mobile", "email", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise forms.ValidationError("Имейл адресът е задължителен.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Този имейл вече е регистриран.")
        return email

    def clean_full_name(self):
        full_name = (self.cleaned_data.get("full_name") or "").strip()
        if not full_name:
            raise forms.ValidationError("Моля, въведете име и фамилия.")
        return full_name

    def clean_mobile(self):
        mobile = (self.cleaned_data.get("mobile") or "").strip()
        if not mobile:
            raise forms.ValidationError("Моля, въведете телефон.")
        return mobile


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control rounded",
                "name": "email",
                "placeholder": "Имейл адрес",
            }
        ),
        required=False,
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control rounded",
                "name": "password",
                "placeholder": "Парола",
            }
        ),
        required=False,
    )
    # captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox())

    class Meta:
        model = User
        fields = ["email", "password"]
