"""Provider error taxonomy and safe retry policy."""

import random
import time
from abc import ABC, abstractmethod


class AIProviderError(Exception):
    """Base exception for AI provider errors."""

    def __init__(self, message: str, *, safe_code: str = "provider_error", retryable: bool = False):
        super().__init__(message)
        self.safe_code = safe_code
        self.retryable = retryable


class AIProviderDisabled(AIProviderError):
    """Raised when AI intake is not enabled."""

    def __init__(self, message: str = "AI intake is not enabled."):
        super().__init__(message, safe_code="intake_disabled", retryable=False)


class AIProviderConfigurationError(AIProviderError):
    """Raised when provider configuration is invalid."""

    def __init__(self, message: str, *, safe_code: str = "provider_configuration_error"):
        super().__init__(message, safe_code=safe_code, retryable=False)


class AIProviderUnavailable(AIProviderError):
    """Raised when provider cannot be reached (transient)."""

    def __init__(self, message: str, *, safe_code: str = "provider_unavailable", retryable: bool = True):
        super().__init__(message, safe_code=safe_code, retryable=retryable)


class AIResponseInvalid(AIProviderError):
    """Raised when provider returns invalid/unexpected content."""

    def __init__(self, message: str, *, safe_code: str = "provider_response_invalid", retryable: bool = False):
        super().__init__(message, safe_code=safe_code, retryable=retryable)


class AISemanticValidationError(AIProviderError):
    """Raised when provider output is structurally valid but semantically unsafe."""

    def __init__(self, message: str, *, safe_code: str = "semantic_validation_failed", retryable: bool = False):
        super().__init__(message, safe_code=safe_code, retryable=retryable)


# ── Retry policy ─────────────────────────────────────────────────────────────
# Automatic retry only for transient failures: connection, timeout, rate limit,
# provider 5xx.  Never retry configuration errors, unsafe output, schema
# violations, injection violations, or deterministic emergency stops.
MAX_RETRIES_DEFAULT = 2
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 8.0
RETRYABLE_EXCEPTIONS = (AIProviderUnavailable,)


def retry_transient(fn, *, max_retries: int = MAX_RETRIES_DEFAULT):
    """Run provider call with bounded exponential backoff + jitter.

    Returns (result, retry_count).  Only retries transient failures whose
    exception instance carries retryable=True (connection / timeout / rate
    limit / 5xx).  Non-retryable errors (4xx rejections, configuration,
    unsafe output) propagate immediately.
    """
    attempt = 0
    while True:
        try:
            return fn(), attempt
        except RETRYABLE_EXCEPTIONS as exc:
            if not getattr(exc, "retryable", True):
                raise
            attempt += 1
            if attempt > max_retries:
                raise
            delay = min(
                MAX_BACKOFF_SECONDS,
                BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)),
            )
            jitter = delay * random.uniform(0.5, 1.5)
            time.sleep(jitter)


class AIProvider(ABC):
    """Abstract interface for AI providers."""

    @abstractmethod
    def generate_structured_response(
        self,
        messages: list[dict],
        schema_name: str = "intake_turn",
    ) -> dict:
        """Send messages and return structured JSON response."""
        ...