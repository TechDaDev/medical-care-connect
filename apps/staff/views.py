from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import UserRole
from apps.accounts.permissions import (
    IsCoordinatorOrAdministrator,
)
from apps.core.security_events import (
    consultation_priority_changed,
    consultation_transferred,
)
from apps.consultations.models import (
    Consultation,
    ConsultationPriorityChange,
    ConsultationStatus,
    ConsultationTransfer,
)
from apps.doctors.models import DoctorProfile
from apps.messaging.models import ConsultationMessage
from apps.notifications.models import Notification, NotificationType
from apps.notifications.services import create_notification
from apps.staff.serializers import (
    DoctorWorkloadSerializer,
    PriorityUpdateSerializer,
    StaffConsultationListSerializer,
    TransferConsultationSerializer,
)

_ACTIVE_STATUSES = (
    ConsultationStatus.SUBMITTED,
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.INTAKE_IN_PROGRESS,
    ConsultationStatus.INTAKE_COMPLETED,
    ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.AWAITING_PATIENT_RESPONSE,
    ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
    ConsultationStatus.UNDER_REVIEW,
)


class StaffPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ── Staff Dashboard ─────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def staff_dashboard(request: Request) -> Response:
    """Operational summary for coordinators and administrators."""
    status_counts = {}
    for s in ConsultationStatus.values:
        status_counts[s] = Consultation.objects.filter(status=s).count()

    urgent_count = Consultation.objects.filter(
        status__in=_ACTIVE_STATUSES,
    ).count()

    unassigned_count = Consultation.objects.filter(
        status=ConsultationStatus.SUBMITTED,
    ).count()

    approved = DoctorProfile.objects.filter(is_approved=True).count()
    accepting = DoctorProfile.objects.filter(
        is_approved=True, is_accepting_consultations=True
    ).count()
    not_accepting = approved - accepting

    total_unread = ConsultationMessage.objects.exclude(
        read_receipts__user=request.user
    ).count()

    return Response({
        "consultations": {
            "total": Consultation.objects.count(),
            **status_counts,
        },
        "urgent_count": urgent_count,
        "unassigned_count": unassigned_count,
        "doctors": {
            "approved": approved,
            "accepting": accepting,
            "not_accepting": not_accepting,
        },
        "messages": {
            "unread_visible": total_unread,
        },
    })


# ── Staff Consultation List ─────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def staff_consultation_list(request: Request) -> Response:
    """List all consultations with staff filters."""
    queryset = Consultation.objects.select_related(
        "patient__user", "doctor__user", "specialty"
    )

    status_f = request.query_params.get("status")
    if status_f:
        queryset = queryset.filter(status=status_f)

    priority = request.query_params.get("priority")
    if priority:
        queryset = queryset.filter(priority=priority)

    specialty = request.query_params.get("specialty")
    if specialty:
        queryset = queryset.filter(specialty_id=specialty)

    doctor = request.query_params.get("doctor")
    if doctor:
        queryset = queryset.filter(doctor_id=doctor)

    patient = request.query_params.get("patient")
    if patient:
        queryset = queryset.filter(patient_id=patient)

    created_after = request.query_params.get("created_after")
    if created_after:
        queryset = queryset.filter(created_at__gte=created_after)

    created_before = request.query_params.get("created_before")
    if created_before:
        queryset = queryset.filter(created_at__lte=created_before)

    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(
            Q(id__icontains=search)
            | Q(patient__user__first_name__icontains=search)
            | Q(patient__user__last_name__icontains=search)
            | Q(patient__user__email__icontains=search)
            | Q(doctor__user__first_name__icontains=search)
            | Q(doctor__user__last_name__icontains=search)
            | Q(doctor__user__email__icontains=search)
            | Q(description__icontains=search)
        )

    queryset = queryset.order_by("-created_at")
    paginator = StaffPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = StaffConsultationListSerializer(
        page if page is not None else queryset, many=True
    )
    if page is not None:
        return paginator.get_paginated_response(serializer.data)
    return Response(serializer.data)


