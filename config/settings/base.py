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
    "apps.attachments",
    "apps.staff",
    "apps.privacy",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "apps.core.logging.RequestLoggingMiddleware",
]

CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-csrftoken",
    "x-request-id",
    "x-requested-with",
]

CORS_EXPOSE_HEADERS = [
    "x-request-id",
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
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

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
        "login": env("AUTH_LOGIN_RATE", default="10/min"),
        "register": env("AUTH_REGISTER_RATE", default="5/hour"),
        "refresh": env("AUTH_REFRESH_RATE", default="30/min"),
        "ai_intake": env("AI_INTAKE_RATE", default="30/hour"),
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

# ── Attachments / Storage ──────────────────────────────────────────────────

ATTACHMENT_STORAGE_BACKEND = env("ATTACHMENT_STORAGE_BACKEND", default="local")
ATTACHMENT_LOCAL_ROOT = env("ATTACHMENT_LOCAL_ROOT", default=str(BASE_DIR / "protected_attachments"))
ATTACHMENT_MAX_SIZE_MB = env.int("ATTACHMENT_MAX_SIZE_MB", default=10)
ATTACHMENT_ALLOWED_EXTENSIONS = env("ATTACHMENT_ALLOWED_EXTENSIONS", default="pdf,jpg,jpeg,png")
ATTACHMENT_ALLOWED_MIME_TYPES = env("ATTACHMENT_ALLOWED_MIME_TYPES", default="application/pdf,image/jpeg,image/png")
ATTACHMENT_SCAN_MODE = env("ATTACHMENT_SCAN_MODE", default="disabled")
ATTACHMENT_RETENTION_DAYS = env.int("ATTACHMENT_RETENTION_DAYS", default=0)
ATTACHMENT_DOWNLOAD_CHUNK_SIZE = env.int("ATTACHMENT_DOWNLOAD_CHUNK_SIZE", default=65536)

# ── Railway Bucket ─────────────────────────────────────────────────────────

RAILWAY_BUCKET_ENDPOINT = env("RAILWAY_BUCKET_ENDPOINT", default="")
RAILWAY_BUCKET_NAME = env("RAILWAY_BUCKET_NAME", default="")
RAILWAY_BUCKET_ACCESS_KEY = env("RAILWAY_BUCKET_ACCESS_KEY", default="")
RAILWAY_BUCKET_SECRET_KEY = env("RAILWAY_BUCKET_SECRET_KEY", default="")
RAILWAY_BUCKET_REGION = env("RAILWAY_BUCKET_REGION", default="auto")
RAILWAY_BUCKET_ADDRESSING_STYLE = env("RAILWAY_BUCKET_ADDRESSING_STYLE", default="virtual")
RAILWAY_BUCKET_USE_SSL = env.bool("RAILWAY_BUCKET_USE_SSL", default=True)
RAILWAY_BUCKET_VERIFY_SSL = env.bool("RAILWAY_BUCKET_VERIFY_SSL", default=True)
RAILWAY_BUCKET_CONNECT_TIMEOUT = env.int("RAILWAY_BUCKET_CONNECT_TIMEOUT", default=5)
RAILWAY_BUCKET_READ_TIMEOUT = env.int("RAILWAY_BUCKET_READ_TIMEOUT", default=30)
RAILWAY_BUCKET_MAX_RETRIES = env.int("RAILWAY_BUCKET_MAX_RETRIES", default=3)

# ── AI-Assisted Intake ──────────────────────────────────────────────────────

AI_INTAKE_ENABLED = env("AI_INTAKE_ENABLED", default=False)
AI_INTAKE_PROVIDER = env("AI_INTAKE_PROVIDER", default="deepseek")

DEEPSEEK_API_KEY = env("DEEPSEEK_API_KEY", default=None)
DEEPSEEK_BASE_URL = env("DEEPSEEK_BASE_URL", default="https://api.deepseek.com")
DEEPSEEK_MODEL = env("DEEPSEEK_MODEL", default=None)
DEEPSEEK_TIMEOUT_SECONDS = env.int("DEEPSEEK_TIMEOUT_SECONDS", default=45)
DEEPSEEK_MAX_TOKENS = env.int("DEEPSEEK_MAX_TOKENS", default=1200)
DEEPSEEK_TEMPERATURE = env.float("DEEPSEEK_TEMPERATURE", default=0.2)

# ── Logging ─────────────────────────────────────────────────────────────────

LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOG_FORMAT = env("LOG_FORMAT", default="json")
LOG_SERVICE_NAME = env("LOG_SERVICE_NAME", default="mcc-backend")
LOG_INCLUDE_REQUESTS = env("LOG_INCLUDE_REQUESTS", default="true")
LOG_SLOW_REQUEST_MS = env.int("LOG_SLOW_REQUEST_MS", default=1000)
LOG_IP_HASH_SALT = env("LOG_IP_HASH_SALT", default="")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "apps.core.logging.JSONFormatter"},
        "simple": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "simple",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "mcc": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "mcc.request": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "mcc.security": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "mcc.monitor": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}

# ── Error Monitoring ────────────────────────────────────────────────────────

ERROR_MONITOR_PROVIDER = env("ERROR_MONITOR_PROVIDER", default="disabled")
ERROR_MONITOR_DSN = env("ERROR_MONITOR_DSN", default="")
ERROR_MONITOR_ENVIRONMENT = env("ERROR_MONITOR_ENVIRONMENT", default="")
ERROR_MONITOR_RELEASE = env("ERROR_MONITOR_RELEASE", default="")

# ── Backup / Operations ─────────────────────────────────────────────────────

BACKUP_ROOT = env("BACKUP_ROOT", default=str(BASE_DIR / "backups"))
BACKUP_RETENTION_COUNT = env.int("BACKUP_RETENTION_COUNT", default=7)
BACKUP_REQUIRE_ENCRYPTION = env.bool("BACKUP_REQUIRE_ENCRYPTION", default=False)
BACKUP_ENCRYPTION_PROVIDER = env("BACKUP_ENCRYPTION_PROVIDER", default="disabled")

# ── Privacy / Data Export ───────────────────────────────────────────────────

DATA_EXPORT_ROOT = env("DATA_EXPORT_ROOT", default=str(BASE_DIR / "exports"))
DATA_EXPORT_EXPIRY_DAYS = env.int("DATA_EXPORT_EXPIRY_DAYS", default=7)

# ── Application Version ─────────────────────────────────────────────────────

APP_VERSION = env("APP_VERSION", default="0.0.0")
APP_RELEASE = env("APP_RELEASE", default="")
GIT_COMMIT_SHA = env("GIT_COMMIT_SHA", default="")
