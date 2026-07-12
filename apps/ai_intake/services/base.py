from abc import ABC, abstractmethod


class AIProviderError(Exception):
    """Base exception for AI provider errors."""

    pass


class AIProviderDisabled(AIProviderError):
    """Raised when AI intake is not enabled."""

    pass


class AIProviderConfigurationError(AIProviderError):
    """Raised when provider configuration is invalid."""

    pass


class AIProviderUnavailable(AIProviderError):
    """Raised when the provider cannot be reached."""

    pass


class AIResponseInvalid(AIProviderError):
    """Raised when the provider returns invalid/unexpected content."""

    pass


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
