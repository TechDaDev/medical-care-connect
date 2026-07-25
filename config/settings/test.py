"""Test settings — raises throttle rates and uses SQLite for CI/offline."""

from .development import *  # noqa: F403, F401

# Use SQLite so tests run without PostgreSQL
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

# Generous throttle rates prevent cross-test cache interactions
REST_FRAMEWORK = {**REST_FRAMEWORK}  # noqa: F405
REST_FRAMEWORK.setdefault("DEFAULT_THROTTLE_RATES", {})
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(
    {
        "anon": "10000/hour",
        "user": "100000/hour",
        "login": "10000/hour",
        "register": "10000/hour",
        "refresh": "10000/hour",
        "ai_intake": "10000/hour",
        "admin_sensitive_write": "10000/hour",
    }
)
