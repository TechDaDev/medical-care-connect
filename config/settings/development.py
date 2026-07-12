from pathlib import Path

import environ

from .base import *  # noqa: F403, F401

DEBUG = True

ALLOWED_HOSTS = ["*"]

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] += [  # noqa: F405
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Database: PostgreSQL with SQLite fallback for development
BASE_DIR = Path(__file__).resolve().parents[2]

_dev_env = environ.Env()
_postgres_db = _dev_env("POSTGRES_DB", default=None)

if _postgres_db:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _postgres_db,
            "USER": _dev_env("POSTGRES_USER", default=""),
            "PASSWORD": _dev_env("POSTGRES_PASSWORD", default=""),
            "HOST": _dev_env("POSTGRES_HOST", default="localhost"),
            "PORT": _dev_env("POSTGRES_PORT", default="5432"),
            "OPTIONS": {
                "connect_timeout": 10,
            },
        },
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        },
    }
