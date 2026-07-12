from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403, F401

# ── Safety net: refuse to serve with dangerous defaults ──────────────────────

def _require(key: str, hint: str = "") -> str:
    val = env(key, default=None)  # noqa: F405
    if not val:
        msg = f"Production requires {key}."
        if hint:
            msg += f" {hint}"
        raise ImproperlyConfigured(msg)
    return val


DEBUG = False

SECRET_KEY = _require("SECRET_KEY")

ALLOWED_HOSTS = _require("ALLOWED_HOSTS", "No wildcard allowed in production.")
if isinstance(ALLOWED_HOSTS, str):
    ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS.split(",")]
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Wildcard ALLOWED_HOSTS ('*') is forbidden in production.")

# ── HTTPS / Security headers ────────────────────────────────────────────────

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # JS reads CSRF token from cookie
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"

# HTTP-only cookie JWT (secure in production)
SIMPLE_JWT["AUTH_COOKIE_SECURE"] = True  # noqa: F405

# ── Database ────────────────────────────────────────────────────────────────

_prod_env = environ.Env()
_postgres_db = _prod_env("POSTGRES_DB", default=None)

if not _postgres_db:
    raise ImproperlyConfigured(
        "Production requires POSTGRES_DB environment variable. "
        "Set POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, "
        "POSTGRES_HOST, and POSTGRES_PORT in .env or environment."
    )

_db_options = {"connect_timeout": 10}
if env.bool("DATABASE_SSL_REQUIRE", default=False):
    _db_options["sslmode"] = "require"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _postgres_db,
        "USER": _prod_env("POSTGRES_USER"),
        "PASSWORD": _prod_env("POSTGRES_PASSWORD"),
        "HOST": _prod_env("POSTGRES_HOST", default="localhost"),
        "PORT": _prod_env("POSTGRES_PORT", default="5432"),
        "OPTIONS": _db_options,
        "CONN_MAX_AGE": env.int("CONN_MAX_AGE", default=0),
    },
}
