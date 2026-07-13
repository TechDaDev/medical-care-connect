"""
Provider-neutral error monitoring interface.

Adapters:
  DisabledErrorMonitor          — no-op (default)
  SentryErrorMonitor            — reserved
  RailwayObservabilityAdapter   — reserved
"""

from abc import ABC, abstractmethod


class ErrorMonitor(ABC):
    """Abstract error monitoring service."""

    @abstractmethod
    def capture_exception(self, exception: Exception, context: dict | None = None) -> None:
        ...

    @abstractmethod
    def capture_message(self, message: str, level: str = "error", context: dict | None = None) -> None:
        ...

    @abstractmethod
    def set_user(self, user_id: str | None, role: str | None = None) -> None:
        ...

    @abstractmethod
    def clear_user(self) -> None:
        ...
