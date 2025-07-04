"""
WSGI config for ibands_site project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
from django.core.wsgi import get_wsgi_application
from environs import Env

env = Env()
env.read_env()

ENVIRONMENT = env("ENVIRONMENT", default="dev")

if ENVIRONMENT == "prod":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ibands_site.settings.prod")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ibands_site.settings.dev")

application = get_wsgi_application()
