from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsApprovedDoctor, IsDoctor
from apps.consultations.models import Consultation
from apps.doctors.models import DoctorAvailability, DoctorProfile
from apps.doctors.serializers import (
    DoctorAcceptingStatusSerializer,
    DoctorAvailabilitySerializer,
    DoctorProfileDetailSerializer,
    DoctorProfileSerializer,
    PublicDoctorDetailSerializer,
    PublicDoctorListSerializer,
)


# ── My Profile ──────────────────────────────────────────────────────────────


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsDoctor])
def my_doctor_profile(request: Request) -> Response:
    """Get or update the authenticated doctor's own profile."""
    profile = getattr(request.user, "doctor_profile", None)
    if profile is None:
        return Response(
            {"detail": "Doctor profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        serializer = DoctorProfileDetailSerializer(profile)
        return Response(serializer.data)

    serializer = DoctorProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    detail_serializer = DoctorProfileDetailSerializer(profile)
    return Response(detail_serializer.data)


# ── Doctor Dashboard Summary ────────────────────────────────────────────────


from django.db.models import Q
from apps.messaging.services import get_unread_message_counts
from apps.notifications.models import Notification


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def my_doctor_dashboard(request: Request) -> Response:
    """Dashboard summary for the authenticated doctor."""
    profile = getattr(request.user, "doctor_profile", None)
    if profile is None:
        return Response(
            {"detail": "Doctor profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    consultations = Consultation.objects.filter(doctor=profile)
    unread_messages = 0
    for c in consultations:
        counts = get_unread_message_counts(c, request.user)
        unread_messages += counts["unread_count"]

    unread_notifications = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()

    return Response({
        "consultations": {
            "total_active": consultations.filter(
                status__in=(
                    "submitted", "accepted", "intake_in_progress",
                    "intake_completed", "doctor_review",
                    "awaiting_patient_response", "awaiting_doctor_response",
                    "under_review", "follow_up_required", "physical_visit_required",
                    "transferred",
                ),
            ).count(),
            "submitted": consultations.filter(status="submitted").count(),
            "accepted": consultations.filter(status="accepted").count(),
            "intake_completed": consultations.filter(status="intake_completed").count(),
            "doctor_review": consultations.filter(status="doctor_review").count(),
            "awaiting_patient": consultations.filter(
                status="awaiting_patient_response"
            ).count(),
            "awaiting_doctor": consultations.filter(
                status="awaiting_doctor_response"
            ).count(),
        },
        "unread_messages": unread_messages,
        "unread_notifications": unread_notifications,
        "profile": {
            "is_approved": profile.is_approved,
            "is_accepting_consultations": profile.is_accepting_consultations,
        },
    })


# ── Public Doctor Directory ─────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([AllowAny])
def public_doctor_list(request: Request) -> Response:
    """List approved, active doctors.

    Filters:
    - specialty (UUID)
    - specialty_slug (str)
    - accepting (bool) - exclude non-accepting when true
    - language (str) - match in languages JSON array
    - search (str) - name / professional_title match
    - ordering (str) - default: years_of_experience
    """
    queryset = DoctorProfile.objects.select_related(
        "user", "specialty"
    ).filter(
        is_approved=True,
        user__is_active=True,
    )

    specialty = request.query_params.get("specialty")
    if specialty:
        queryset = queryset.filter(specialty_id=specialty)

    specialty_slug = request.query_params.get("specialty_slug")
    if specialty_slug:
        queryset = queryset.filter(specialty__slug=specialty_slug)

    accepting = request.query_params.get("accepting")
    if accepting and accepting.lower() in ("true", "1"):
        queryset = queryset.filter(is_accepting_consultations=True)

    language = request.query_params.get("language")
    if language:
        queryset = queryset.filter(languages__contains=[language])

    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(professional_title__icontains=search)
        )

    ordering = request.query_params.get("ordering", "years_of_experience")
    if ordering.lstrip("-") not in (
        "years_of_experience", "consultation_fee",
        "user__first_name", "user__last_name",
    ):
        ordering = "years_of_experience"
    queryset = queryset.order_by(ordering)

    page = request.query_params.get("page")
    page_size = request.query_params.get("page_size", 20)
    if page is not None:
        from rest_framework.pagination import PageNumberPagination

        class DoctorPagination(PageNumberPagination):
            page_size = 20
            page_size_query_param = "page_size"
            max_page_size = 100

        paginator = DoctorPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PublicDoctorListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = PublicDoctorListSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_doctor_detail(request: Request, pk: str) -> Response:
    """Public profile of a single approved, active doctor."""
    profile = get_object_or_404(
        DoctorProfile.objects.select_related("user", "specialty"),
        pk=pk,
        is_approved=True,
        user__is_active=True,
    )
    serializer = PublicDoctorDetailSerializer(profile)
    return Response(serializer.data)


# ── Doctor Availability ─────────────────────────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def my_availability_list(request: Request) -> Response:
    """List or create availability slots for the authenticated doctor."""
    profile = getattr(request.user, "doctor_profile", None)
    if profile is None:
        return Response(
            {"detail": "Doctor profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        slots = DoctorAvailability.objects.filter(doctor=profile)
        serializer = DoctorAvailabilitySerializer(slots, many=True)
        return Response(serializer.data)

    serializer = DoctorAvailabilitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(doctor=profile)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def my_availability_detail(request: Request, pk: str) -> Response:
    """Update or delete a specific availability slot."""
    profile = getattr(request.user, "doctor_profile", None)
    if profile is None:
        return Response(
            {"detail": "Doctor profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    slot = get_object_or_404(
        DoctorAvailability, pk=pk, doctor=profile
    )

    if request.method == "DELETE":
        slot.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = DoctorAvailabilitySerializer(slot, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


# ── Accepting Status ────────────────────────────────────────────────────────


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def update_accepting_status(request: Request) -> Response:
    """Toggle the doctor accepting-consultations flag."""
    # Allow admins/coordinators to set for any doctor, or doctor to set own
    profile = getattr(request.user, "doctor_profile", None)
    if profile is None:
        return Response(
            {"detail": "Doctor profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = DoctorAcceptingStatusSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    profile.is_accepting_consultations = serializer.validated_data[
        "is_accepting_consultations"
    ]
    profile.save(update_fields=["is_accepting_consultations", "updated_at"])

    return Response(
        {"is_accepting_consultations": profile.is_accepting_consultations}
    )
