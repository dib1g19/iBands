from pathlib import Path
import environ
import dj_database_url
from django.contrib import messages

env = environ.Env()
BASE_DIR = Path(__file__).resolve().parent.parent.parent
env.read_env(str(BASE_DIR / ".env"))
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
    "ibands_site.middleware.RequestCounterMiddleware",
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
                "store.context_processors.pixel_settings",
                "store.context_processors.theme_settings",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

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
ORDER_NOTIFICATION_EMAIL = env("ORDER_NOTIFICATION_EMAIL")
ANYMAIL = {
    "MAILGUN_API_KEY": env("MAILGUN_API_KEY"),
    "MAILGUN_SENDER_DOMAIN": env("MAILGUN_SENDER_DOMAIN"),
    "MAILGUN_API_URL": "https://api.eu.mailgun.net/v3",
}

# --- Third Party Keys ---
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")

RECAPTCHA_PUBLIC_KEY = env("DJANGO_RECAPTCHA_PUBLIC_KEY")
RECAPTCHA_PRIVATE_KEY = env("DJANGO_RECAPTCHA_PRIVATE_KEY")

# --- Meta / Facebook ---
FACEBOOK_PIXEL_ID = env("FACEBOOK_PIXEL_ID")
FACEBOOK_CAPI_ACCESS_TOKEN = env("FACEBOOK_CAPI_ACCESS_TOKEN")
FACEBOOK_CAPI_TEST_CODE = env("FACEBOOK_CAPI_TEST_CODE", default=None)

# --- Miscellaneous ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MESSAGE_TAGS = {messages.ERROR: "danger"}
GRAPH_MODELS = {"all_applications": True, "graph_models": True}

# Canonical site URL (used in emails/links)
SITE_URL = env("SITE_URL", default="https://ibands.online")

# --- Econt Integration ---
ECONT_SHOP_ID = env("ECONT_SHOP_ID")
ECONT_SHIPPMENT_CALC_URL = env("ECONT_SHIPPMENT_CALC_URL", default="https://delivery.econt.com/customer_info.php")
ECONT_UPDATE_ORDER_ENDPOINT = env("ECONT_UPDATE_ORDER_ENDPOINT", default="https://delivery.econt.com/services/OrdersService.updateOrder.json")
ECONT_PRIVATE_KEY = env("ECONT_PRIVATE_KEY")

# --- Speedy Integration ---
SPEEDY_USERNAME = env("SPEEDY_USERNAME")
SPEEDY_PASSWORD = env("SPEEDY_PASSWORD")
SPEEDY_API_BASE = env("SPEEDY_API_BASE", default="https://api.speedy.bg")
SPEEDY_CREATE_SHIPMENT_URL = env("SPEEDY_CREATE_SHIPMENT_URL", default=f"{SPEEDY_API_BASE}/shipments")
SPEEDY_CALCULATION_URL = env("SPEEDY_CALCULATION_URL", default=f"{SPEEDY_API_BASE}/calculation")
SPEEDY_DEFAULT_SERVICE_ID = env("SPEEDY_DEFAULT_SERVICE_ID", default="505")
SPEEDY_DROPOFF_OFFICE_ID = env("SPEEDY_DROPOFF_OFFICE_ID", default=867)
SPEEDY_OBPD_OPTION = env("SPEEDY_OBPD_OPTION", default="TEST")  # Allowed: OPEN or TEST

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
        "store.productitem",
        "store.size",
        "store.sizegroup",
        "store.devicemodel",
        "store.modelgroup",
        "store.BandOfTheWeek",
        "store.category",
        "store.categoryLink",
        "store.cart",
        "store.order",
        "store.orderitem",
        "store.variant",
        "store.variantitem",
        "store.gallery",
        "store.coupon",
        "store.review",
        "store.colorgroup",
        "store.color",
        "store.stats",
        "store.SpinPrize",
        "store.SpinMilestone",
        "store.SpinMilestoneAward",
        "store.SpinEntry",
        "store.StoreThemeSettings",
        "store.Stats",
        "userauths",
        "userauths.user",
        "userauths.profile",
    ],
    "icons": {
        "store.Product": "fas fa-th",
        "store.ProductItem": "fas fa-th",
        "store.Size": "fas fa-ruler",
        "store.SizeGroup": "fas fa-th",
        "store.DeviceModel": "fas fa-mobile-alt",
        "store.ModelGroup": "fas fa-th",
        "store.BandOfTheWeek": "fas fa-calendar-week",
        "store.Category": "fas fa-tag",
        "store.CategoryLink": "fas fa-link",
        "store.Cart": "fas fa-cart-plus",
        "store.Order": "fas fa-clipboard-list",
        "store.OrderItem": "fas fa-box-open",
        "store.Variant": "fas fa-layer-group",
        "store.VariantItem": "fas fa-shapes",
        "store.Gallery": "fas fa-images",
        "store.Coupon": "fas fa-ticket-alt",
        "store.Review": "fas fa-star fa-beat",
        "store.ColorGroup": "fas fa-palette",
        "store.Color": "fas fa-eye-dropper",
        "store.SpinPrize": "fas fa-gift",
        "store.SpinMilestone": "fas fa-trophy",
        "store.SpinEntry": "fas fa-dice",
        "store.SpinMilestoneAward": "fas fa-medal",
        "store.StoreThemeSettings": "fas fa-palette",
        "store.Stats": "fas fa-chart-bar",
        "userauths.User": "fas fa-user",
        "userauths.Profile": "fas fa-address-card",
        "userauths.ContactMessage": "fas fa-envelope-open-text",
        "userauths.NewsletterSubscription": "fas fa-newspaper",
        "customer.Address": "fas fa-location-arrow",
        "customer.Notifications": "fas fa-bell",
        "customer.Wishlist": "fas fa-heart",
    },
    "custom_links": {
        "store": [
            {"name": "Stats", "url": "admin-stats", "icon": "fas fa-chart-bar"},
        ]
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
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
