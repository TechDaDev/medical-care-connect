"""Deterministic intake completeness and next-question target engine.

DeepSeek may propose review. Only this engine decides:
- can_generate_review_summary;
- can_confirm;
- can_submit_to_doctor;
- missing blocking vs non-blocking fields;
- question budget.

The engine reads the per-field metadata map stored on the session
(see AIIntakeSession.field_metadata) and never trusts AI wording.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from types import SimpleNamespace

from django.conf import settings

from apps.ai_intake.constants import (
    CONDITIONAL_RELEVANCE_RULES,
    DECLINABLE_OPTIONAL,
    INTAKE_FIELDS,
    UNKNOWN_ALLOWED_UNIVERSAL,
    UNIVERSAL_REQUIRED,
    field_is_universal,
)

MAX_QUESTIONS_DEFAULT = 12


class CompletionReason(str, Enum):
    REQUIRED_INFORMATION_MISSING = "required_information_missing"
    CONDITIONAL_REQUIRED_MISSING = "conditional_required_missing"
    QUESTION_BUDGET_EXHAUSTED = "question_budget_exhausted"
    UNKNOWN_BLOCKING_REQUIRED_FIELD = "unknown_blocking_required_field"
    DECLINED_BLOCKING_REQUIRED_FIELD = "declined_blocking_required_field"
    UNCERTAIN_BLOCKING_REQUIRED_FIELD = "uncertain_blocking_required_field"
    REVIEW_READY = "review_ready"
    EMERGENCY_STOPPED = "emergency_stopped"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CompletenessResult:
    required_fields: list[str] = field(default_factory=list)
    relevant_fields: list[str] = field(default_factory=list)
    answered_fields: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)
    declined_fields: list[str] = field(default_factory=list)
    uncertain_fields: list[str] = field(default_factory=list)
    not_applicable_fields: list[str] = field(default_factory=list)
    missing_blocking_fields: list[str] = field(default_factory=list)
    missing_non_blocking_fields: list[str] = field(default_factory=list)
    questions_asked: int = 0
    questions_remaining: int = 0
    can_generate_review_summary: bool = False
    can_confirm: bool = False
    can_submit_to_doctor: bool = False
    emergency_stopped: bool = False
    reason_code: str = CompletionReason.REQUIRED_INFORMATION_MISSING.value


@dataclass(frozen=True)
class QuestionTargetPlan:
    """Backend-authoritative fields that may be asked next."""

    allowed_next_fields: list[str] = field(default_factory=list)
    preferred_next_field: str | None = None


def _max_questions() -> int:
    return getattr(settings, "AI_INTAKE_MAX_QUESTIONS", MAX_QUESTIONS_DEFAULT)


def _field_status(metadata: dict, field_name: str) -> str:
    entry = (metadata or {}).get(field_name) or {}
    return entry.get("status", "missing")


def _field_answered(metadata: dict, field_name: str) -> bool:
    status = _field_status(metadata, field_name)
    return status == "answered"


def evaluate_completeness(session) -> CompletenessResult:
    """Compute deterministic completeness for an intake session.

    session.field_metadata maps field -> {
        value, status, source, confidence, evidence_message_ids, confirmed_by_patient
    }
    """
    metadata = session.field_metadata or {}
    question_count = session.question_count
    status = session.status
    max_questions = _max_questions()

    answered = set()
    unknown = set()
    declined = set()
    uncertain = set()
    not_applicable = set()

    for name in INTAKE_FIELDS:
        st = _field_status(metadata, name)
        if st == "answered":
            answered.add(name)
        elif st == "unknown":
            unknown.add(name)
        elif st == "declined":
            declined.add(name)
        elif st == "uncertain":
            uncertain.add(name)
        elif st == "not_applicable":
            not_applicable.add(name)

    # Start with all universal fields as required.
    required = set(UNIVERSAL_REQUIRED)

    # Timing pair: onset OR duration satisfies both, so neither is required
    # when the other is answered.
    if "onset" in answered or "duration" in answered:
        answered.add("onset")
        answered.add("duration")
        required.discard("onset")
        required.discard("duration")

    # Apply conditional relevance from server side.
    # The AI may suggest relevance rules; backend stores them in
    # session.suggested_relevant_fields and maps them to conditional fields.
    suggested = set(getattr(session, "suggested_relevant_fields", []) or [])
    conditional_mapping = {
        "localized_symptom": {"location"},
        "recurrence_relevant": {"previous_episodes"},
        "pregnancy_relevant": {"pregnancy_possible"},
        "family_history_relevant": {"family_history"},
    }
    for rule in suggested:
        if rule in CONDITIONAL_RELEVANCE_RULES:
            required.update(conditional_mapping.get(rule, set()))

    missing_blocking = []
    missing_non_blocking = []
    reason = CompletionReason.REQUIRED_INFORMATION_MISSING

    # Registry order is deliberate question priority. Do not alphabetize it.
    for name in (field_name for field_name in INTAKE_FIELDS if field_name in required):
        st = _field_status(metadata, name)
        if st == "answered":
            continue
        if st == "not_applicable":
            continue
        if st == "unknown":
            if name in UNKNOWN_ALLOWED_UNIVERSAL:
                continue
            missing_blocking.append(name)
            reason = CompletionReason.UNKNOWN_BLOCKING_REQUIRED_FIELD
        elif st == "uncertain":
            if name in UNKNOWN_ALLOWED_UNIVERSAL:
                continue
            missing_blocking.append(name)
            reason = CompletionReason.UNCERTAIN_BLOCKING_REQUIRED_FIELD
        elif st == "declined":
            if name in DECLINABLE_OPTIONAL or name in UNKNOWN_ALLOWED_UNIVERSAL:
                continue
            missing_blocking.append(name)
            reason = CompletionReason.DECLINED_BLOCKING_REQUIRED_FIELD
        else:
            missing_blocking.append(name)

    # Optional relevant fields missing are non-blocking.
    for name in sorted(answered):
        if name not in required and not field_is_universal(name):
            continue

    if not missing_blocking and answered >= required - (unknown | declined | uncertain):
        # Timing pair handled above by adding both to answered.
        pass

    complete = not missing_blocking
    budget_exhausted = question_count >= max_questions

    if complete:
        reason = CompletionReason.REVIEW_READY
    elif budget_exhausted:
        reason = CompletionReason.QUESTION_BUDGET_EXHAUSTED

    can_review = complete
    can_confirm = complete and status in {"awaiting_patient_review"}
    can_submit = complete and status in {"confirmed"}

    # Emergency / terminal override.
    if status == "emergency_stopped":
        can_review = False
        can_confirm = False
        can_submit = False
        reason = CompletionReason.EMERGENCY_STOPPED
    if status == "cancelled":
        can_review = False
        can_confirm = False
        can_submit = False
        reason = CompletionReason.CANCELLED

    return CompletenessResult(
        required_fields=sorted(required),
        relevant_fields=sorted(
            {name for name in INTAKE_FIELDS if not field_is_universal(name)}
            & (answered | unknown | declined | uncertain | not_applicable)
        ),
        answered_fields=sorted(answered),
        unknown_fields=sorted(unknown),
        declined_fields=sorted(declined),
        uncertain_fields=sorted(uncertain),
        not_applicable_fields=sorted(not_applicable),
        missing_blocking_fields=missing_blocking,
        missing_non_blocking_fields=missing_non_blocking,
        questions_asked=question_count,
        questions_remaining=max(0, max_questions - question_count),
        can_generate_review_summary=can_review,
        can_confirm=can_confirm,
        can_submit_to_doctor=can_submit,
        emergency_stopped=status == "emergency_stopped",
        reason_code=reason.value,
    )


def question_target_plan(session) -> QuestionTargetPlan:
    """Return deterministic allowed and preferred next fields.

    Provider may word a question, but it cannot select outside this plan.
    Emergency/terminal/review-ready sessions never have a next target.
    """
    completeness = evaluate_completeness(session)
    if completeness.emergency_stopped or session.status == "cancelled":
        return QuestionTargetPlan()
    allowed = list(completeness.missing_blocking_fields)
    if not allowed:
        return QuestionTargetPlan()
    return QuestionTargetPlan(
        allowed_next_fields=allowed,
        preferred_next_field=allowed[0],
    )


def projected_question_target_plan(
    session,
    extracted_updates,
    uncertain_fields,
    suggested_relevant_fields,
) -> QuestionTargetPlan:
    """Plan next target against safe in-memory projection of provider updates."""
    metadata = deepcopy(session.field_metadata or {})
    for update in extracted_updates:
        existing = metadata.get(update.field) or {}
        if (
            existing.get("status") == "answered"
            and existing.get("source") == "patient_message"
        ):
            continue
        metadata[update.field] = {
            **existing,
            "value": update.value,
            "status": "uncertain" if update.certainty == "uncertain" else "answered",
            "source": "intake_extraction",
        }
    for field_name in uncertain_fields:
        if (metadata.get(field_name) or {}).get("status") != "answered":
            metadata[field_name] = {
                **(metadata.get(field_name) or {}),
                "status": "uncertain",
                "source": "intake_extraction",
            }
    suggested = list(dict.fromkeys([
        *(getattr(session, "suggested_relevant_fields", []) or []),
        *(suggested_relevant_fields or []),
    ]))
    projected = SimpleNamespace(
        field_metadata=metadata,
        question_count=session.question_count + 1,
        status=session.status,
        language=getattr(session, "language", "en"),
        suggested_relevant_fields=suggested,
    )
    return question_target_plan(projected)


def required_field_questions(session) -> list[str]:
    """Return allowlisted questions for fields that still block completion."""
    result = evaluate_completeness(session)
    questions = []
    for name in result.missing_blocking_fields:
        question = INTAKE_FIELDS.get(name, {}).get("question")
        if question:
            questions.append(question)
    return questions
