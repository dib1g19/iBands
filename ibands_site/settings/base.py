from pathlib import Path
from environs import Env
import dj_database_url
import os
from django.contrib import messages

env = Env()
env.read_env()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --- Security & Host Settings ---
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = [
    "127.0.0.1",
    "ibands.online",
    "www.ibands.online",
    "ibands-production.up.railway.app",
    "ibands.onrender.com",
]
ADMINS = [("Dimitar Bedachev", "dimitarbedachev@gmail.com")]
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1",
    "https://ibands.online",
    "https://www.ibands.online",
    "https://ibands-production.up.railway.app",
    "https://ibands.onrender.com",
]
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

# --- Installed Apps ---
INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "userauths",
    "store",
    "customer",
    "storages",
    "django_ckeditor_5",
    "anymail",
    "captcha",
    "django_extensions",
]

# --- Middleware ---
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    'ibands_site.middleware.ReconnectDBMiddleware',
    'ibands_site.middleware.OperationalErrorCounterMiddleware',
]

ROOT_URLCONF = "ibands_site.urls"

# --- Templates ---
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "store.context_processors.navigation_context",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ibands_site.wsgi.application"

# --- Authentication ---
AUTH_USER_MODEL = "userauths.User"
LOGIN_URL = "userauths:sign-in"
LOGIN_REDIRECT_URL = ""
LOGOUT_REDIRECT_URL = "userauths:sign-in"

# --- Password Validation ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalization ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Sofia"
USE_I18N = True
USE_TZ = True

# --- Static & Media Files ---
STATICFILES_DIRS = [BASE_DIR / "static"]

# --- AWS / S3 Storage ---
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = "ibandsbg"
AWS_S3_REGION_NAME = "eu-central-1"
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"

# --- Email / Anymail ---
EMAIL_BACKEND = env("EMAIL_BACKEND")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = env("SERVER_EMAIL")
ORDER_NOTIFICATION_EMAIL =  env("ORDER_NOTIFICATION_EMAIL")
ANYMAIL = {
    "MAILGUN_API_KEY": os.environ.get("MAILGUN_API_KEY"),
    "MAILGUN_SENDER_DOMAIN": os.environ.get("MAILGUN_SENDER_DOMAIN"),
    "MAILGUN_API_URL": "https://api.eu.mailgun.net/v3",
}

# --- Third Party Keys ---
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
PAYPAL_CLIENT_ID = env("PAYPAL_CLIENT_ID")
PAYPAL_SECRET_ID = env("PAYPAL_SECRET_ID")
FLUTTERWAVE_PUBLIC_KEY = env("FLUTTERWAVE_PUBLIC_KEY")
FLUTTERWAVE_PRIVATE_KEY = env("FLUTTERWAVE_PRIVATE_KEY")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY")
PAYSTACK_PRIVATE_KEY = env("PAYSTACK_PRIVATE_KEY")
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET")

RECAPTCHA_PUBLIC_KEY = env("DJANGO_RECAPTCHA_PUBLIC_KEY")
RECAPTCHA_PRIVATE_KEY = env("DJANGO_RECAPTCHA_PRIVATE_KEY")

# --- Miscellaneous ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MESSAGE_TAGS = {messages.ERROR: "danger"}
GRAPH_MODELS = {"all_applications": True, "graph_models": True}

# --- Jazzmin Admin Theme ---
JAZZMIN_SETTINGS = {
    "site_title": "iBands",
    "site_header": "iBands",
    "site_brand": "iBands",
    "site_icon": "assets/favicons/favicon.ico",
    "site_logo": "assets/img/logo-black.avif",
    "welcome_sign": "Welcome To iBands",
    "copyright": "iBands",
    "user_avatar": "images/photos/logo.jpg",
    "show_sidebar": True,
    "navigation_expanded": True,
    "order_with_respect_to": [
        "store",
        "store.product",
        "store.cart",
        "store.category",
        "store.order",
        "store.orderitem",
        "store.variant",
        "store.variantitem",
        "store.gallery",
        "store.coupon",
        "store.review",
        "store.middlewarestats",
        "userauths",
        "userauths.user",
        "userauths.profile",
    ],
    "icons": {
        "store.Product": "fas fa-th",
        "store.Cart": "fas fa-cart-plus",
        "store.Category": "fas fa-tag",
        "store.Order": "fas fa-clipboard-list",
        "store.OrderItem": "fas fa-box-open",
        "store.Variant": "fas fa-layer-group",
        "store.VariantItem": "fas fa-shapes",
        "store.Gallery": "fas fa-images",
        "store.Coupon": "fas fa-ticket-alt",
        "store.Review": "fas fa-star fa-beat",
        "store.MiddlewareStats": "fas fa-chart-bar",
        "userauths.User": "fas fa-user",
        "userauths.Profile": "fas fa-address-card",
        "userauths.ContactMessage": "fas fa-envelope-open-text",
        "customer.Address": "fas fa-location-arrow",
        "customer.Notifications": "fas fa-bell",
        "customer.Wishlist": "fas fa-heart",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-arrow-circle-right",
    "related_modal_active": False,
    "custom_js": None,
    "show_ui_builder": True,
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs",
    },
}

