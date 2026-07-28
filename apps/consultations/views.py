from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import UserRole
from apps.accounts.permissions import IsApprovedDoctor, IsPatient
from apps.ai_intake.serializers import StartIntakeResponseSerializer
from apps.ai_intake.services.base import AIProviderDisabled
from apps.ai_intake.services.intake import start_intake_session
from apps.consultations.models import Consultation, ConsultationStatus
from apps.consultations.serializers import (
    ConsultationCancelSerializer,
    ConsultationCreateSerializer,
    ConsultationCreateResponseSerializer,
    ConsultationDetailSerializer,
    ConsultationSerializer,
)
from apps.consultations.services import (
    ConsultationCreationError,
    create_patient_consultation,
)


# ── Consultation Collection ─────────────────────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def consultation_collection(request: Request) -> Response:
    """List or create consultations.

    GET  → list based on user role (patient owns, doctor assigned, staff all).
    POST → create a new consultation (patient-only).
    """
    if request.method == "GET":
        return _list_consultations(request)

    return _create_consultation(request)


def _list_consultations(request: Request) -> Response:
    """List consultations based on user role."""
    user = request.user
    queryset = Consultation.objects.select_related(
        "patient__user", "doctor__user", "specialty"
    )

    if user.role == UserRole.PATIENT and hasattr(user, "patient_profile"):
        queryset = queryset.filter(patient=user.patient_profile)
    elif user.role == UserRole.DOCTOR and hasattr(user, "doctor_profile"):
        queryset = queryset.filter(doctor=user.doctor_profile)
    elif user.role not in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        return Response(
            {"detail": "You do not have permission to view consultations."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = ConsultationSerializer(queryset, many=True)
    return Response(serializer.data)


def _create_consultation(request: Request) -> Response:
    """Create a new consultation. Patient-only."""
    if request.user.role != UserRole.PATIENT:
        return Response(
            {
                "detail": "patient_role_required",
                "code": "patient_role_required",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    patient_profile = getattr(request.user, "patient_profile", None)
    if patient_profile is None:
        return Response(
            {
                "detail": "patient_profile_unavailable",
                "code": "patient_profile_unavailable",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = ConsultationCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    try:
        result = create_patient_consultation(
            patient=patient_profile,
            doctor_id=values["doctor"],
            description=values["description"],
            client_request_id=values["client_request_id"],
            priority=values["priority"],
            specialty_id=values.get("specialty"),
            expected_doctor_updated_at=values.get(
                "expected_doctor_updated_at"
            ),
            request_id=getattr(request, "request_id", ""),
        )
    except ConsultationCreationError as error:
        conflict_codes = {
            "doctor_not_accepting",
            "doctor_state_changed",
            "specialty_inactive",
            "duplicate_request",
        }
        response_status = (
            status.HTTP_409_CONFLICT
            if error.code in conflict_codes
            else status.HTTP_400_BAD_REQUEST
        )
        return Response(
            {
                "detail": error.code,
                "code": error.code,
                "fields": {error.field: [error.code]},
            },
            status=response_status,
        )

    output = ConsultationCreateResponseSerializer(
        result.consultation,
        context={"request": request},
    )
    return Response(
        output.data,
        status=(
            status.HTTP_201_CREATED
            if result.created
            else status.HTTP_200_OK
        ),
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def consultation_detail(request: Request, pk: str) -> Response:
    """Get a single consultation. Role-scoped access."""
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            "patient__user", "doctor__user", "specialty",
            "intake_session", "medical_record",
        ),
        pk=pk,
    )

    user = request.user
    is_participant = (
        (hasattr(user, "patient_profile") and consultation.patient == user.patient_profile)
        or (hasattr(user, "doctor_profile") and consultation.doctor == user.doctor_profile)
    )
    if not is_participant and user.role not in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        return Response(
            {"detail": "You do not have permission to view this consultation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = ConsultationDetailSerializer(
        consultation, context={"request": request}
    )
    return Response(serializer.data)


# ── Consultation Actions ────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def accept_consultation(request: Request, pk: str) -> Response:
    """Accept a consultation. Only the assigned doctor can accept."""
    consultation = get_object_or_404(
        Consultation.objects.select_related("patient__user", "doctor__user", "specialty"),
        pk=pk,
    )

    doctor_profile = getattr(request.user, "doctor_profile", None)
    if doctor_profile is None or consultation.doctor != doctor_profile:
        return Response(
            {"detail": "You are not the assigned doctor for this consultation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if consultation.status != ConsultationStatus.SUBMITTED:
        return Response(
            {"detail": f"Cannot accept consultation in status '{consultation.get_status_display()}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    consultation.status = ConsultationStatus.ACCEPTED
    consultation.accepted_at = timezone.now()
    consultation.save(update_fields=["status", "accepted_at", "updated_at"])

    # Notify patient
    from apps.notifications.services import notify_consultation_accepted
    notify_consultation_accepted(consultation)

    serializer = ConsultationSerializer(consultation)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_consultation(request: Request, pk: str) -> Response:
    """Cancel a consultation. Requires cancellation_reason."""
    consultation = get_object_or_404(
        Consultation.objects.select_related("patient__user", "doctor__user", "specialty"),
        pk=pk,
    )

    user = request.user
    is_participant = (
        (hasattr(user, "patient_profile") and consultation.patient == user.patient_profile)
        or (hasattr(user, "doctor_profile") and consultation.doctor == user.doctor_profile)
    )
    if not is_participant and user.role not in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        return Response(
            {"detail": "You do not have permission to cancel this consultation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if consultation.status in (ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED):
        return Response(
            {"detail": f"Cannot cancel consultation in status '{consultation.get_status_display()}'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ConsultationCancelSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    consultation.status = ConsultationStatus.CANCELLED
    consultation.cancellation_reason = serializer.validated_data["cancellation_reason"]
    consultation.cancelled_at = timezone.now()
    consultation.save(update_fields=[
        "status", "cancellation_reason", "cancelled_at", "updated_at"
    ])

    # Notify participants
    from apps.notifications.services import notify_consultation_cancelled
    notify_consultation_cancelled(consultation)

    output = ConsultationSerializer(consultation)
    return Response(output.data)


# ── AI Intake Start ─────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPatient])
def start_intake(request: Request, pk) -> Response:
    """Start (or resume) an AI intake session for a consultation.

    Returns 503 when AI intake is disabled.
    """
    consultation = get_object_or_404(
        Consultation,
        id=pk,
        patient__user=request.user,
    )

    try:
        language = request.data.get("language", "en")
        session = start_intake_session(consultation, language=str(language))
    except AIProviderDisabled:
        return Response(
            {"detail": "AI-assisted intake is currently unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

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
