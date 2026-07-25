from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from django.http import FileResponse

from apps.accounts.models import User, UserRole
from apps.accounts.permissions import (
    IsCoordinatorOrAdministrator,
)
from apps.attachments.choices import AttachmentStatus
from apps.attachments.models import ConsultationAttachment
from apps.attachments.services.factory import get_storage_backend
from apps.consultations.models import (
    Consultation,
    ConsultationPriorityChange,
    ConsultationStatus,
    ConsultationTransfer,
    Priority,
)
from apps.core.security_events import (
    consultation_priority_changed,
    consultation_transferred,
    doctor_application_reviewed,
)
from apps.doctors.models import DoctorProfile, LicenseDocument
from apps.messaging.models import ConsultationMessage
from apps.notifications.models import Notification, NotificationType
from apps.notifications.services import create_notification, notify_doctor_application_status
from apps.privacy.models import AccountDeletionRequest, DeletionStatus
from apps.reviews.models import ReviewReport
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


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def doctor_application_list(request: Request) -> Response:
    """Authorized application queue. License data stays staff-only."""
    queryset = DoctorProfile.objects.select_related("user", "specialty").filter(
        approval_status=request.query_params.get("status", "pending")
    ).order_by("created_at")
    return Response([
        {
            "id": str(profile.id), "name": profile.user.full_name,
            "specialty": profile.specialty.name if profile.specialty else None,
            "years_of_experience": profile.years_of_experience,
            "workplace_name": profile.workplace_name, "biography": profile.biography,
            "license_number": profile.license_number, "approval_status": profile.approval_status,
            "created_at": profile.created_at,
        }
        for profile in queryset
    ])


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def review_doctor_application(request: Request, profile_id: str) -> Response:
    """Approve, reject, or suspend application; status remains server-owned."""
    action = request.data.get("action")
    status_map = {
        "approve": DoctorProfile.ApprovalStatus.APPROVED,
        "reject": DoctorProfile.ApprovalStatus.REJECTED,
        "suspend": DoctorProfile.ApprovalStatus.SUSPENDED,
    }
    if action not in status_map:
        return Response({"detail": "Invalid review action."}, status=status.HTTP_400_BAD_REQUEST)
    note = str(request.data.get("reason", "")).strip()
    if len(note) > 500:
        return Response({"detail": "Reason is too long."}, status=status.HTTP_400_BAD_REQUEST)

    profile = get_object_or_404(DoctorProfile.objects.select_related("user"), pk=profile_id)
    new_status = status_map[action]
    with transaction.atomic():
        profile.approval_status = new_status
        profile.is_approved = new_status == DoctorProfile.ApprovalStatus.APPROVED
        if not profile.is_approved:
            profile.is_accepting_consultations = False
        profile.approval_note = note
        profile.save(update_fields=[
            "approval_status", "is_approved", "is_accepting_consultations",
            "approval_note", "updated_at",
        ])
        doctor_application_reviewed(
            str(profile.user_id), str(profile.id), new_status, str(request.user.id)
        )
        notify_doctor_application_status(profile)
    return Response({"id": str(profile.id), "approval_status": profile.approval_status})


# ── Staff Dashboard ─────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def staff_dashboard(request: Request) -> Response:
    """Operational summary for coordinators and administrators."""
    status_counts = {}
    for s in ConsultationStatus.values:
        status_counts[s] = Consultation.objects.filter(status=s).count()

    urgent = Consultation.objects.filter(
        status__in=_ACTIVE_STATUSES,
        priority=Priority.URGENT,
    ).count()

    unassigned = Consultation.objects.filter(
        status=ConsultationStatus.SUBMITTED,
    ).count()

    approved = DoctorProfile.objects.filter(
        is_approved=True, user__is_active=True
    ).count()
    pending = DoctorProfile.objects.filter(
        approval_status=DoctorProfile.ApprovalStatus.PENDING
    ).count()
    rejected = DoctorProfile.objects.filter(
        approval_status=DoctorProfile.ApprovalStatus.REJECTED
    ).count()
    suspended = DoctorProfile.objects.filter(
        approval_status=DoctorProfile.ApprovalStatus.SUSPENDED
    ).count()
    total_doctors = DoctorProfile.objects.count()
    accepting = DoctorProfile.objects.filter(
        is_approved=True, is_accepting_consultations=True, user__is_active=True
    ).count()
    non_accepting = DoctorProfile.objects.filter(
        is_approved=True, is_accepting_consultations=False, user__is_active=True
    ).count()

    total_unread = ConsultationMessage.objects.exclude(
        read_receipts__user=request.user
    ).count()

    users_by_role = {}
    for r, _ in UserRole.choices:
        users_by_role[r] = User.objects.filter(role=r, is_active=True).count()
    total_users = User.objects.count()
    inactive_users = User.objects.filter(is_active=False).count()

    pending_applications = DoctorProfile.objects.filter(
        approval_status=DoctorProfile.ApprovalStatus.PENDING
    ).count()

    pending_deletions = AccountDeletionRequest.objects.exclude(
        status__in=[DeletionStatus.COMPLETED, DeletionStatus.CANCELLED]
    ).count()

    pending_reports = ReviewReport.objects.filter(
        resolved_at__isnull=True
    ).count()

    quarantined_attachments = ConsultationAttachment.objects.filter(
        status=AttachmentStatus.QUARANTINED
    ).count()

    pending_notifications = Notification.objects.count()

    return Response({
        "consultations": {
            "total": Consultation.objects.count(),
            **status_counts,
            "urgent": urgent,
            "unassigned": unassigned,
        },
        "doctors": {
            "total": total_doctors,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "suspended": suspended,
            "accepting": accepting,
            "non_accepting": non_accepting,
        },
        "users": {
            "total": total_users,
            **users_by_role,
            "inactive": inactive_users,
        },
        "queues": {
            "pending_applications": pending_applications,
            "pending_deletions": pending_deletions,
            "pending_reports": pending_reports,
            "quarantined_attachments": quarantined_attachments,
            "pending_notifications": pending_notifications,
        },
        "messages": {
            "unread_messages": total_unread,
        },
        "generated_at": timezone.now().isoformat(),
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


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def download_license_document(request: Request, profile_id: str) -> Response:
    """Stream a doctor's license document to authorized staff only."""
    profile = get_object_or_404(DoctorProfile, id=profile_id)
    license_doc = get_object_or_404(LicenseDocument, doctor_profile=profile)

    backend = get_storage_backend()
    stream = backend.open(license_doc.storage_key)
    if stream is None:
        return Response(
            {"detail": "License document not found on storage.", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return FileResponse(stream, filename=license_doc.original_filename, as_attachment=True)
