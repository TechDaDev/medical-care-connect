"""Error monitor factory — resolves provider name to adapter."""

from django.conf import settings

from apps.core.monitoring.base import ErrorMonitor
from apps.core.monitoring.disabled import DisabledErrorMonitor


def get_error_monitor() -> ErrorMonitor:
    """Return configured ErrorMonitor instance.

    Provider set via ERROR_MONITOR_PROVIDER env (default: "disabled").
    Unsupported providers fall back to disabled safely.
    """
    provider = getattr(settings, "ERROR_MONITOR_PROVIDER", "disabled")
    return _resolve(provider)


def _resolve(provider: str) -> ErrorMonitor:
    mapping: dict[str, type[ErrorMonitor]] = {
        "disabled": DisabledErrorMonitor,
    }
    cls = mapping.get(provider)
    if cls is None:
        return DisabledErrorMonitor()
    return cls()


# Module-level singleton
_monitor: ErrorMonitor | None = None


def error_monitor() -> ErrorMonitor:
    global _monitor
    if _monitor is None:
        _monitor = get_error_monitor()
    return _monitor
