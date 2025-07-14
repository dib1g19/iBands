"""
WSGI config for ibands_site project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
from django.core.wsgi import get_wsgi_application
import environ

env = environ.Env()
env.read_env(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

ENVIRONMENT = env("ENVIRONMENT", default="dev")

if ENVIRONMENT == "prod":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ibands_site.settings.prod")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ibands_site.settings.dev")

application = get_wsgi_application()
