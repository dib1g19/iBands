from .base import *

DEBUG = False

STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
STATICFILES_STORAGE = 'ibands_site.storages.StaticStorage'

MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
DEFAULT_FILE_STORAGE = 'ibands_site.storages.MediaStorage'

DATABASES = {
    'default': dj_database_url.parse(
        env("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=True
    )
}