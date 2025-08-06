from .base import *

DEBUG = True

# ✅ Static files are served locally
STATIC_URL = "static/"
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ✅ Media files are still stored on S3
MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"
DEFAULT_FILE_STORAGE = "ibands_site.storages.MediaStorage"

# EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
# EMAIL_FILE_PATH = BASE_DIR / "sent_emails"

DATABASES = {
    "default": dj_database_url.parse(env("DEVELOPMENT_DATABASE_URL"), conn_max_age=600)
}
INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
]
INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
