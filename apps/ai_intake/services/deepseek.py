"""OpenAI-compatible DeepSeek provider with bounded retries and safe errors."""

import json
import logging

from django.conf import settings
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from apps.ai_intake.services.base import (
    AIProvider,
    AIProviderConfigurationError,
    AIProviderUnavailable,
    AIResponseInvalid,
    retry_transient,
)

logger = logging.getLogger(__name__)


class DeepSeekProvider(AIProvider):
    """OpenAI-compatible provider for DeepSeek API.

    Automatic retries happen only inside retry_transient for transient
    failures (connection / timeout / rate-limit / 5xx). Configuration
    errors and malformed or unsafe content never retry.
    """

    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = settings.DEEPSEEK_BASE_URL
        self.model = settings.DEEPSEEK_MODEL
        self.timeout = settings.DEEPSEEK_TIMEOUT_SECONDS
        self.max_tokens = settings.DEEPSEEK_MAX_TOKENS
        self.temperature = settings.DEEPSEEK_TEMPERATURE
        self._validate_config()
        self.retry_count = 0

    def _validate_config(self):
        missing = []
        if not self.api_key:
            missing.append("API key")
        if not self.model:
            missing.append("model name")
        if missing:
            raise AIProviderConfigurationError(
                f"DeepSeek is missing required configuration: {', '.join(missing)}",
                safe_code="provider_configuration_error",
            )

    def _call_api(self, client, messages):
        return client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

    def generate_structured_response(
        self,
        messages: list[dict],
        schema_name: str = "intake_turn",
    ) -> dict:
        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

        def _network_call():
            return self._call_api(client, messages)

        try:
            response, self.retry_count = retry_transient(_network_call)
        except APITimeoutError as exc:
            raise AIProviderUnavailable(
                "Provider request timed out.",
                safe_code="provider_timeout",
            ) from exc
        except APIConnectionError as exc:
            raise AIProviderUnavailable(
                "Provider connection failed.",
                safe_code="provider_connection_error",
            ) from exc
        except RateLimitError as exc:
            raise AIProviderUnavailable(
                "Provider rate limit exceeded.",
                safe_code="provider_rate_limited",
            ) from exc
        except APIStatusError as exc:
            status = exc.status_code
            if 500 <= status < 600:
                raise AIProviderUnavailable(
                    "Provider server error.",
                    safe_code="provider_server_error",
                ) from exc
            raise AIProviderUnavailable(
                "Provider request rejected.",
                safe_code="provider_request_rejected",
                retryable=False,
            ) from exc

        choice = response.choices[0]
        finish = choice.finish_reason

        if finish == "length":
            raise AIResponseInvalid(
                "Response truncated due to token limit.",
                safe_code="provider_response_truncated",
            )
        if finish != "stop":
            raise AIResponseInvalid(
                f"Unexpected finish reason: {finish}",
                safe_code="provider_unexpected_finish_reason",
            )

        content = choice.message.content
        if not content or not content.strip():
            raise AIResponseInvalid(
                "Empty response content from AI provider.",
                safe_code="provider_empty_response",
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIResponseInvalid(
                "Invalid JSON in AI response.",
                safe_code="provider_invalid_json",
            ) from exc

        if response.usage:
            self._record_usage(response.usage)

        return parsed

    @property
    def input_tokens(self):
        return getattr(self, "_last_input_tokens", 0)

    @property
    def output_tokens(self):
        return getattr(self, "_last_output_tokens", 0)

    @property
    def total_tokens(self):
        return getattr(self, "_last_total_tokens", 0)

    def _record_usage(self, usage):
        self._last_input_tokens = usage.prompt_tokens or 0
        self._last_output_tokens = usage.completion_tokens or 0
        self._last_total_tokens = usage.total_tokens or 0