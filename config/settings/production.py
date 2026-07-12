from django.core.exceptions import ImproperlyConfigured

import environ

from .base import *  # noqa: F403, F401

DEBUG = False

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # JS reads CSRF token via DOM
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# HTTP-only cookie JWT (secure in production)
SIMPLE_JWT["AUTH_COOKIE_SECURE"] = True  # noqa: F405

# Database: PostgreSQL required in production
_prod_env = environ.Env()
_postgres_db = _prod_env("POSTGRES_DB", default=None)

if not _postgres_db:
    raise ImproperlyConfigured(
        "Production requires POSTGRES_DB environment variable. "
        "Set POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, "
        "POSTGRES_HOST, and POSTGRES_PORT in .env or environment."
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _postgres_db,
        "USER": _prod_env("POSTGRES_USER"),
        "PASSWORD": _prod_env("POSTGRES_PASSWORD"),
        "HOST": _prod_env("POSTGRES_HOST", default="localhost"),
        "PORT": _prod_env("POSTGRES_PORT", default="5432"),
        "OPTIONS": {
            "connect_timeout": 10,
        },
    },
}
