"""Bounded conversation history and token budget.

Original patient messages always remain stored in the DB.
Only a bounded, role-separated window is sent to the provider.
"""

from django.conf import settings

from apps.ai_intake.constants import INTAKE_FIELDS

DEFAULT_MAX_HISTORY_MESSAGES = 20
DEFAULT_MAX_PROMPT_TOKENS = 6000
DEFAULT_MAX_OUTPUT_TOKENS = 1200
DEFAULT_MAX_SESSION_TOKENS = 40000
DEFAULT_MAX_ANSWER_LENGTH = 2000
DEFAULT_MAX_ASSISTANT_LENGTH = 1000
DEFAULT_MAX_QUESTIONS = 12

# Conservative estimate: ~1.5 tokens per Latin char, ~1 token per CJK/Arabic char.
_CHARS_PER_TOKEN = 3


def max_questions() -> int:
    return getattr(settings, "AI_INTAKE_MAX_QUESTIONS", DEFAULT_MAX_QUESTIONS)


def max_answer_length() -> int:
    return getattr(settings, "AI_INTAKE_MAX_ANSWER_LENGTH", DEFAULT_MAX_ANSWER_LENGTH)


def max_assistant_length() -> int:
    return getattr(settings, "AI_INTAKE_MAX_ASSISTANT_LENGTH", DEFAULT_MAX_ASSISTANT_LENGTH)


def max_history_messages() -> int:
    return getattr(settings, "AI_INTAKE_MAX_HISTORY_MESSAGES", DEFAULT_MAX_HISTORY_MESSAGES)


def max_prompt_tokens() -> int:
    return getattr(settings, "AI_INTAKE_MAX_PROMPT_TOKENS", DEFAULT_MAX_PROMPT_TOKENS)


def max_output_tokens() -> int:
    return getattr(settings, "AI_INTAKE_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS)


def max_session_tokens() -> int:
    return getattr(settings, "AI_INTAKE_MAX_SESSION_TOKENS", DEFAULT_MAX_SESSION_TOKENS)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def bounded_history(messages: list[dict], *, max_messages: int | None = None) -> list[dict]:
    """Return the most recent N role-separated messages.

    Always keeps the system prompt (index 0) when present.
    """
    limit = max_messages or max_history_messages()
    if len(messages) <= limit:
        return messages
    head = messages[:1] if messages and messages[0].get("role") == "system" else []
    tail = messages[-(limit - len(head)):] if head else messages[-limit:]
    return head + tail


def history_within_budget(messages: list[dict], *, budget: int | None = None) -> bool:
    limit = budget or max_prompt_tokens()
    total = sum(estimate_tokens(m.get("content", "")) for m in messages)
    return total <= limit


def session_within_budget(session) -> bool:
    return (session.total_tokens or 0) < max_session_tokens()


def field_allowlist_payload() -> dict:
    """Server-controlled intake context sent to the provider."""
    return {
        name: {
            "type": spec["type"],
            "universal": spec.get("universal", False),
            "conditional": spec.get("conditional", False),
        }
        for name, spec in INTAKE_FIELDS.items()
    }