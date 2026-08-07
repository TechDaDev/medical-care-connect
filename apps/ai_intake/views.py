from django.db import transaction
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
    ConfirmRequestSerializer,
    CorrectionRequestSerializer,
    IntakeSessionSerializer,
    ReviewResponseSerializer,
    SubmissionRequestSerializer,
)
from apps.ai_intake.services.intake import (
    IntakeNotConfirmableError,
    IntakeNotReviewableError,
    IntakeNotSubmittableError,
    IntakeProcessingError,
    StaleIntakeError,
    apply_corrections,
    confirm_intake,
    get_review_summary,
    process_intake_answer,
    submit_intake,
)


def _patient_session(request, session_id) -> AIIntakeSession:
    return get_object_or_404(
        AIIntakeSession.objects.prefetch_related("messages"),
        id=session_id,
        consultation__patient__user=request.user,
    )


# ── Answer Question ──────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def answer_intake(request: Request, session_id) -> Response:
    """Submit an answer to the AI intake session (idempotent)."""
    session = _patient_session(request, session_id)
    serializer = AnswerRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    request_id = serializer.validated_data.get("client_request_id")

    try:
        session, result = process_intake_answer(
            session,
            serializer.validated_data["answer"],
            client_request_id=request_id,
        )
    except IntakeProcessingError as exc:
        return Response(
            {"detail": exc.code, "code": exc.code},
            status=status.HTTP_409_CONFLICT,
        )

    response_data = AnswerResponseSerializer({
        "session_status": result.get("session_status", session.status),
        "patient_facing_message": result.get("patient_facing_message", ""),
        "next_question": result.get("next_question"),
        "next_question_field": result.get("next_question_field"),
        "question_count": result.get("question_count", session.question_count),
        "emergency_detected": result.get("emergency_detected", session.emergency_detected),
        "emergency_level": result.get("emergency_level", session.emergency_level),
        "record_ready": result.get("record_ready", False),
        "submitted_to_doctor": result.get("submitted_to_doctor", False),
        "error_code": result.get("error_code"),
        "retryable": result.get("retryable"),
        "replayed": result.get("replayed", False),
        "completeness": result.get("completeness"),
    }).data
    return Response(response_data, status=status.HTTP_200_OK)


# ── Get Session ──────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPatient])
def get_session(request: Request, session_id) -> Response:
    """Retrieve intake session with message history."""
    session = _patient_session(request, session_id)
    data = IntakeSessionSerializer(session).data
    return Response(data, status=status.HTTP_200_OK)


# ── Review ───────────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPatient])
def intake_review(request: Request, session_id) -> Response:
    """Patient-facing review summary."""
    session = _patient_session(request, session_id)
    summary = get_review_summary(session)
    data = ReviewResponseSerializer({
        "session_id": session.id,
        "session_status": session.status,
        "consultation_id": session.consultation_id,
        "review": summary,
        "can_confirm": session.status in {"awaiting_patient_review", "correction_in_progress"},
        "can_correct": session.status in {"awaiting_patient_review", "correction_in_progress"},
        "can_submit": session.status == "confirmed",
        "updated_at": session.updated_at,
        "missing_blocking_fields": session.missing_fields,
    }).data
    return Response(data, status=status.HTTP_200_OK)


# ── Corrections ─────────────────────────────────────────────────────────────


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsPatient])
def intake_corrections(request: Request, session_id) -> Response:
    """Apply patient corrections to extracted information."""
    session = _patient_session(request, session_id)
    serializer = CorrectionRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        summary = apply_corrections(
            session,
            serializer.validated_data["corrections"],
            expected_updated_at=serializer.validated_data["expected_updated_at"],
            client_request_id=serializer.validated_data["client_request_id"],
        )
    except IntakeNotReviewableError:
        return Response(
            {"detail": "intake_not_reviewable", "code": "intake_not_reviewable"},
            status=status.HTTP_409_CONFLICT,
        )
    except StaleIntakeError:
        return Response(
            {"detail": "stale_intake", "code": "stale_intake"},
            status=status.HTTP_409_CONFLICT,
        )
    except ValueError:
        return Response(
            {"detail": "no_valid_corrections", "code": "no_valid_corrections"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    session.refresh_from_db()
    data = ReviewResponseSerializer({
        "session_id": session.id,
        "session_status": session.status,
        "consultation_id": session.consultation_id,
        "review": summary,
        "can_confirm": True,
        "can_correct": True,
        "can_submit": session.status == "confirmed",
        "updated_at": session.updated_at,
        "missing_blocking_fields": session.missing_fields,
    }).data
    return Response(data, status=status.HTTP_200_OK)


# ── Confirm ─────────────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def intake_confirm(request: Request, session_id) -> Response:
    """Confirm the reviewed summary. Idempotent. No doctor notification."""
    session = _patient_session(request, session_id)
    serializer = ConfirmRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = confirm_intake(
            session,
            expected_updated_at=serializer.validated_data["expected_updated_at"],
            client_request_id=serializer.validated_data["client_request_id"],
        )
    except IntakeNotConfirmableError as exc:
        return Response(
            {"detail": str(exc), "code": str(exc)},
            status=status.HTTP_409_CONFLICT,
        )
    except StaleIntakeError:
        return Response(
            {"detail": "stale_intake", "code": "stale_intake"},
            status=status.HTTP_409_CONFLICT,
        )
    return Response(result, status=status.HTTP_200_OK)


# ── Submit ──────────────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def intake_submit(request: Request, session_id) -> Response:
    """Submit confirmed intake to the doctor. Idempotent."""
    session = _patient_session(request, session_id)
    serializer = SubmissionRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = submit_intake(
            session,
            expected_updated_at=serializer.validated_data["expected_updated_at"],
            client_request_id=serializer.validated_data["client_request_id"],
        )
    except IntakeNotSubmittableError as exc:
        return Response(
            {"detail": str(exc), "code": str(exc)},
            status=status.HTTP_409_CONFLICT,
        )
    except StaleIntakeError:
        return Response(
            {"detail": "stale_intake", "code": "stale_intake"},
            status=status.HTTP_409_CONFLICT,
        )
    return Response(result, status=status.HTTP_200_OK)