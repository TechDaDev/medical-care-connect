import os
from pathlib import Path

import environ

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["*"]),
    CORS_ALLOWED_ORIGINS=(list, []),
)

BASE_DIR = Path(__file__).resolve().parents[2]

environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")

DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Application definition

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.patients",
    "apps.doctors",
    "apps.specialties",
    "apps.consultations",
    "apps.messaging",
    "apps.medical_records",
    "apps.ai_intake",
    "apps.notifications",
    "apps.audit",
    "apps.staff",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database

_postgres_db = env("POSTGRES_DB", default=None)
if _postgres_db:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _postgres_db,
            "USER": env("POSTGRES_USER", default=""),
            "PASSWORD": env("POSTGRES_PASSWORD", default=""),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            "OPTIONS": {
                "connect_timeout": 10,
            },
        },
    }
else:
    DATABASES = {
        "default": env.db_url(
            "DATABASE_URL",
            default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        ),
    }

# Custom user model

AUTH_USER_MODEL = "accounts.User"

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Baghdad"
USE_I18N = True
USE_TZ = True

# Static files

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# CSRF

CSRF_TRUSTED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CSRF_COOKIE_NAME = "mcc_csrftoken"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# REST Framework

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.CookieJWTAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}

# SimpleJWT

from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    # HTTP-only cookie names
    "AUTH_COOKIE": "mcc_access",
    "AUTH_COOKIE_REFRESH": "mcc_refresh",
    # Cookie flags
    "AUTH_COOKIE_SECURE": False,         # True in production
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_SAMESITE": "Lax",
    "AUTH_COOKIE_PATH": "/",
}

# ── AI-Assisted Intake ──────────────────────────────────────────────────────

AI_INTAKE_ENABLED = env("AI_INTAKE_ENABLED", default=False)
AI_INTAKE_PROVIDER = env("AI_INTAKE_PROVIDER", default="deepseek")

DEEPSEEK_API_KEY = env("DEEPSEEK_API_KEY", default=None)
DEEPSEEK_BASE_URL = env("DEEPSEEK_BASE_URL", default="https://api.deepseek.com")
DEEPSEEK_MODEL = env("DEEPSEEK_MODEL", default=None)
DEEPSEEK_TIMEOUT_SECONDS = env.int("DEEPSEEK_TIMEOUT_SECONDS", default=45)
DEEPSEEK_MAX_TOKENS = env.int("DEEPSEEK_MAX_TOKENS", default=1200)
DEEPSEEK_TEMPERATURE = env.float("DEEPSEEK_TEMPERATURE", default=0.2)
