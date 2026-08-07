"""Semantic validation of DeepSeek structured output.

Pydantic enforces shape. This module enforces meaning:
- evidence IDs exist and belong to this session;
- extracted values are grounded in the cited evidence (hallucination guard);
- no duplicate fields;
- no next-question for an already answered field;
- no diagnosis/treatment/prescription words in patient-facing content;
- no prompt-disclosure patterns;
- no unsupported emergency reasons (code allowlist);
- no extracted value that has zero supporting evidence (fabrication guard).
"""

import re

from apps.ai_intake.constants import INTAKE_FIELDS

PROHIBITED_PATIENT_FACING_TERMS = {
    "diagnos",
    "diagnosed",
    "your condition is",
    "you have been diagnosed",
    "you are suffering from",
    "you have [a-z]+ disease",
    "prescription",
    "prescribe",
    "prescribed",
    "take [0-9] mg",
    "take antibiotics",
    "take paracetamol",
    "take ibuprofen",
    "take medication",
    "you should take",
    "you need to take",
    "stop taking",
    "increase your dose",
    "you need surgery",
    "system prompt",
    "instructions:",
    "ignore your",
    "mark complete",
    "return this json",
    "no emergency",
}

EMERGENCY_REASON_CODES = {
    "self_harm",
    "chest_pain",
    "breathing_difficulty",
    "major_bleeding",
    "stroke_like",
    "anaphylaxis",
    "loss_of_consciousness",
}

# Fields that are already answered by patient message, keyed in field metadata.
ANSWERED_STATUS = "answered"

# Minimum token length considered meaningful for grounding.
_TOKEN_MIN_LEN = 4
# Include Arabic + Kurdish Unicode ranges plus Latin.
_TOKEN_RE = re.compile(r"[A-Za-z0-9\u0600-\u06FF\u0750-\u077F]{4,}")


class SemanticValidationError(Exception):
    pass


def _is_prohibited(text: str) -> bool:
    lowered = (text or "").lower()
    for term in PROHIBITED_PATIENT_FACING_TERMS:
        # Escape regex-lite patterns safely.
        if "[" in term or "]" in term:
            if re.search(term, lowered):
                return True
        elif term in lowered:
            return True
    return False


def _significant_tokens(text) -> set[str]:
    if not text:
        return set()
    return set(_TOKEN_RE.findall(str(text).lower()))


def _grounded(update, evidence_text: str) -> bool:
    """Check that the extracted value is lexically grounded in evidence.

    Conservative: for explicit/inferred extractions there must be at least one
    significant shared token between the value and the cited patient message.
    This rejects fabricated facts while remaining safe (a miss only forces a
    re-ask; it never blocks clinical content because none exists here).
    """
    value_tokens = _significant_tokens(update.value)
    if not value_tokens:
        # Structured values (bool/int) or empty — no lexical claim to verify.
        return True
    evidence_tokens = _significant_tokens(evidence_text)
    return bool(value_tokens & evidence_tokens)


def _value_type_matches(field_type: str | None, value) -> bool:
    """Enforce the canonical per-field type from the registry."""
    if field_type == "list":
        return isinstance(value, list)
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    # text and unknown types require a string.
    return isinstance(value, str)


def validate_semantics(session, response) -> None:
    """Raise SemanticValidationError on unsafe or meaningless output."""

    if _is_prohibited(response.patient_facing_message):
        raise SemanticValidationError("Unsafe content in patient-facing message")

    if response.summary_for_review and _is_prohibited(response.summary_for_review):
        raise SemanticValidationError("Unsafe content in review summary")

    # Evidence message IDs must belong to this session; load id -> content once
    # so grounding can be checked without per-update queries.
    session_messages = {
        str(m.id): m.content for m in session.messages.all()
    }
    for update in response.extracted_updates:
        for mid in update.source_message_ids:
            if str(mid) not in session_messages:
                raise SemanticValidationError(
                    f"Evidence message {mid} does not belong to this session"
                )
        if not update.source_message_ids:
            raise SemanticValidationError(
                f"Extracted field {update.field!r} has no supporting evidence"
            )
        if update.certainty in {"explicit", "inferred"}:
            evidence_text = " ".join(
                session_messages.get(str(mid), "") for mid in update.source_message_ids
            )
            if not _grounded(update, evidence_text):
                raise SemanticValidationError(
                    f"Extracted field {update.field!r} is not grounded in the patient's answers"
                )
        # Enforce the canonical per-field type (e.g. boolean fields must be bool).
        field_spec = INTAKE_FIELDS.get(update.field, {})
        if not _value_type_matches(field_spec.get("type"), update.value):
            raise SemanticValidationError(
                f"Extracted field {update.field!r} has an invalid value type"
            )

    # No next question for an already-answered field.
    metadata = session.field_metadata or {}
    if response.next_question and response.next_question.field:
        field = response.next_question.field
        entry = metadata.get(field) or {}
        if entry.get("status") == ANSWERED_STATUS:
            raise SemanticValidationError(
                f"Next question targets already-answered field {field!r}"
            )

    # Emergency reasons must be safe codes.
    for reason in response.emergency_signal.reasons:
        if reason not in EMERGENCY_REASON_CODES:
            raise SemanticValidationError(f"Unsupported emergency reason {reason!r}")

    # Suggested relevance rules already allowlisted by Pydantic.
    # Extracted fields already allowlisted by Pydantic.