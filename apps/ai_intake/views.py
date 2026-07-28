from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsPatient
from apps.ai_intake.models import AIIntakeMessage, AIIntakeSession
from apps.ai_intake.serializers import (
    AnswerRequestSerializer,
    AnswerResponseSerializer,
    IntakeSessionSerializer,
)
from apps.ai_intake.services.intake import process_intake_answer


# ── Answer Question ─────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def answer_intake(request: Request, session_id) -> Response:
    """Submit an answer to the AI intake session."""
    session = get_object_or_404(
        AIIntakeSession.objects.prefetch_related("messages"),
        id=session_id,
        consultation__patient__user=request.user,
    )

    serializer = AnswerRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    request_id = serializer.validated_data.get("client_request_id")
    existing = (
        AIIntakeMessage.objects.filter(
            session=session, client_request_id=request_id
        ).first()
        if request_id
        else None
    )
    if existing:
        return Response(
            AnswerResponseSerializer({
                "session_status": session.status,
                "patient_facing_message": session.current_question or "",
                "next_question": session.current_question or None,
                "question_count": session.question_count,
                "emergency_detected": session.emergency_detected,
                "emergency_level": session.emergency_level,
                "record_ready": session.status == "ready_for_review",
            }).data,
            status=status.HTTP_200_OK,
        )
    if session.status not in {"not_started", "in_progress", "awaiting_patient"}:
        return Response(
            {"detail": "intake_session_closed", "code": "intake_session_closed"},
            status=status.HTTP_409_CONFLICT,
        )

    session, result = process_intake_answer(
        session,
        serializer.validated_data["answer"],
        client_request_id=request_id,
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
@permission_classes([IsAuthenticated, IsPatient])
def get_session(request: Request, session_id) -> Response:
    """Retrieve intake session with message history."""
    session = get_object_or_404(
        AIIntakeSession,
        id=session_id,
        consultation__patient__user=request.user,
    )
    data = IntakeSessionSerializer(session).data
    return Response(data, status=status.HTTP_200_OK)
