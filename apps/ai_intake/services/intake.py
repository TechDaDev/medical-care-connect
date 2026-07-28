import json
import logging

from django.conf import settings
from django.utils import timezone

from apps.ai_intake.models import AIIntakeSession, AIIntakeMessage
from apps.ai_intake.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from apps.ai_intake.schemas import IntakeTurnResponse, CollectedData
from apps.ai_intake.services.base import (
    AIProviderDisabled,
    AIProviderUnavailable,
    AIResponseInvalid,
    AIProviderConfigurationError,
)
from apps.ai_intake.services.deepseek import DeepSeekProvider
from apps.ai_intake.services.emergency import screen_patient_input
from apps.consultations.models import ConsultationStatus

logger = logging.getLogger(__name__)

COLLECTED_DATA_FIELDS = [
    "chief_complaint",
    "symptoms",
    "duration",
    "severity",
    "location",
    "triggers",
    "relieving_factors",
    "past_medical_history",
    "medications",
    "allergies",
    "family_history",
    "social_history",
    "additional_notes",
]


def _escalate_consultation(session: AIIntakeSession) -> None:
    consultation = session.consultation
    if consultation.status == ConsultationStatus.EMERGENCY_ESCALATED:
        return
    consultation.status = ConsultationStatus.EMERGENCY_ESCALATED
    consultation.save(update_fields=["status", "updated_at"])

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

    raise AIProviderConfigurationError(
        f"Unsupported AI provider: {provider_name}"
    )


def start_intake_session(consultation, language: str = "en") -> AIIntakeSession:
    """Create a new AI intake session for a consultation."""
    defaults = dict(
        status="in_progress",
        started_at=timezone.now(),
        language=language,
        ai_provider=settings.AI_INTAKE_PROVIDER or "deepseek",
        ai_model=settings.DEEPSEEK_MODEL,
        prompt_version=PROMPT_VERSION,
        question_count=0,
        collected_data={},
        missing_fields=list(COLLECTED_DATA_FIELDS),
    )
    session, created = AIIntakeSession.objects.get_or_create(
        consultation=consultation,
        defaults=defaults,
    )
    if created or session.status in {"not_started", "failed"}:
        for field, value in defaults.items():
            setattr(session, field, value)
        session.save()
    if consultation.status == ConsultationStatus.ACCEPTED:
        consultation.status = ConsultationStatus.INTAKE_IN_PROGRESS
        consultation.save(update_fields=["status", "updated_at"])
    return session


def process_intake_answer(
    session: AIIntakeSession,
    patient_message: str,
    client_request_id=None,
) -> tuple[AIIntakeSession, dict]:
    """Process one patient answer.

    1. Deterministic emergency screen (no AI cost).
    2. Save patient message.
    3. Call AI for next turn.
    4. Save AI response.
    5. Update session state.
    """
    # ── 1. Emergency pre-screen ──────────────────────────────────
    emergency = screen_patient_input(patient_message)

    # ── 2. Save patient message ──────────────────────────────────
    patient_msg = AIIntakeMessage.objects.create(
        session=session,
        role="patient",
        content=patient_message,
        sequence_number=AIIntakeMessage.objects.filter(session=session).count() + 1,
        emergency_flags=emergency if emergency["detected"] else [],
        client_request_id=client_request_id,
    )

    if emergency["detected"]:
        session.emergency_detected = True
        session.emergency_level = emergency["level"]
        session.emergency_reasons = emergency["reasons"]
        session.status = "emergency_stopped"
        if not session.started_at:
            session.started_at = timezone.now()
        session.updated_at = timezone.now()
        session.save(update_fields=[
            "emergency_detected", "emergency_level", "emergency_reasons",
            "status", "started_at", "updated_at",
        ])
        _escalate_consultation(session)
        # Return early — no AI call for flagged emergencies
        return session, _make_emergency_response(session, emergency)

    # ── 3. Build messages for AI ─────────────────────────────────
    max_questions = getattr(settings, "AI_INTAKE_MAX_QUESTIONS", 12)
    messages = _build_ai_messages(session, patient_message, max_questions)

    # ── 4. Call AI provider ──────────────────────────────────────
    try:
        provider = _get_provider()
        raw = provider.generate_structured_response(messages)
    except (AIProviderDisabled, AIProviderUnavailable, AIResponseInvalid,
            AIProviderConfigurationError) as exc:
        logger.error("AI intake error: %s", exc)
        session.status = "failed"
        session.error_code = type(exc).__name__
        session.error_message = str(exc)
        session.updated_at = timezone.now()
        session.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        return session, _make_error_response(str(exc))

    # ── 5. Validate AI response ──────────────────────────────────
    try:
        validated = IntakeTurnResponse(**raw)
    except Exception as exc:
        logger.warning("AI response validation failed: %s", exc)
        validated = _coerce_partial_response(raw)

    # ── 6. Update session fields ─────────────────────────────────
    session.question_count += 1
    session.current_question = validated.next_question or ""
    session.collected_data = validated.collected_data.model_dump()
    session.missing_fields = validated.missing_fields

    session.input_tokens = provider.input_tokens or 0
    session.output_tokens = provider.output_tokens or 0
    session.total_tokens = provider.total_tokens or 0
    session.last_ai_request_at = timezone.now()

    if validated.conversation_status == "ready_for_review":
        session.status = "ready_for_review"
        session.completed_at = timezone.now()
        # Auto-generate medical record draft
        from apps.medical_records.services import generate_draft_from_intake
        generate_draft_from_intake(session)
        session.consultation.status = ConsultationStatus.INTAKE_COMPLETED
        session.consultation.save(update_fields=["status", "updated_at"])
        from apps.notifications.services import notify_intake_completed
        notify_intake_completed(session.consultation)
    elif validated.emergency_detected:
        session.status = "emergency_stopped"
        session.emergency_detected = True
        session.emergency_level = validated.emergency_level
        session.emergency_reasons = validated.emergency_reasons or []
        _escalate_consultation(session)

    if not validated.next_question and validated.conversation_status == "needs_more_information":
        # Guard — never leave a live session without a next question
        validated.next_question = _fallback_question(session.missing_fields)

    session.updated_at = timezone.now()
    session.save()

    # ── 7. Save AI message ───────────────────────────────────────
    AIIntakeMessage.objects.create(
        session=session,
        role="assistant",
        content=validated.patient_facing_message or validated.next_question or "",
        sequence_number=AIIntakeMessage.objects.filter(session=session).count() + 1,
        structured_data=validated.collected_data.model_dump() if validated.collected_data else None,
    )

    return session, validated.model_dump(exclude_none=True)


