from .base import *

DEBUG = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ✅ Media files are still stored on S3
MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
DEFAULT_FILE_STORAGE = 'ecom_prj.storages.MediaStorage'

# ✅ Static files are served locally
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

DATABASES = {
    'default': dj_database_url.parse(
        env("DEVELOPMENT_DATABASE_URL"),
        conn_max_age=600
    )
}