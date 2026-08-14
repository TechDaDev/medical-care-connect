"""
AI intake deterministic orchestration service.

The backend controls: ownership, state, transitions, idempotency, sequence
allocation, emergency stop, completion gates, confirmation, submission,
draft creation, notifications, and audits.

DeepSeek only supplies conversational wording + structured extraction.
"""

import json
import logging
from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.ai_intake.constants import (
    INTAKE_FIELDS,
    VALID_CERTAINTY,
    VALID_FIELD_SOURCES,
    VALID_FIELD_STATUSES,
)
from apps.ai_intake.models import (
    AIIntakeMessage,
    AIIntakeSession,
    IntakeIdempotencyLedger,
    IntakeSessionStatus,
)
from apps.ai_intake.prompts import PROMPT_VERSION, build_ai_messages
from apps.ai_intake.schemas import IntakeTurnResponse
from apps.ai_intake.services.base import (
    AIProviderConfigurationError,
    AIProviderDisabled,
    AIProviderUnavailable,
    AIResponseInvalid,
    AISemanticValidationError,
)
from apps.ai_intake.services.completeness import (
    CompletionReason,
    evaluate_completeness,
)
from apps.ai_intake.services.deepseek import DeepSeekProvider
from apps.ai_intake.services.emergency import screen_patient_input
from apps.ai_intake.services.history import (
    bounded_history,
    max_answer_length,
    max_history_messages,
    max_questions,
    session_within_budget,
)
from apps.ai_intake.services.semantic_validation import (
    SemanticValidationError,
    validate_semantics,
)
from apps.ai_intake.services.state import (
    ACTIVE_QUESTIONING_STATES,
    CONFIRMABLE_STATES,
    CORRECTABLE_STATES,
    RETRYABLE_STATES,
    REVIEWABLE_STATES,
    STATE_CHOICES,
    IllegalTransition,
    transition_state,
)
from apps.consultations.models import ConsultationStatus

logger = logging.getLogger(__name__)

PATIENT_SESSION_QUERY = "consultation__patient__user"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _audit(event_type, *, actor_id, actor_role="patient", target_id=None,
           metadata=None, severity="info", result="success"):
    from apps.core.audit_service import create_audit_event
    from apps.core.models import AuditEventCategory

    create_audit_event(
        event_type,
        AuditEventCategory.CONSULTATION,
        severity=severity,
        result=result,
        actor_id=str(actor_id),
        actor_role=actor_role,
        target_type="intake_session",
        target_id=str(target_id) if target_id else None,
        metadata=metadata or {},
    )


def _notify_intake_submitted(consultation):
    from apps.notifications.models import Notification, NotificationType

    Notification.objects.get_or_create(
        recipient=consultation.doctor.user,
        notification_type=NotificationType.INTAKE_COMPLETED,
        consultation=consultation,
        defaults={
            "title": "Intake ready for review",
            "body": "The patient has completed and confirmed their intake.",
        },
    )


def _escalate_consultation(session: AIIntakeSession) -> None:
    """Atomic emergency escalation — consultation, notification, audit once."""
    consultation = session.consultation
    if consultation.status == ConsultationStatus.EMERGENCY_ESCALATED:
        return
    consultation.status = ConsultationStatus.EMERGENCY_ESCALATED
    consultation.save(update_fields=["status", "updated_at"])
    if not session.emergency_escalated_at:
        session.emergency_escalated_at = timezone.now()
        session.save(update_fields=["emergency_escalated_at", "updated_at"])

    from apps.core.audit_service import create_audit_event
    from apps.core.models import AuditEventCategory
    from apps.notifications.models import Notification, NotificationType

    create_audit_event(
        "patient_intake_emergency_escalated",
        AuditEventCategory.CONSULTATION,
        actor_id=str(consultation.patient.user_id),
        actor_role="patient",
        target_type="consultation",
        target_id=str(consultation.id),
        metadata={"level": session.emergency_level},
    )
    Notification.objects.get_or_create(
        recipient=consultation.doctor.user,
        notification_type=NotificationType.EMERGENCY_ESCALATED,
        consultation=consultation,
        defaults={
            "title": "Consultation requires urgent review",
            "body": "A consultation has entered emergency escalation.",
        },
    )


