"""Scanner factory — returns the configured scanner singleton."""

from django.conf import settings

from .base import BaseScanner
from .disabled import DisabledScanner


_scanner_cache = {}


def get_scanner() -> BaseScanner:
    """Return a cached scanner instance based on ATTACHMENT_SCAN_MODE."""
    mode = getattr(settings, "ATTACHMENT_SCAN_MODE", "disabled")

    if mode == "disabled":
        return _cached("disabled", lambda: DisabledScanner())
    elif mode == "clamav":
        from .clamav import ClamavScanner
        return _cached("clamav", lambda: ClamavScanner())

    raise ValueError(f"Unknown ATTACHMENT_SCAN_MODE: {mode}")


def clear_scanner_cache():
    _scanner_cache.clear()


def _cached(key: str, factory):
    if key not in _scanner_cache:
        _scanner_cache[key] = factory()
    return _scanner_cache[key]
