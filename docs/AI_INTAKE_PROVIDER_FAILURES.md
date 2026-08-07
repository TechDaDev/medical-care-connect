# AI Intake Provider Failures

`apps/ai_intake/services/base.py` defines the provider error taxonomy and
retry policy. `apps/ai_intake/services/deepseek.py` implements the
OpenAI-compatible DeepSeek provider.

## Error taxonomy (safe codes)

- `intake_disabled` — AI intake not enabled.
- `provider_configuration_error` — missing API key/model; never retried.
- `provider_unavailable` — connection failure; retryable.
- `provider_timeout` — request timeout; retryable.
- `provider_connection_error` — connection error; retryable.
- `provider_rate_limited` — rate limit; retryable.
- `provider_server_error` — provider 5xx; retryable.
- `provider_request_rejected` — provider 4xx; NOT retried.
- `provider_empty_response` — empty content.
- `provider_response_truncated` — finish reason `length`.
- `provider_unexpected_finish_reason`.
- `provider_invalid_json`.
- `schema_validation_failed` — Pydantic validation failed.
- `semantic_validation_failed` — semantic/hallucination guard failed.
- `session_token_budget_exceeded`.

## Retry policy

- Automatic retry only for transient failures: connection, timeout, rate limit,
  provider 5xx.
- Bounded: `AI_INTAKE_MAX_RETRIES` (default 2), exponential backoff with jitter.
- Never retried: configuration errors, unsafe output, schema violations,
  injection violations, deterministic emergency stops, 4xx rejections.

## Patient-facing behavior

On any failure the patient receives a generic, localized message with safe
retry guidance and no provider details, no stack trace, no raw API exception
text. The session enters `temporarily_unavailable` (retryable) or `failed`
(non-retryable). Safe error codes, retryability, provider name, and timestamp
are retained on backend fields only.

## History and token budget

`apps/ai_intake/services/history.py`:

- `AI_INTAKE_MAX_HISTORY_MESSAGES` (20) — bounded recent turns.
- `AI_INTAKE_MAX_ANSWER_LENGTH` (2000) — patient answer cap.
- `AI_INTAKE_MAX_ASSISTANT_LENGTH` (1000).
- `AI_INTAKE_MAX_PROMPT_TOKENS` (6000) — prompt budget check.
- `AI_INTAKE_MAX_OUTPUT_TOKENS` (1200).
- `AI_INTAKE_MAX_SESSION_TOKENS` (40000) — session budget; when exceeded the
  session becomes `temporarily_unavailable`.
- Original patient messages always remain stored in the DB; only a bounded
  window is sent to the provider.
