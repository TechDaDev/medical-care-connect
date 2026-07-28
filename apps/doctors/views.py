from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, FloatField, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsApprovedDoctor, IsDoctor
from apps.consultations.models import Consultation
from apps.core.audit_service import create_audit_event
from apps.core.models import AuditEventCategory
from apps.core.security_events import doctor_profile_updated
from apps.doctors.models import DoctorAvailability, DoctorProfile
from apps.doctors.serializers import (
    DoctorAcceptingStatusSerializer,
    DoctorAvailabilityMutationSerializer,
    DoctorAvailabilitySerializer,
    DoctorOwnProfileReadSerializer,
    DoctorOwnProfileUpdateSerializer,
    DoctorSearchQuerySerializer,
    PublicDoctorDetailSerializer,
    PublicDoctorListSerializer,
)
from apps.doctors.services import (
    availability_overlaps,
    availability_summary,
    build_doctor_dashboard,
    doctor_access_state,
    stale_timestamp,
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


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def my_doctor_dashboard(request: Request) -> Response:
    """Bounded-query dashboard summary for the authenticated doctor."""
    profile = getattr(request.user, "doctor_profile", None)
    if profile is None:
        return Response(
            {"detail": "Doctor profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(build_doctor_dashboard(profile, request.user))


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsDoctor])
def my_doctor_access_state(request: Request) -> Response:
    """Authoritative routing/access state, including missing-profile doctors."""
    profile = getattr(request.user, "doctor_profile", None)
    return Response(doctor_access_state(request.user, profile))


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
        return Response(
            {
                "timezone": settings.TIME_ZONE,
                "is_accepting_consultations": profile.is_accepting_consultations,
                "can_manage": True,
                "slots": serializer.data,
                "generated_at": timezone.now(),
            }
        )

    serializer = DoctorAvailabilityMutationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    values.pop("expected_updated_at", None)
    try:
        with transaction.atomic():
            locked_profile = DoctorProfile.objects.select_for_update().get(
                pk=profile.pk
            )
            if DoctorAvailability.objects.filter(
                doctor=locked_profile,
                day_of_week=values["day_of_week"],
                start_time=values["start_time"],
                end_time=values["end_time"],
            ).exists():
                return Response(
                    {"detail": "Availability slot already exists.", "code": "duplicate_availability"},
                    status=status.HTTP_409_CONFLICT,
                )
            if availability_overlaps(
                profile=locked_profile,
                day_of_week=values["day_of_week"],
                start_time=values["start_time"],
                end_time=values["end_time"],
            ):
                return Response(
                    {"detail": "Availability overlaps an existing slot.", "code": "availability_overlap"},
                    status=status.HTTP_409_CONFLICT,
                )
            slot = DoctorAvailability.objects.create(
                doctor=locked_profile, **values
            )
            create_audit_event(
                "doctor_availability_created",
                AuditEventCategory.DOCTOR,
                actor_id=str(request.user.id),
                actor_role=request.user.role,
                target_type="doctor_availability",
                target_id=str(slot.id),
                summary="Doctor availability slot created.",
                metadata={
                    "profile_id": str(locked_profile.id),
                    "changed_fields": sorted(values.keys()),
                },
            )
    except IntegrityError:
        return Response(
            {"detail": "Availability slot already exists.", "code": "duplicate_availability"},
            status=status.HTTP_409_CONFLICT,
        )
    return Response(
        DoctorAvailabilitySerializer(slot).data,
        status=status.HTTP_201_CREATED,
    )


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

    if request.method == "DELETE":
        expected = request.query_params.get("expected_updated_at")
        parsed_expected = parse_datetime(expected) if expected else None
        if expected and parsed_expected is None:
            return Response(
                {"detail": "Invalid expected_updated_at.", "code": "invalid_timestamp"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            DoctorProfile.objects.select_for_update().get(pk=profile.pk)
            try:
                slot = DoctorAvailability.objects.select_for_update().get(
                    pk=pk, doctor=profile
                )
            except DoctorAvailability.DoesNotExist:
                return Response(
                    {"detail": "Availability slot not found.", "code": "availability_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if stale_timestamp(parsed_expected, slot.updated_at):
                return Response(
                    {"detail": "Availability slot changed.", "code": "stale_availability"},
                    status=status.HTTP_409_CONFLICT,
                )
            slot_id = slot.id
            slot.delete()
            create_audit_event(
                "doctor_availability_deleted",
                AuditEventCategory.DOCTOR,
                actor_id=str(request.user.id),
                actor_role=request.user.role,
                target_type="doctor_availability",
                target_id=str(slot_id),
                summary="Doctor availability slot deleted.",
                metadata={
                    "changed_fields": ["deleted"],
                    "profile_id": str(profile.id),
                },
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    try:
        slot = DoctorAvailability.objects.get(pk=pk, doctor=profile)
    except DoctorAvailability.DoesNotExist:
        return Response(
            {"detail": "Availability slot not found.", "code": "availability_not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    serializer = DoctorAvailabilityMutationSerializer(
        slot, data=request.data, partial=True
    )
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    expected = values.pop("expected_updated_at", None)
    try:
        with transaction.atomic():
            DoctorProfile.objects.select_for_update().get(pk=profile.pk)
            try:
                locked_slot = DoctorAvailability.objects.select_for_update().get(
                    pk=pk, doctor=profile
                )
            except DoctorAvailability.DoesNotExist:
                return Response(
                    {"detail": "Availability slot not found.", "code": "availability_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if stale_timestamp(expected, locked_slot.updated_at):
                return Response(
                    {"detail": "Availability slot changed.", "code": "stale_availability"},
                    status=status.HTTP_409_CONFLICT,
                )
            merged = {
                "day_of_week": values.get("day_of_week", locked_slot.day_of_week),
                "start_time": values.get("start_time", locked_slot.start_time),
                "end_time": values.get("end_time", locked_slot.end_time),
            }
            if DoctorAvailability.objects.filter(
                doctor=profile,
                **merged,
            ).exclude(id=locked_slot.id).exists():
                return Response(
                    {"detail": "Availability slot already exists.", "code": "duplicate_availability"},
                    status=status.HTTP_409_CONFLICT,
                )
            if availability_overlaps(
                profile=profile, exclude_id=locked_slot.id, **merged
            ):
                return Response(
                    {"detail": "Availability overlaps an existing slot.", "code": "availability_overlap"},
                    status=status.HTTP_409_CONFLICT,
                )
            changed_fields = [
                field
                for field, value in values.items()
                if getattr(locked_slot, field) != value
            ]
            for field, value in values.items():
                setattr(locked_slot, field, value)
            if changed_fields:
                locked_slot.save(update_fields=changed_fields + ["updated_at"])
                create_audit_event(
                    "doctor_availability_updated",
                    AuditEventCategory.DOCTOR,
                    actor_id=str(request.user.id),
                    actor_role=request.user.role,
                    target_type="doctor_availability",
                    target_id=str(locked_slot.id),
                    summary="Doctor availability slot updated.",
                    metadata={
                        "profile_id": str(profile.id),
                        "changed_fields": sorted(changed_fields),
                    },
                )
    except IntegrityError:
        return Response(
            {"detail": "Availability slot already exists.", "code": "duplicate_availability"},
            status=status.HTTP_409_CONFLICT,
        )
    return Response(DoctorAvailabilitySerializer(locked_slot).data)


# ── Accepting Status ────────────────────────────────────────────────────────


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsApprovedDoctor])
def update_accepting_status(request: Request) -> Response:
    """Toggle the doctor accepting-consultations flag."""
    profile = getattr(request.user, "doctor_profile", None)
    if profile is None:
        return Response(
            {"detail": "Doctor profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = DoctorAcceptingStatusSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    desired = serializer.validated_data["is_accepting_consultations"]
    expected = serializer.validated_data.get("expected_updated_at")
    with transaction.atomic():
        locked_profile = DoctorProfile.objects.select_for_update().get(
            pk=profile.pk
        )
        if stale_timestamp(expected, locked_profile.updated_at):
            return Response(
                {"detail": "Accepting status changed.", "code": "stale_accepting_status"},
                status=status.HTTP_409_CONFLICT,
            )
        changed = locked_profile.is_accepting_consultations != desired
        if changed:
            previous = locked_profile.is_accepting_consultations
            locked_profile.is_accepting_consultations = desired
            locked_profile.save(
                update_fields=["is_accepting_consultations", "updated_at"]
            )
            create_audit_event(
                "doctor_accepting_status_updated",
                AuditEventCategory.DOCTOR,
                actor_id=str(request.user.id),
                actor_role=request.user.role,
                target_type="doctor_profile",
                target_id=str(locked_profile.id),
                summary="Doctor accepting-consultations status updated.",
                metadata={
                    "changed_fields": ["is_accepting_consultations"],
                    "previous": previous,
                    "current": desired,
                },
            )

    return Response(
        {
            "changed": changed,
            "reason": "updated" if changed else "accepting_status_unchanged",
            "profile_updated_at": locked_profile.updated_at,
            **availability_summary(locked_profile),
        }
    )
