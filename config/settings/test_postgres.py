"""Acceptance-test settings using real PostgreSQL locking semantics."""

from .base import env
from .test import *  # noqa: F403, F401

_database_name = env("POSTGRES_DB")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _database_name,
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "OPTIONS": {"connect_timeout": 10},
        "TEST": {"NAME": f"test_{_database_name}_phase_e"},
    },
}