def _get_provider():
    if not settings.AI_INTAKE_ENABLED:
        raise AIProviderDisabled("AI intake is not enabled.")
    provider_name = (settings.AI_INTAKE_PROVIDER or "").lower()
    if provider_name == "deepseek":
        return DeepSeekProvider()
    if provider_name == "mock":
        if not settings.DEBUG or not getattr(settings, "E2E_LOCAL_ALLOWED", False):
            raise AIProviderConfigurationError(
                "Deterministic mock provider is restricted to explicit local E2E runs.",
                safe_code="mock_provider_forbidden",
            )
        from apps.ai_intake.services.mock import DeterministicE2EProvider

        return DeterministicE2EProvider()
    raise AIProviderConfigurationError(
        f"Unsupported AI provider: {provider_name}",
        safe_code="unsupported_provider",
    )


def _next_sequence(session: AIIntakeSession) -> int:
    last = (
        AIIntakeMessage.objects.filter(session=session)
        .order_by("-sequence_number")
        .values_list("sequence_number", flat=True)
        .first()
    )
    return (last or 0) + 1


def _safe_generic_error() -> str:
    return _(
        "We encountered a technical issue. Please try again or contact support."
    )


# ── Start ────────────────────────────────────────────────────────────────────


def start_intake_session(consultation, language: str = "en") -> AIIntakeSession:
    """Start or resume an AI intake session (no provider call at start)."""
    defaults = dict(
        status=IntakeSessionStatus.IN_PROGRESS,
        started_at=timezone.now(),
        language=language,
        ai_provider=settings.AI_INTAKE_PROVIDER or "deepseek",
        ai_model=settings.DEEPSEEK_MODEL or "",
        prompt_version=PROMPT_VERSION,
        schema_version="mcc-intake-v2",
        question_count=0,
        field_metadata={},
        collected_data={},
        missing_fields=[],
        suggested_relevant_fields=[],
    )
    session, created = AIIntakeSession.objects.get_or_create(
        consultation=consultation,
        defaults=defaults,
    )
    if created or session.status in {IntakeSessionStatus.NOT_STARTED, IntakeSessionStatus.FAILED}:
        for field, value in defaults.items():
            setattr(session, field, value)
        session.status = IntakeSessionStatus.IN_PROGRESS
        session.save()
    if consultation.status == ConsultationStatus.ACCEPTED:
        consultation.status = ConsultationStatus.INTAKE_IN_PROGRESS
        consultation.save(update_fields=["status", "updated_at"])
    return session


# ── Answer processing ────────────────────────────────────────────────────────


