from django import forms
from django.contrib.auth.forms import UserCreationForm

from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Checkbox

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
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox())

    class Meta:
        model = User
        fields = ["full_name", "mobile", "email", "password1", "password2", "captcha"]


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
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox())

    class Meta:
        model = User
        fields = ["email", "password", "captcha"]