def _make_emergency_response(session, emergency):
    return {
        "conversation_status": "emergency",
        "patient_facing_message": _emergency_message(emergency["level"]),
        "next_question": None,
        "emergency_detected": True,
        "emergency_level": emergency["level"],
        "emergency_reasons": emergency["reasons"],
        "collected_data": {},
        "missing_fields": [],
    }


def _emergency_message(level: str) -> str:
    if level == "emergency":
        return "Your description suggests this may be a life-threatening emergency. MCC is not an emergency service. Please seek immediate emergency care by calling your local emergency number."
    return "What you described sounds urgent. A coordinator may review your case. If your condition worsens, please seek immediate medical attention."


def _make_error_response(error_message: str) -> dict:
    return {
        "conversation_status": "error",
        "patient_facing_message": "We encountered a technical issue. Please try again or contact support.",
        "next_question": None,
        "emergency_detected": False,
        "emergency_level": "none",
        "emergency_reasons": [],
        "collected_data": {},
        "missing_fields": [],
        "error": error_message,
    }


def _build_ai_messages(
    session: AIIntakeSession,
    latest_answer: str,
    max_questions: int,
) -> list[dict]:
    history = AIIntakeMessage.objects.filter(session=session).order_by("sequence_number")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Include all previous turns
    for h in history:
        messages.append({"role": h.role, "content": h.content})

    # Append the new answer
    messages.append({"role": "patient", "content": latest_answer})

    prompt_context = (
        f"You are conducting medical intake for a consultation. "
        f"You have asked {session.question_count} questions so far. "
        f"The maximum is {max_questions}. "
        f"Already collected: {json.dumps(session.collected_data or {}, ensure_ascii=False)}. "
        f"Still missing: {session.missing_fields or []}. "
    )
    messages.append({"role": "user", "content": prompt_context + "\n\nRespond with valid JSON following the schema."})

    return messages


def _coerce_partial_response(raw: dict) -> IntakeTurnResponse:
    """Best-effort coercion when Pydantic validation of AI output fails."""
    collected = raw.get("collected_data", {})
    if not isinstance(collected, dict):
        collected = {}
    try:
        validated_collected = CollectedData(**collected)
    except Exception:
        validated_collected = CollectedData()

    return IntakeTurnResponse(
        conversation_status=raw.get("conversation_status", "needs_more_information"),
        patient_facing_message=raw.get("patient_facing_message"),
        next_question=raw.get("next_question"),
        emergency_detected=bool(raw.get("emergency_detected")),
        emergency_level=raw.get("emergency_level", "none"),
        emergency_reasons=raw.get("emergency_reasons") or [],
        collected_data=validated_collected,
        missing_fields=raw.get("missing_fields") or [],
    )


def _fallback_question(missing_fields: list[str]) -> str:
    fallbacks = {
        "chief_complaint": "What brings you in today?",
        "symptoms": "What symptoms are you experiencing?",
        "duration": "How long have you had these symptoms?",
        "severity": "How severe is your discomfort on a scale of 0-10?",
        "location": "Where on your body are you experiencing this?",
        "past_medical_history": "Do you have any relevant medical history?",
        "medications": "Are you currently taking any medications?",
        "allergies": "Do you have any allergies?",
    }
    for field in missing_fields:
        if field in fallbacks:
            return fallbacks[field]
    return "Is there anything else you'd like to share before we finish?"
