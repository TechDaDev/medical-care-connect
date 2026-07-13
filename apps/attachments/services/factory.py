"""Storage backend factory.

Selects and caches the active storage backend based on settings.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.attachments.services.base import AttachmentStorageBackend
from apps.attachments.services.local import LocalProtectedStorageBackend

_backend_cache: dict[str, AttachmentStorageBackend] = {}


def get_storage_backend() -> AttachmentStorageBackend:
    """Return the configured storage backend (cached after first call)."""
    provider = settings.ATTACHMENT_STORAGE_BACKEND
    if provider in _backend_cache:
        return _backend_cache[provider]

    if provider == "local":
        backend: AttachmentStorageBackend = LocalProtectedStorageBackend()
    else:
        raise ImproperlyConfigured(
            f"Unknown ATTACHMENT_STORAGE_BACKEND: '{provider}'. "
            f"Supported values: 'local'."
        )

    _backend_cache[provider] = backend
    return backend


def clear_backend_cache() -> None:
    """Clear the cached backend (useful in tests)."""
    _backend_cache.clear()
