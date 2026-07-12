from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsPatient
from apps.consultations.models import Consultation
from apps.messaging.services import get_unread_message_counts
from apps.notifications.models import Notification
from apps.patients.models import PatientProfile
from apps.patients.serializers import (
    PatientProfileDetailSerializer,
    PatientProfileSerializer,
)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsPatient])
def my_patient_profile(request: Request) -> Response:
    """Get or update the authenticated patient's own profile."""
    profile = getattr(request.user, "patient_profile", None)
    if profile is None:
        return Response(
            {"detail": "Patient profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        serializer = PatientProfileDetailSerializer(profile)
        return Response(serializer.data)

    serializer = PatientProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    detail_serializer = PatientProfileDetailSerializer(profile)
    return Response(detail_serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPatient])
def my_patient_dashboard(request: Request) -> Response:
    """Dashboard summary for the authenticated patient."""
    profile = getattr(request.user, "patient_profile", None)
    if profile is None:
        return Response(
            {"detail": "Patient profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    consultations = Consultation.objects.filter(patient=profile)
    total = consultations.count()
    active = consultations.filter(
        status__in=(
            "submitted", "accepted", "intake_in_progress",
            "intake_completed", "doctor_review",
            "awaiting_patient_response", "awaiting_doctor_response",
            "under_review",
        ),
    ).count()
    completed = consultations.filter(status="completed").count()

    unread_messages = 0
    for c in consultations:
        counts = get_unread_message_counts(c, request.user)
        unread_messages += counts["unread_count"]

    unread_notifications = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()

    recent = consultations.order_by("-created_at")[:5]
    recent_data = [
        {
            "id": c.id,
            "status": c.status,
            "doctor_name": c.doctor.user.full_name if c.doctor else None,
            "specialty_name": c.specialty.name if c.specialty else None,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in recent.select_related("doctor__user", "specialty")
    ]

    return Response({
        "consultations": {
            "total": total,
            "active": active,
            "awaiting_patient": consultations.filter(
                status="awaiting_patient_response"
            ).count(),
            "awaiting_doctor": consultations.filter(
                status="awaiting_doctor_response"
            ).count(),
            "completed": completed,
        },
        "unread_messages": unread_messages,
        "unread_notifications": unread_notifications,
        "recent_consultations": recent_data,
    })
