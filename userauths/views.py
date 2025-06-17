from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth import logout
from django.urls import reverse

from userauths import models as userauths_models
from userauths import forms as userauths_forms

def register_view(request):
    if request.user.is_authenticated:
        messages.warning(request, f"Вече сте влезли в профила си")
        return redirect('/')   

    form = userauths_forms.UserRegisterForm(request.POST or None)

    if form.is_valid():
        user = form.save()

        full_name = form.cleaned_data.get('full_name')
        email = form.cleaned_data.get('email')
        mobile = form.cleaned_data.get('mobile')
        password = form.cleaned_data.get('password1')

        user = authenticate(email=email, password=password)
        login(request, user)

        messages.success(request, f"Профилът беше създаден успешно.")
        profile = userauths_models.Profile.objects.create(full_name=full_name, mobile=mobile, user=user)
        profile.save()

        next_url = request.GET.get("next", 'store:index')
        return redirect(next_url)
    
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Създай акаунт", "url": ""},
    ]
    
    context = {
        "form": form,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, 'userauths/sign-up.html', context)

def login_view(request):
    if request.user.is_authenticated:
        messages.warning(request, "Вече сте в профила си")
        return redirect('store:index')
    
    if request.method == 'POST':
        form = userauths_forms.LoginForm(request.POST)  
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            captcha_verified = form.cleaned_data.get('captcha', False)  

            if captcha_verified:
                try:
                    user_authenticate = authenticate(request, email=email, password=password)

                    if user_authenticate is not None:
                        login(request, user_authenticate)
                        messages.success(request, "Успешно влязохте в профила си.")
                        next_url = request.GET.get("next", 'store:index')

                        print("next_url ========", next_url)
                        if next_url == '/undefined/':
                            return redirect('store:index')
                        
                        if next_url == 'undefined':
                            return redirect('store:index')

                        if next_url is None or not next_url.startswith('/'):
                            return redirect('store:index')

                        return redirect(next_url)
                    else:
                        messages.error(request, "Грешен имейл или парола")
                except userauths_models.User.DoesNotExist:
                    messages.error(request, 'Потребителят не съществува')
            else:
                messages.error(request, 'Верификацията чрез капча не бе успешна. Моля, опитайте отново.')
    else:
        form = userauths_forms.LoginForm()  
    
    breadcrumbs = [
        {"label": "Начална Страница", "url": reverse("store:index")},
        {"label": "Вход", "url": ""},
    ]
    
    context = {
        "form": form,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "userauths/sign-in.html", context)

def logout_view(request):
    if "cart_id" in request.session:
        cart_id = request.session['cart_id']
    else:
        cart_id = None
    logout(request)
    request.session['cart_id'] = cart_id
    messages.success(request, 'Успешно излязохте от профила си.')
    return redirect("userauths:sign-in")

def handler404(request, exception, *args, **kwargs):
    context = {}
    response = render(request, 'userauths/404.html', context)
    response.status_code = 404
    return response

def handler500(request, *args, **kwargs):
    context = {}
    response = render(request, 'userauths/500.html', context)
    response.status_code = 500
    return response
