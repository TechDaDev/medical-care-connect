"""Test settings — raises throttle rates so the cache never blocks tests."""

from .development import *  # noqa: F403, F401

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
    }
)
