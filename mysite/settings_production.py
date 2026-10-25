"""Production settings. Use with DJANGO_SETTINGS_MODULE=mysite.settings_production."""

import importlib.util
import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in ('1', 'true', 'yes', 'on')


DEBUG = False

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if (
    not SECRET_KEY
    or SECRET_KEY.startswith('django-insecure-')
    or len(SECRET_KEY) < 50
):
    raise ImproperlyConfigured(
        'Set a strong DJANGO_SECRET_KEY (at least 50 characters) for production.'
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')
    if host.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('Set DJANGO_ALLOWED_HOSTS for production.')

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

# Enforce HTTPS and secure cookies in production.
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r'^healthz/$']
SECURE_COOKIES = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('DJANGO_HSTS_INCLUDE_SUBDOMAINS', True)
SECURE_HSTS_PRELOAD = _env_bool('DJANGO_HSTS_PRELOAD', False)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

# Reuse database connections between requests.
DATABASES['default']['CONN_MAX_AGE'] = int(os.environ.get('DB_CONN_MAX_AGE', '60'))
if 'mysql' in DATABASES['default'].get('ENGINE', ''):
    DATABASES['default'].setdefault('OPTIONS', {})
    DATABASES['default']['OPTIONS'].setdefault('charset', 'utf8mb4')

# Use a shared cache so rate limits apply across workers. Run
# `python manage.py createcachetable` during deployment.
CACHES = {
    'default': {
        'BACKEND': os.environ.get(
            'DJANGO_CACHE_BACKEND',
            'django.core.cache.backends.db.DatabaseCache',
        ),
        'LOCATION': os.environ.get('DJANGO_CACHE_LOCATION', 'healthwise_cache'),
    }
}

EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '20'))

# WhiteNoise serves collected static files when installed.
if importlib.util.find_spec('whitenoise'):
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }
