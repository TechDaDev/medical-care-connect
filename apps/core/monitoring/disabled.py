"""No-op error monitor — logs to safe logger instead."""

from apps.core.logging import SafeLogger
from apps.core.monitoring.base import ErrorMonitor


class DisabledErrorMonitor(ErrorMonitor):
    """Safe no-op monitor. Logs events locally without external calls."""

    def __init__(self):
        self._logger = SafeLogger("mcc.monitor")

    def capture_exception(self, exception: Exception, context: dict | None = None) -> None:
        self._logger.error("monitor.exception", exception=repr(exception))

    def capture_message(self, message: str, level: str = "error", context: dict | None = None) -> None:
        getattr(self._logger, level, self._logger.info)(f"monitor.message: {message}")

    def set_user(self, user_id: str | None, role: str | None = None) -> None:
        pass

    def clear_user(self) -> None:
        pass