# ── Consultation Transfer ───────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def transfer_consultation(request: Request, consultation_id: str) -> Response:
    """Transfer a consultation to another doctor."""
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            "patient__user", "doctor__user", "specialty"
        ),
        pk=consultation_id,
    )

    if consultation.status in (
        ConsultationStatus.COMPLETED,
        ConsultationStatus.CANCELLED,
    ):
        return Response(
            {"detail": "Cannot transfer a completed or cancelled consultation.",
             "code": "validation_error"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = TransferConsultationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    new_doctor = get_object_or_404(
        DoctorProfile.objects.select_related("user"),
        pk=serializer.validated_data["doctor_id"],
    )

    if not new_doctor.is_approved:
        return Response(
            {"detail": "Target doctor is not approved.",
             "code": "validation_error"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not new_doctor.user.is_active:
        return Response(
            {"detail": "Target doctor account is not active.",
             "code": "validation_error"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not new_doctor.specialty:
        return Response(
            {"detail": "Target doctor does not have a specialty assigned.",
             "code": "validation_error"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    previous_doctor = consultation.doctor
    reason = serializer.validated_data["reason"]

    from django.db import transaction
    with transaction.atomic():
        ConsultationTransfer.objects.create(
            consultation=consultation,
            previous_doctor=previous_doctor,
            new_doctor=new_doctor,
            transferred_by=request.user,
            reason=reason,
        )

        consultation.doctor = new_doctor
        consultation.specialty = new_doctor.specialty
        consultation.status = ConsultationStatus.TRANSFERRED
        consultation.save(update_fields=[
            "doctor", "specialty", "status", "updated_at",
        ])

        for recipient, title, body in [
            (consultation.patient.user, "Consultation Transferred",
             "Your consultation has been transferred to a new doctor."),
            (previous_doctor.user if previous_doctor else None,
             "Consultation Transferred",
             "A consultation has been transferred from you."),
            (new_doctor.user, "New Consultation Transferred",
             "A consultation has been transferred to you."),
        ]:
            if recipient:
                create_notification(
                    recipient=recipient,
                    notification_type=NotificationType.STATUS_CHANGE,
                    title=title,
                    body=body,
                    consultation=consultation,
                )

    consultation_transferred(
        consultation_id=str(consultation.id),
        from_doctor=str(previous_doctor.id) if previous_doctor else "",
        to_doctor=str(new_doctor.id),
        by_user=str(request.user.id),
    )

    return Response({"detail": "Consultation transferred successfully."})


# ── Priority Update ─────────────────────────────────────────────────────────


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def update_priority(request: Request, consultation_id: str) -> Response:
    """Update consultation priority."""
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            "patient__user", "doctor__user"
        ),
        pk=consultation_id,
    )

    if consultation.status in (
        ConsultationStatus.COMPLETED,
        ConsultationStatus.CANCELLED,
    ):
        return Response(
            {"detail": "Cannot change priority of a completed or cancelled consultation.",
             "code": "validation_error"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = PriorityUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    previous_priority = consultation.priority
    new_priority = serializer.validated_data["priority"]

    if previous_priority == new_priority:
        return Response({"detail": "Priority unchanged."})

    ConsultationPriorityChange.objects.create(
        consultation=consultation,
        previous_priority=previous_priority,
        new_priority=new_priority,
        changed_by=request.user,
    )

    consultation.priority = new_priority
    consultation.save(update_fields=["priority", "updated_at"])

    consultation_priority_changed(
        consultation_id=str(consultation.id),
        old=str(previous_priority) if previous_priority else "",
        new=str(new_priority),
        by_user=str(request.user.id),
    )

    return Response({
        "detail": "Priority updated.",
        "previous_priority": previous_priority,
        "new_priority": new_priority,
    })


# ── Doctor Workload ─────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def doctor_workload(request: Request) -> Response:
    """Aggregate workload summary per doctor."""
    queryset = DoctorProfile.objects.select_related("user", "specialty").filter(
        is_approved=True
    )

    specialty = request.query_params.get("specialty")
    if specialty:
        queryset = queryset.filter(specialty_id=specialty)

    accepting = request.query_params.get("accepting")
    if accepting and accepting.lower() in ("true", "1"):
        queryset = queryset.filter(is_accepting_consultations=True)

    approved_filter = request.query_params.get("approved")
    if approved_filter and approved_filter.lower() in ("false", "0"):
        queryset = DoctorProfile.objects.all()

    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    results = []
    for doc in queryset:
        active_count = Consultation.objects.filter(
            doctor=doc, status__in=_ACTIVE_STATUSES
        ).count()
        submitted_count = Consultation.objects.filter(
            doctor=doc, status=ConsultationStatus.SUBMITTED
        ).count()
        accepted_count = Consultation.objects.filter(
            doctor=doc, status=ConsultationStatus.ACCEPTED
        ).count()
        intake_completed_count = Consultation.objects.filter(
            doctor=doc, status=ConsultationStatus.INTAKE_COMPLETED
        ).count()
        doctor_review_count = Consultation.objects.filter(
            doctor=doc, status=ConsultationStatus.DOCTOR_REVIEW
        ).count()

        results.append({
            "id": doc.id,
            "full_name": doc.user.full_name,
            "specialty_name": doc.specialty.name if doc.specialty else None,
            "is_approved": doc.is_approved,
            "is_accepting_consultations": doc.is_accepting_consultations,
            "active_count": active_count,
            "submitted_count": submitted_count,
            "accepted_count": accepted_count,
            "intake_completed_count": intake_completed_count,
            "doctor_review_count": doctor_review_count,
            "estimated_response_minutes": doc.estimated_response_minutes,
        })

    return Response(results)