# --- CKEditor 5 ---
customColorPalette = [
    {"color": "hsl(4, 90%, 58%)", "label": "Red"},
    {"color": "hsl(340, 82%, 52%)", "label": "Pink"},
    {"color": "hsl(291, 64%, 42%)", "label": "Purple"},
    {"color": "hsl(262, 52%, 47%)", "label": "Deep Purple"},
    {"color": "hsl(231, 48%, 48%)", "label": "Indigo"},
    {"color": "hsl(207, 90%, 54%)", "label": "Blue"},
]

CKEDITOR_5_CONFIGS = {
    "default": {
        "toolbar": [
            "heading",
            "|",
            "bold",
            "italic",
            "link",
            "bulletedList",
            "numberedList",
            "blockQuote",
            "imageUpload",
        ],
    },
    "comment": {
        "language": {"ui": "en", "content": "en"},
        "toolbar": [
            "heading",
            "|",
            "bold",
            "italic",
            "link",
            "bulletedList",
            "numberedList",
            "blockQuote",
        ],
    },
    "extends": {
        "language": "en",
        "blockToolbar": [
            "paragraph",
            "heading1",
            "heading2",
            "heading3",
            "|",
            "bulletedList",
            "numberedList",
            "|",
            "blockQuote",
        ],
        "toolbar": [
            "bold",
            "italic",
            "underline",
            "|",
            "link",
            "strikethrough",
            "code",
            "subscript",
            "superscript",
            "highlight",
            "|",
            "bulletedList",
            "numberedList",
            "todoList",
            "|",
            "blockQuote",
            "insertImage",
            "|",
            "fontSize",
            "fontFamily",
            "fontColor",
            "fontBackgroundColor",
            "mediaEmbed",
            "removeFormat",
            "insertTable",
            "sourceEditing",
        ],
        "image": {
            "toolbar": [
                "imageTextAlternative",
                "|",
                "imageStyle:alignLeft",
                "imageStyle:alignRight",
                "imageStyle:alignCenter",
                "imageStyle:side",
                "|",
                "toggleImageCaption",
                "|",
            ],
            "styles": [
                "full",
                "side",
                "alignLeft",
                "alignRight",
                "alignCenter",
            ],
        },
        "table": {
            "contentToolbar": [
                "tableColumn",
                "tableRow",
                "mergeTableCells",
                "tableProperties",
                "tableCellProperties",
            ],
            "tableProperties": {
                "borderColors": customColorPalette,
                "backgroundColors": customColorPalette,
            },
            "tableCellProperties": {
                "borderColors": customColorPalette,
                "backgroundColors": customColorPalette,
            },
        },
        "heading": {
            "options": [
                {
                    "model": "paragraph",
                    "title": "Paragraph",
                    "class": "ck-heading_paragraph",
                },
                {
                    "model": "heading1",
                    "view": "h1",
                    "title": "Heading 1",
                    "class": "ck-heading_heading1",
                },
                {
                    "model": "heading2",
                    "view": "h2",
                    "title": "Heading 2",
                    "class": "ck-heading_heading2",
                },
                {
                    "model": "heading3",
                    "view": "h3",
                    "title": "Heading 3",
                    "class": "ck-heading_heading3",
                },
            ]
        },
        "list": {
            "properties": {
                "styles": True,
                "startIndex": True,
                "reversed": True,
            }
        },
        "htmlSupport": {
            "allow": [
                {"name": "/.*/", "attributes": True, "classes": True, "styles": True}
            ]
        },
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'store.middleware': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}