class IntakeProcessingError(Exception):
    """Raised when patient cannot send another answer (HTTP 409)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _assert_can_answer(session: AIIntakeSession) -> None:
    # Patients may keep answering while questioning, in a retryable failure
    # state, or when returning to questioning from review/correction.
    if session.status not in (
        ACTIVE_QUESTIONING_STATES | RETRYABLE_STATES | REVIEWABLE_STATES
    ):
        raise IntakeProcessingError("intake_session_closed")


def _apply_extracted_updates(
    session: AIIntakeSession,
    validated: IntakeTurnResponse,
    patient_message: AIIntakeMessage,
) -> None:
    """Merge AI-extracted updates into field_metadata under strict rules.

    - never overwrite an explicit patient answer with inferred AI data;
    - every extracted update must carry evidence;
    - uncertain extractions are marked uncertain and exposed for review.
    """
    metadata = session.field_metadata or {}
    for update in validated.extracted_updates:
        existing = metadata.get(update.field) or {}
        existing_status = existing.get("status", "missing")
        if existing_status == "answered" and existing.get("source") == "patient_message":
            # Preserve explicit patient-reported value; AI may only add uncertainty
            continue
        evidence_ids = [str(mid) for mid in update.source_message_ids]
        if update.certainty == "uncertain":
            status = "uncertain"
        else:
            status = "answered"
        metadata[update.field] = {
            "value": update.value,
            "status": status,
            "source": "intake_extraction",
            "confidence": _certainty_to_confidence(update.certainty),
            "evidence_message_ids": evidence_ids,
            "confirmed_by_patient": False,
        }
        # Explicit patient answers always retain patient_message source priority
        if status == "answered" and existing_status == "answered":
            metadata[update.field]["source"] = existing.get(
                "source", existing["source"]
            )
    for field_name in validated.uncertain_fields:
        entry = metadata.get(field_name) or {}
        if entry.get("status") in (None, "missing", "answered"):
            if entry.get("status") == "answered":
                continue
            metadata[field_name] = {
                "value": entry.get("value"),
                "status": "uncertain",
                "source": "intake_extraction",
                "confidence": "low",
                "evidence_message_ids": [],
                "confirmed_by_patient": False,
            }
    session.field_metadata = metadata
    _sync_collected_data(session)


def _certainty_to_confidence(certainty: str) -> str:
    mapping = {"explicit": "high", "inferred": "medium", "uncertain": "low"}
    return mapping.get(certainty, "low")


def _sync_collected_data(session: AIIntakeSession) -> None:
    """Derive backward-compatible collected_data from field_metadata."""
    metadata = session.field_metadata or {}
    collected: dict = {}
    for name, spec in INTAKE_FIELDS.items():
        entry = metadata.get(name) or {}
        if entry.get("status") == "answered" and entry.get("value") is not None:
            collected[name] = entry["value"]
    session.collected_data = collected


def _sync_missing_fields(session: AIIntakeSession) -> None:
    result = evaluate_completeness(session)
    session.missing_fields = result.missing_blocking_fields


def _merge_patient_evidence(session, patient_message: AIIntakeMessage) -> None:
    """Record patient-reported evidence on the session before AI call.

    The raw message is always the patient's own record.  Structured
    extraction happens after the provider returns.  current_question
    is never replaced with patient content.
    """
    # Evidence lives in AIIntakeMessage rows, intrinsically linked to the
    # session.  No additional mutation needed here.
    pass


def _fallback_question(session) -> str:
    from apps.ai_intake.services.completeness import required_field_questions

    questions = required_field_questions(session)
    if questions:
        return questions[0]
    return _("Is there anything else you would like to share before we finish?")


def _build_evidence_messages(session: AIIntakeSession) -> list[dict]:
    """Return bounded role-separated history, EXCLUDING the current turn.

    Patient answers appear exactly once each — derived from stored messages.
    Each message carries its DB id so the provider can cite real evidence
    (source_message_ids) instead of inventing references.
    """
    messages = []
    for m in session.messages.order_by("sequence_number"):
        messages.append({
            "role": m.role,
            "content": m.content,
            "message_id": str(m.id),
        })
    return bounded_history(messages, max_messages=max_history_messages())


def _record_answer_ledger(
    session, request_id, *, provider_calls, state_before, state_after, token_delta, result_code
) -> bool:
    """Insert idempotency ledger; returns False when duplicate already exists."""
    _, created = IntakeIdempotencyLedger.objects.get_or_create(
        session=session,
        action="answer",
        client_request_id=request_id,
        defaults={
            "result_code": result_code,
            "provider_call_count": provider_calls,
            "state_before": state_before,
            "state_after": state_after,
            "token_delta": token_delta,
            "prompt_version": PROMPT_VERSION,
        },
    )
    return created


def process_intake_answer(
    session: AIIntakeSession,
    patient_message: str,
    client_request_id: UUID | None = None,
) -> tuple[AIIntakeSession, dict]:
    """Process one patient answer transactionally.

    Flow:
      1. emergency deterministic screen (before ANY normal persistence);
      2. if emergency → save patient message with flags, stop, escalate, return;
      3. idempotency check (duplicate request returns existing result);
      4. save patient message once (transactional sequence);
      5. build bounded evidence history;
      6. call provider once (with bounded transient retries);
      7. validate schema + semantics;
      8. apply extracted updates, recompute completeness from backend;
      9. decide review / continue; save assistant message; audit.
    """
    patient_message = (patient_message or "").strip()
    if not patient_message:
        raise ValueError("patient_message is required")

    with transaction.atomic():
        session = AIIntakeSession.objects.select_for_update().get(pk=session.pk)

        # ── 1. Deterministic emergency screen BEFORE any normal-flow persistence.
        emergency = screen_patient_input(patient_message)

        # ── Idempotency check first: a replayed request (same client_request_id)
        # ── returns the existing result even when the session is now closed.
        if client_request_id:
            existing = AIIntakeMessage.objects.filter(
                session=session, client_request_id=client_request_id
            ).first()
            if existing:
                # Replay: return current state, no provider call, no duplicate save.
                result = _answer_replay_response(session, existing)
                _record_answer_ledger(
                    session, client_request_id,
                    provider_calls=0,
                    state_before=session.status,
                    state_after=session.status,
                    token_delta=0,
                    result_code="replayed",
                )
                return session, result

        _assert_can_answer(session)

        # ── Returning to questioning from review/correction.
        if session.status in REVIEWABLE_STATES:
            session.status = IntakeSessionStatus.IN_PROGRESS
            session.save(update_fields=["status", "updated_at"])

        # ── 2. Save patient message once with transactional sequence.
        if emergency["detected"]:
            patient_msg = AIIntakeMessage.objects.create(
                session=session,
                role="patient",
                content=patient_message,
                sequence_number=_next_sequence(session),
                emergency_flags=emergency["reasons"],
                client_request_id=client_request_id,
            )
            session.emergency_detected = True
            session.emergency_level = emergency["level"]
            session.emergency_reasons = emergency["reasons"]
            session.status = IntakeSessionStatus.EMERGENCY_STOPPED
            if not session.started_at:
                session.started_at = timezone.now()
            session.save(update_fields=[
                "emergency_detected", "emergency_level", "emergency_reasons",
                "status", "started_at", "updated_at",
            ])
            _escalate_consultation(session)
            _audit(
                "patient_intake_answer_accepted",
                actor_id=session.consultation.patient.user_id,
                target_id=session.id,
                metadata={"emergency_level": emergency["level"]},
            )
            if client_request_id:
                _record_answer_ledger(
                    session, client_request_id,
                    provider_calls=0,
                    state_before="in_progress",
                    state_after=session.status,
                    token_delta=0,
                    result_code="emergency_stopped",
                )
            return session, _make_emergency_response(session, emergency)

        patient_msg = AIIntakeMessage.objects.create(
            session=session,
            role="patient",
            content=patient_message,
            sequence_number=_next_sequence(session),
            client_request_id=client_request_id,
        )

        # ── 3. Token/session budget guard.
        if not session_within_budget(session):
            session.status = IntakeSessionStatus.TEMPORARILY_UNAVAILABLE
            session.error_code = "session_token_budget_exceeded"
            session.save(update_fields=["status", "error_code", "updated_at"])
            return session, _make_error_response(
                safe_code="session_token_budget_exceeded",
                retryable=False,
            )

        # ── 4. Build evidence + call provider once.
        evidence = _build_evidence_messages(session)
        completeness = evaluate_completeness(session)
        max_q = max_questions()

        try:
            provider = _get_provider()
        except (AIProviderDisabled, AIProviderConfigurationError) as exc:
            session.status = IntakeSessionStatus.FAILED
            session.error_code = exc.safe_code
            session.save(update_fields=["status", "error_code", "updated_at"])
            return session, _make_error_response(safe_code=exc.safe_code, retryable=False)

        messages = build_ai_messages(
            session,
            history_messages=evidence,
            completeness=completeness,
            max_questions_budget=max_q,
        )

        retry_count = 0
        try:
            raw, retry_count = _call_with_retries(provider, messages)
        except AIProviderUnavailable as exc:
            if exc.retryable:
                session.status = IntakeSessionStatus.TEMPORARILY_UNAVAILABLE
                session.error_code = exc.safe_code
                session.retry_count = retry_count
                session.save(update_fields=[
                    "status", "error_code", "retry_count", "updated_at",
                ])
                return session, _make_error_response(safe_code=exc.safe_code, retryable=True)
            # Non-retryable provider rejection (e.g. 4xx) — safe terminal-ish failure.
            session.status = IntakeSessionStatus.FAILED
            session.error_code = exc.safe_code
            session.save(update_fields=["status", "error_code", "updated_at"])
            return session, _make_error_response(safe_code=exc.safe_code, retryable=False)

        except (AIResponseInvalid, AISemanticValidationError) as exc:
            session.status = IntakeSessionStatus.TEMPORARILY_UNAVAILABLE
            session.error_code = exc.safe_code
            session.save(update_fields=["status", "error_code", "updated_at"])
            return session, _make_error_response(safe_code=exc.safe_code, retryable=False)

        # ── 5. Schema validation.
        try:
            validated = IntakeTurnResponse(**raw)
        except Exception as exc:
            session.status = IntakeSessionStatus.TEMPORARILY_UNAVAILABLE
            session.error_code = "schema_validation_failed"
            session.save(update_fields=["status", "error_code", "updated_at"])
            return session, _make_error_response(
                safe_code="schema_validation_failed", retryable=False
            )

        # ── 6. Semantic validation.
        try:
            validate_semantics(session, validated)
        except SemanticValidationError as exc:
            session.status = IntakeSessionStatus.TEMPORARILY_UNAVAILABLE
            session.error_code = "semantic_validation_failed"
            session.save(update_fields=["status", "error_code", "updated_at"])
            return session, _make_error_response(
                safe_code="semantic_validation_failed", retryable=False
            )

        # ── 7. Apply extraction + deterministically recompute completeness.
        _apply_extracted_updates(session, validated, patient_msg)
        _merge_patient_evidence(session, patient_msg)

        session.question_count += 1
        if validated.next_question:
            session.current_question = validated.next_question.text or _fallback_question(session)
        else:
            session.current_question = _fallback_question(session)
        session.input_tokens += provider.input_tokens or 0
        session.output_tokens += provider.output_tokens or 0
        session.total_tokens += provider.total_tokens or 0
        session.provider_calls += 1
        session.retry_count = max(session.retry_count, retry_count)
        session.last_ai_request_at = timezone.now()
        session.error_code = ""

        # Suggested relevance rules (allowlisted by Pydantic).
        if validated.suggested_relevant_fields:
            session.suggested_relevant_fields = list(
                dict.fromkeys(session.suggested_relevant_fields or [] + validated.suggested_relevant_fields)
            )

        new_completeness = evaluate_completeness(session)
        _sync_missing_fields(session)

        # Emergency signal from AI — may only escalate, never reduce.
        ai_signal = validated.emergency_signal
        if ai_signal.detected and not session.emergency_detected:
            session.emergency_detected = True
            session.emergency_level = "emergency" if ai_signal.level == "emergency" else "urgent"
            session.emergency_reasons = ai_signal.reasons
            session.status = IntakeSessionStatus.EMERGENCY_STOPPED
            _escalate_consultation(session)
            session.save()
            AIIntakeMessage.objects.create(
                session=session,
                role="assistant",
                content=validated.patient_facing_message,
                sequence_number=_next_sequence(session),
                structured_data=None,
            )
            return session, _make_emergency_response(session, {
                "level": session.emergency_level,
                "reasons": session.emergency_reasons,
            })

        # ── 8. Backend completeness gate — the AI cannot force completion.
        if new_completeness.can_generate_review_summary:
            session.status = IntakeSessionStatus.AWAITING_PATIENT_REVIEW
            session.completed_at = timezone.now()
            session.patient_review_summary = _build_review_payload(
                session, validated.summary_for_review
            )
        else:
            session.status = IntakeSessionStatus.IN_PROGRESS

        session.save()

        # ── 9. Save assistant message exactly once.
        AIIntakeMessage.objects.create(
            session=session,
            role="assistant",
            content=validated.patient_facing_message,
            sequence_number=_next_sequence(session),
            structured_data={
                "next_question_field": validated.next_question.field if validated.next_question else None,
                "proposed_review": validated.conversation_status == "propose_review",
                "confirmed_by_backend_gate": new_completeness.can_generate_review_summary,
            },
        )

        if client_request_id:
            _record_answer_ledger(
                session, client_request_id,
                provider_calls=1 + (session.retry_count if session.retry_count > 0 else 0),
                state_before="in_progress",
                state_after=session.status,
                token_delta=provider.total_tokens or 0,
                result_code="ok",
            )

        _audit(
            "patient_intake_answer_accepted",
            actor_id=session.consultation.patient.user_id,
            target_id=session.id,
            metadata={
                "state": session.status,
                "provider_calls": 1,
                "prompt_version": PROMPT_VERSION,
            },
        )

        return session, _make_turn_response(session, validated, new_completeness)


def _call_with_retries(provider, messages):
    """Call provider once; retry_transient handles bounded retries."""
    from apps.ai_intake.services.base import retry_transient

    def _call():
        return provider.generate_structured_response(messages)

    try:
        result, retries = retry_transient(_call)
        return result, retries
    except Exception:
        raise


def _answer_replay_response(session, existing_message):
    return {
        "session_status": session.status,
        "patient_facing_message": session.current_question or "",
        "next_question": None,
        "question_count": session.question_count,
        "emergency_detected": session.emergency_detected,
        "emergency_level": session.emergency_level,
        "record_ready": session.status == IntakeSessionStatus.AWAITING_PATIENT_REVIEW,
        "submitted_to_doctor": session.status == IntakeSessionStatus.SUBMITTED_TO_DOCTOR,
        "replayed": True,
    }


def _make_turn_response(session, validated, completeness):
    return {
        "conversation_status": (
            "propose_review"
            if session.status == IntakeSessionStatus.AWAITING_PATIENT_REVIEW
            else "needs_more_information"
        ),
        "session_status": session.status,
        "patient_facing_message": validated.patient_facing_message,
        "next_question": (
            validated.next_question.text if validated.next_question else None
        ),
        "next_question_field": (
            validated.next_question.field if validated.next_question else None
        ),
        "question_count": session.question_count,
        "emergency_detected": session.emergency_detected,
        "emergency_level": session.emergency_level,
        "record_ready": session.status == IntakeSessionStatus.AWAITING_PATIENT_REVIEW,
        "submitted_to_doctor": session.status == IntakeSessionStatus.SUBMITTED_TO_DOCTOR,
        "completeness": {
            "missing_blocking_fields": completeness.missing_blocking_fields,
            "can_generate_review_summary": completeness.can_generate_review_summary,
            "reason_code": completeness.reason_code,
            "questions_remaining": completeness.questions_remaining,
        },
    }


def _make_emergency_response(session, emergency):
    return {
        "conversation_status": "emergency",
        "session_status": session.status,
        "patient_facing_message": _emergency_message(emergency["level"]),
        "next_question": None,
        "emergency_detected": True,
        "emergency_level": emergency["level"],
        "emergency_reasons": emergency["reasons"],
        "question_count": session.question_count,
        "record_ready": False,
        "submitted_to_doctor": False,
    }


def _emergency_message(level: str) -> str:
    if level == "emergency":
        return _(
            "Your description suggests this may be a life-threatening emergency. "
            "MCC is not an emergency service. Please seek immediate emergency "
            "care by calling your local emergency number."
        )
    return _(
        "What you described sounds urgent. A clinician may review your case. "
        "If your condition worsens, please seek immediate medical attention."
    )


def _make_error_response(safe_code: str, retryable: bool) -> dict:
    return {
        "conversation_status": "error",
        "session_status": "temporarily_unavailable" if retryable else "failed",
        "patient_facing_message": _safe_generic_error(),
        "next_question": None,
        "emergency_detected": False,
        "emergency_level": "none",
        "emergency_reasons": [],
        "question_count": 0,
        "record_ready": False,
        "submitted_to_doctor": False,
        "error_code": safe_code,
        "retryable": retryable,
    }


# ── Review payload ───────────────────────────────────────────────────────────


def _build_review_payload(session, ai_summary: str | None) -> dict:
    """Build patient-facing structured review from field metadata."""
    metadata = session.field_metadata or {}
    sections = {}
    for name, spec in INTAKE_FIELDS.items():
        entry = metadata.get(name)
        if not entry or entry.get("status") not in {
            "answered", "unknown", "declined", "uncertain", "not_applicable",
        }:
            continue
        sections[name] = {
            "value": entry.get("value"),
            "status": entry.get("status"),
            "source": entry.get("source"),
            "evidence_message_ids": entry.get("evidence_message_ids", []),
            "confirmed_by_patient": entry.get("confirmed_by_patient", False),
        }
    return {
        "sections": sections,
        "ai_generated_summary": ai_summary,
        "generated_at": timezone.now().isoformat(),
        "prompt_version": PROMPT_VERSION,
        "schema_version": "mcc-intake-v2",
    }


# ── Correction / Confirmation / Submission ──────────────────────────────────


def get_review_summary(session: AIIntakeSession) -> dict:
    if session.patient_review_summary:
        return session.patient_review_summary
    return _build_review_payload(session, None)


class IntakeNotReviewableError(Exception):
    pass


class IntakeNotConfirmableError(Exception):
    pass


class IntakeNotSubmittableError(Exception):
    pass


class StaleIntakeError(Exception):
    pass


def _stale(session, expected_updated_at) -> bool:
    """Compare expected_updated_at (ISO string or datetime) with session.updated_at.

    Views pass a parsed datetime (DRF DateTimeField).  Direct callers may pass
    an ISO string.  parse_datetime raises TypeError for non-string input, so
    normalize first.
    """
    from django.utils.dateparse import parse_datetime

    if isinstance(expected_updated_at, str):
        expected = parse_datetime(expected_updated_at)
    elif isinstance(expected_updated_at, datetime):
        expected = expected_updated_at
    else:
        expected = None
    if expected is None:
        return True
    current = session.updated_at
    if current is None:
        return True
    # Normalize naive/aware mismatch (SQLite stores naive; DRF may return aware).
    if timezone.is_naive(expected) and timezone.is_aware(current):
        expected = timezone.make_aware(expected, timezone.get_current_timezone())
    elif timezone.is_aware(expected) and timezone.is_naive(current):
        current = timezone.make_aware(current, timezone.get_current_timezone())
    # Compare with microsecond tolerance (DRF serializes with +00:00).
    return abs((current - expected).total_seconds()) > 0.000001


def apply_corrections(
    session: AIIntakeSession,
    corrections: dict,
    *,
    expected_updated_at,
    client_request_id: UUID,
) -> dict:
    """Apply patient corrections to field metadata.

    - field must be allowlisted;
    - value, status must be valid;
    - protected fields cannot be corrected (confirmed storage only);
    - corrected value replaces AI extraction, not the original answer text.
    """
    with transaction.atomic():
        session = AIIntakeSession.objects.select_for_update().get(pk=session.pk)
        if session.status not in CORRECTABLE_STATES:
            raise IntakeNotReviewableError("intake_not_reviewable")
        if _stale(session, expected_updated_at):
            raise StaleIntakeError("stale_intake")

        metadata = session.field_metadata or {}
        changed_fields = []
        for name, patch in corrections.items():
            if name not in INTAKE_FIELDS:
                continue
            patch_value = patch.get("value") if isinstance(patch, dict) else None
            patch_status = (
                patch.get("status") if isinstance(patch, dict) else None
            )
            if patch_status and patch_status not in VALID_FIELD_STATUSES:
                continue
            if patch_status == "answered" and patch_value is None:
                continue
            existing_entry = metadata.get(name) or {}
            new_status = patch_status or "answered"
            metadata[name] = {
                "value": patch_value if patch_status != "unknown" else None,
                "status": new_status,
                "source": "patient_correction",
                "confidence": existing_entry.get("confidence", "high"),
                "evidence_message_ids": existing_entry.get("evidence_message_ids", []),
                "confirmed_by_patient": False,
            }
            changed_fields.append(name)

        if not changed_fields:
            raise ValueError("no_valid_corrections")

        session.field_metadata = metadata
        _sync_collected_data(session)
        _sync_missing_fields(session)
        session.status = IntakeSessionStatus.AWAITING_PATIENT_REVIEW
        session.patient_review_summary = _build_review_payload(session, None)
        session.save()

        IntakeIdempotencyLedger.objects.get_or_create(
            session=session,
            action="correction",
            client_request_id=client_request_id,
            defaults={
                "result_code": "ok",
                "state_before": "correction_in_progress",
                "state_after": session.status,
                "prompt_version": PROMPT_VERSION,
            },
        )
        _audit(
            "patient_intake_correction",
            actor_id=session.consultation.patient.user_id,
            target_id=session.id,
            metadata={"changed_fields": changed_fields},
        )
        return _build_review_payload(session, None)


def confirm_intake(
    session: AIIntakeSession,
    *,
    expected_updated_at: str,
    client_request_id: UUID,
) -> dict:
    """Confirm the reviewed summary. Idempotent. No doctor notification."""
    with transaction.atomic():
        session = AIIntakeSession.objects.select_for_update().get(pk=session.pk)
        if session.status in {"confirmed"}:
            # Idempotent replay.
            return _confirmation_response(session, replayed=True)
        if session.status not in CONFIRMABLE_STATES:
            raise IntakeNotConfirmableError("intake_not_reviewable")
        if _stale(session, expected_updated_at):
            raise StaleIntakeError("stale_intake")

        completeness = evaluate_completeness(session)
        if not completeness.can_generate_review_summary:
            raise IntakeNotConfirmableError("required_information_missing")

        session.status = IntakeSessionStatus.CONFIRMED
        session.confirmed_at = timezone.now()
        session.confirmation_snapshot = {
            "field_metadata": session.field_metadata,
            "collected_data": session.collected_data,
            "confirmed_at": session.confirmed_at.isoformat(),
            "prompt_version": PROMPT_VERSION,
            "schema_version": "mcc-intake-v2",
        }
        # Mark fields confirmed.
        metadata = session.field_metadata or {}
        for name, entry in metadata.items():
            if isinstance(entry, dict) and entry.get("status") in {
                "answered", "unknown", "declined", "uncertain", "not_applicable",
            }:
                entry["confirmed_by_patient"] = True
                metadata[name] = entry
        session.field_metadata = metadata
        session.save()

        IntakeIdempotencyLedger.objects.get_or_create(
            session=session,
            action="confirm",
            client_request_id=client_request_id,
            defaults={
                "result_code": "ok",
                "state_before": "awaiting_patient_review",
                "state_after": session.status,
                "prompt_version": PROMPT_VERSION,
            },
        )
        _audit(
            "patient_intake_confirmed",
            actor_id=session.consultation.patient.user_id,
            target_id=session.id,
            metadata={"state": session.status},
        )
        return _confirmation_response(session, replayed=False)


def _confirmation_response(session, *, replayed: bool) -> dict:
    completeness = evaluate_completeness(session)
    return {
        "session_status": session.status,
        "confirmed_at": session.confirmed_at.isoformat() if session.confirmed_at else None,
        "can_submit_to_doctor": completeness.can_submit_to_doctor,
        "replayed": replayed,
    }


def submit_intake(
    session: AIIntakeSession,
    *,
    expected_updated_at: str,
    client_request_id: UUID,
) -> dict:
    """Submit confirmed intake to the doctor.

    - atomic transaction, row locks on session + consultation;
    - exactly one medical-record draft;
    - consultation -> DOCTOR_REVIEW once;
    - one doctor notification; one audit;
    - idempotent via client_request_id.
    """
    with transaction.atomic():
        session = AIIntakeSession.objects.select_for_update().get(pk=session.pk)
        if session.status == IntakeSessionStatus.SUBMITTED_TO_DOCTOR:
            session.consultation.refresh_from_db()
            return _submission_response(session, replayed=True)
        if session.status != IntakeSessionStatus.CONFIRMED:
            raise IntakeNotSubmittableError("intake_not_confirmed")
        if _stale(session, expected_updated_at):
            raise StaleIntakeError("stale_intake")

        consultation = (
            session.consultation.__class__.objects.select_for_update()
            .get(pk=session.consultation_id)
        )
        completeness = evaluate_completeness(session)
        if not completeness.can_submit_to_doctor:
            raise IntakeNotSubmittableError("required_information_missing")

        # One draft.
        from apps.medical_records.services import generate_draft_from_intake

        generate_draft_from_intake(session)

        session.status = IntakeSessionStatus.SUBMITTED_TO_DOCTOR
        session.submitted_at = timezone.now()
        session.save()

        consultation.status = ConsultationStatus.DOCTOR_REVIEW
        consultation.save(update_fields=["status", "updated_at"])

        IntakeIdempotencyLedger.objects.get_or_create(
            session=session,
            action="submit",
            client_request_id=client_request_id,
            defaults={
                "result_code": "ok",
                "state_before": "confirmed",
                "state_after": session.status,
                "prompt_version": PROMPT_VERSION,
            },
        )
        _notify_intake_submitted(consultation)
        _audit(
            "patient_intake_submitted",
            actor_id=session.consultation.patient.user_id,
            target_id=session.id,
            metadata={"state": session.status},
        )
        return _submission_response(
            session, replayed=False, consultation_status=consultation.status
        )


def _submission_response(session, *, replayed: bool, consultation_status=None) -> dict:
    return {
        "session_status": session.status,
        "submitted_at": session.submitted_at.isoformat() if session.submitted_at else None,
        "consultation_status": consultation_status or session.consultation.status,
        "replayed": replayed,
    }
