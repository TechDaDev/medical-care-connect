from django.db.models import Avg, Count, FloatField, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsApprovedDoctor, IsDoctor
from apps.consultations.models import Consultation
from apps.core.security_events import doctor_profile_updated
from apps.doctors.models import DoctorAvailability, DoctorProfile
from apps.doctors.serializers import (
    DoctorAcceptingStatusSerializer,
    DoctorAvailabilitySerializer,
    DoctorOwnProfileReadSerializer,
    DoctorOwnProfileUpdateSerializer,
    DoctorSearchQuerySerializer,
    PublicDoctorDetailSerializer,
    PublicDoctorListSerializer,
)
from apps.reviews.models import ReviewStatus


# ── My Profile ──────────────────────────────────────────────────────────────


PROTECTED_DOCTOR_FIELDS = {
    "license_number",
    "approval_status",
    "is_approved",
    "approval_note",
    "is_accepting_consultations",
    "medical_license_document",
}


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
        serializer = DoctorOwnProfileReadSerializer(profile)
        return Response(serializer.data)

    # Reject protected fields explicitly
    protected_attempted = PROTECTED_DOCTOR_FIELDS & set(request.data.keys())
    if protected_attempted:
        return Response(
            {
                field: ["This field cannot be changed through profile update."]
                for field in sorted(protected_attempted)
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = DoctorOwnProfileUpdateSerializer(
        profile, data=request.data, partial=True
    )
    serializer.is_valid(raise_exception=True)
    updated_profile = serializer.save()
    updated_profile.refresh_from_db()

    # Audit changed field names (no values)
    if serializer.validated_data:
        changed_fields = list(serializer.validated_data.keys())
        doctor_profile_updated(
            user_id=str(request.user.id),
            profile_id=str(updated_profile.id),
            changed_fields=changed_fields,
        )

    read_serializer = DoctorOwnProfileReadSerializer(updated_profile)
    return Response(read_serializer.data)


# ── Doctor Dashboard Summary ────────────────────────────────────────────────


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


class DoctorPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _public_doctor_queryset():
    published_reviews = Q(
        consultations__review__status=ReviewStatus.PUBLISHED
    )
    return (
        DoctorProfile.objects.select_related("user", "specialty")
        .filter(
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
            user__is_active=True,
            specialty__is_active=True,
        )
        .annotate(
            average_rating=Coalesce(
                Avg(
                    "consultations__review__rating",
                    filter=published_reviews,
                ),
                0.0,
                output_field=FloatField(),
            ),
            total_reviews=Count(
                "consultations__review",
                filter=published_reviews,
                distinct=True,
            ),
        )
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def public_doctor_list(request: Request) -> Response:
    """Paginated public directory of approved, active doctors."""
    params = DoctorSearchQuerySerializer(data=request.query_params.dict())
    params.is_valid(raise_exception=True)
    values = params.validated_data
    queryset = _public_doctor_queryset()

    if specialty := values.get("specialty"):
        queryset = queryset.filter(specialty_id=specialty)
    if specialty_slug := values.get("specialty_slug"):
        queryset = queryset.filter(specialty__slug=specialty_slug)
    if "accepting" in values:
        queryset = queryset.filter(
            is_accepting_consultations=values["accepting"]
        )
    if language := values.get("language"):
        queryset = queryset.filter(languages__icontains=language)
    if min_experience := values.get("min_experience"):
        queryset = queryset.filter(years_of_experience__gte=min_experience)
    if values.get("min_fee") is not None:
        queryset = queryset.filter(
            consultation_fee__gte=values["min_fee"]
        )
    if values.get("max_fee") is not None:
        queryset = queryset.filter(
            consultation_fee__lte=values["max_fee"]
        )
    if max_response := values.get("max_response_minutes"):
        queryset = queryset.filter(
            estimated_response_minutes__lte=max_response
        )
    if search := values.get("search", "").strip():
        queryset = queryset.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(professional_title__icontains=search)
            | Q(workplace_name__icontains=search)
            | Q(qualifications__icontains=search)
            | Q(specialty__name_en__icontains=search)
            | Q(specialty__name_ar__icontains=search)
            | Q(specialty__name_ckb__icontains=search)
        )

    ordering_map = {
        "relevance": (
            "-is_accepting_consultations",
            "estimated_response_minutes",
            "user__first_name",
            "user__last_name",
        ),
        "name": ("user__first_name", "user__last_name"),
        "experience_desc": ("-years_of_experience", "user__first_name"),
        "fee_asc": ("consultation_fee", "user__first_name"),
        "fee_desc": ("-consultation_fee", "user__first_name"),
        "response_time_asc": (
            "estimated_response_minutes",
            "user__first_name",
        ),
        "newest": ("-created_at",),
    }
    queryset = queryset.order_by(*ordering_map[values["ordering"]], "id")

    paginator = DoctorPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = PublicDoctorListSerializer(
        page,
        many=True,
        context={"request": request},
    )
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_doctor_detail(request: Request, pk: str) -> Response:
    """Public profile of a single approved, active doctor."""
    profile = get_object_or_404(
        DoctorProfile.objects.select_related("user", "specialty").annotate(
            average_rating=Coalesce(
                Avg(
                    "consultations__review__rating",
                    filter=Q(
                        consultations__review__status=ReviewStatus.PUBLISHED
                    ),
                ),
                0.0,
                output_field=FloatField(),
            ),
            total_reviews=Count(
                "consultations__review",
                filter=Q(
                    consultations__review__status=ReviewStatus.PUBLISHED
                ),
                distinct=True,
            ),
        ),
        pk=pk,
        is_approved=True,
        approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        user__is_active=True,
    )
    serializer = PublicDoctorDetailSerializer(
        profile,
        context={"request": request},
    )
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
