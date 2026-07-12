from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsPatient
from apps.ai_intake.models import AIIntakeSession
from apps.ai_intake.serializers import (
    AnswerRequestSerializer,
    AnswerResponseSerializer,
    IntakeSessionSerializer,
    StartIntakeResponseSerializer,
)
from apps.ai_intake.services.intake import (
    process_intake_answer,
    start_intake_session,
)
from apps.consultations.models import Consultation


# ── Start Intake ────────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def start_intake(request: Request, consultation_id) -> Response:
    """Start (or resume) an AI intake session for a consultation."""
    consultation = get_object_or_404(
        Consultation,
        id=consultation_id,
        patient__user=request.user,
    )

    language = request.data.get("language", "en")
    session = start_intake_session(consultation, language=str(language))

    data = StartIntakeResponseSerializer({
        "session_id": session.id,
        "session_status": session.status,
        "current_question": session.current_question or "",
        "question_count": session.question_count,
        "emergency_detected": session.emergency_detected,
        "emergency_level": session.emergency_level,
        "language": session.language,
    }).data

    return Response(data, status=status.HTTP_200_OK)


# ── Answer Question ─────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def answer_intake(request: Request, session_id) -> Response:
    """Submit an answer to the AI intake session."""
    session = get_object_or_404(
        AIIntakeSession,
        id=session_id,
        consultation__patient__user=request.user,
        status__in=["not_started", "in_progress", "awaiting_patient"],
    )

    serializer = AnswerRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    session, result = process_intake_answer(
        session,
        serializer.validated_data["answer"],
    )

    # Normalize response fields for the client serializer
    response_data = AnswerResponseSerializer({
        "session_status": session.status,
        "patient_facing_message": result.get(
            "patient_facing_message",
            result.get("next_question", ""),
        ),
        "next_question": result.get("next_question"),
        "question_count": session.question_count,
        "emergency_detected": session.emergency_detected,
        "emergency_level": session.emergency_level,
        "record_ready": session.status == "ready_for_review",
    }).data

    return Response(response_data, status=status.HTTP_200_OK)


# ── Get Session ─────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_session(request: Request, session_id) -> Response:
    """Retrieve intake session with message history."""
    session = get_object_or_404(
        AIIntakeSession,
        id=session_id,
        consultation__patient__user=request.user,
    )
    data = IntakeSessionSerializer(session).data
    return Response(data, status=status.HTTP_200_OK)
