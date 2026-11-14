from .base import *

DEBUG = False

STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/static/"
MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"
STORAGES = {
    "default": {
        "BACKEND": "ibands_site.storages.MediaStorage",
    },
    "staticfiles": {
        "BACKEND": "ibands_site.storages.StaticStorage",
    },
}

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL"),
        conn_max_age=290
    )
}

DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
