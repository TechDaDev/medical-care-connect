import json
import logging

from django.conf import settings
from openai import APIStatusError, OpenAI, RateLimitError, APITimeoutError, APIConnectionError

from apps.ai_intake.services.base import (
    AIProvider,
    AIProviderConfigurationError,
    AIProviderUnavailable,
    AIResponseInvalid,
)

logger = logging.getLogger(__name__)


class DeepSeekProvider(AIProvider):
    """OpenAI-compatible provider for DeepSeek API."""

    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = settings.DEEPSEEK_BASE_URL
        self.model = settings.DEEPSEEK_MODEL
        self.timeout = settings.DEEPSEEK_TIMEOUT_SECONDS
        self.max_tokens = settings.DEEPSEEK_MAX_TOKENS
        self.temperature = settings.DEEPSEEK_TEMPERATURE
        self._validate_config()

    def _validate_config(self):
        if not self.api_key:
            raise AIProviderConfigurationError("DeepSeek API key is not configured.")
        if not self.model:
            raise AIProviderConfigurationError("DeepSeek model name is not configured.")

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

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except (
            APITimeoutError,
            APIConnectionError,
            RateLimitError,
            APIStatusError,
        ) as exc:
            logger.warning("DeepSeek API call failed: %s", exc)
            raise AIProviderUnavailable(str(exc)) from exc

        choice = response.choices[0]
        finish = choice.finish_reason

        if finish == "length":
            logger.warning("DeepSeek response truncated (finish_reason=length)")
            raise AIResponseInvalid("Response was truncated due to token limit.")

        if finish != "stop":
            logger.warning("Unexpected finish_reason: %s", finish)
            raise AIResponseInvalid(f"Unexpected finish reason: {finish}")

        content = choice.message.content
        if not content or not content.strip():
            raise AIResponseInvalid("Empty response content from AI provider.")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("DeepSeek returned invalid JSON: %s", exc)
            raise AIResponseInvalid("Invalid JSON in AI response.") from exc

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
