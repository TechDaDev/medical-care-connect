from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from django.http import FileResponse

from apps.accounts.models import User, UserRole
from apps.accounts.permissions import (
    IsAdministrator,
    IsCoordinatorOrAdministrator,
)
from apps.accounts.throttles import AdminSensitiveWriteThrottle, PrivacySensitiveWriteThrottle, AuditExportThrottle
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
from apps.core.models import AuditEvent, AuditEventCategory, AuditEventSeverity, AuditEventResult, RetentionClass
from apps.core.security_events import (
    consultation_priority_changed,
    consultation_transferred,
    doctor_application_reviewed,
    doctor_license_document_accessed,
    privacy_deletion_request_viewed,
    privacy_audit_export_created,
)
from apps.core.audit_service import create_audit_event
from apps.doctors.models import DoctorProfile, LicenseDocument
from apps.messaging.models import ConsultationMessage
from apps.notifications.models import Notification, NotificationType
from apps.notifications.services import create_notification, notify_doctor_application_status
from apps.privacy.models import AccountDeletionRequest, DeletionStatus
from apps.reviews.models import ReviewReport
from apps.specialties.models import Specialty
from apps.staff.serializers import (
    DoctorWorkloadSerializer,
    PriorityUpdateSerializer,
    StaffConsultationListSerializer,
    TransferConsultationSerializer,
    AdminPrivacyDeletionListSerializer,
    AdminPrivacyDeletionDetailSerializer,
    PrivacyDeletionReviewInputSerializer,
    AuditEventListSerializer,
    AuditEventDetailSerializer,
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


# ── Doctor Application Views ────────────────────────────────────────────────

from apps.staff.serializers import (
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminUserRoleSerializer,
    AdminSessionRevocationSerializer,
    AdminUserStatusSerializer,
    DoctorApplicationListSerializer,
    DoctorApplicationDetailSerializer,
    DoctorApplicationReviewSerializer,
    get_available_actions,
)
from django.contrib.contenttypes.models import ContentType
from apps.notifications.models import NotificationType


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def doctor_application_list(request: Request) -> Response:
    """Paginated, filterable application queue. No full license number exposed."""
    queryset = DoctorProfile.objects.select_related("user", "specialty").prefetch_related(
        "license_document"
    )

    # Status filter
    status_f = request.query_params.get("status")
    if status_f:
        queryset = queryset.filter(approval_status=status_f)

    # Specialty filter
    specialty = request.query_params.get("specialty")
    if specialty:
        queryset = queryset.filter(specialty_id=specialty)

    # Date filters
    created_after = request.query_params.get("created_after")
    if created_after:
        queryset = queryset.filter(created_at__gte=created_after)

    created_before = request.query_params.get("created_before")
    if created_before:
        queryset = queryset.filter(created_at__lte=created_before)

    # Search
    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(professional_title__icontains=search)
            | Q(workplace_name__icontains=search)
        )

    # Ordering
    ordering = request.query_params.get("ordering", "created_at")
    allowed_ordering = ["created_at", "-created_at", "updated_at", "-updated_at",
                        "years_of_experience", "-years_of_experience",
                        "approval_status", "-approval_status"]
    if ordering not in allowed_ordering:
        ordering = "created_at"
    if not status_f:
        # Default: pending first, then oldest
        queryset = queryset.order_by("approval_status", ordering)
    else:
        queryset = queryset.order_by(ordering)

    paginator = StaffPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = DoctorApplicationListSerializer(
        page if page is not None else queryset, many=True
    )
    if page is not None:
        return paginator.get_paginated_response(serializer.data)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def doctor_application_detail(request: Request, profile_id: str) -> Response:
    """Full application detail with authorized fields and available actions."""
    profile = get_object_or_404(
        DoctorProfile.objects.select_related("user", "specialty").prefetch_related(
            "license_document"
        ),
        pk=profile_id,
    )
    serializer = DoctorApplicationDetailSerializer(
        profile, context={"request": request}
    )
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def review_doctor_application(request: Request, profile_id: str) -> Response:
    """Approve, reject, suspend, or reactivate with concurrency protection."""
    serializer = DoctorApplicationReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    action = serializer.validated_data["action"]
    reason = serializer.validated_data.get("reason", "")
    expected_status = serializer.validated_data.get("expected_status")

    status_map = {
        "approve": DoctorProfile.ApprovalStatus.APPROVED,
        "reject": DoctorProfile.ApprovalStatus.REJECTED,
        "suspend": DoctorProfile.ApprovalStatus.SUSPENDED,
        "reactivate": DoctorProfile.ApprovalStatus.APPROVED,
    }

    is_admin = request.user.role == UserRole.ADMINISTRATOR
    new_status = status_map[action]

    profile = get_object_or_404(
        DoctorProfile.objects.select_related("user"),
        pk=profile_id,
    )

    with transaction.atomic():
        locked = DoctorProfile.objects.select_for_update().get(pk=profile.id)

        # Concurrency check
        if expected_status and locked.approval_status != expected_status:
            return Response(
                {
                    "detail": "The application was already reviewed by another staff member.",
                    "code": "application_state_changed",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Validate transition
        allowed = get_available_actions(locked, is_admin)
        if action not in allowed:
            return Response(
                {
                    "detail": "This status transition is not allowed.",
                    "code": "invalid_status_transition",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        prev_status = locked.approval_status
        locked.approval_status = new_status
        locked.is_approved = new_status == DoctorProfile.ApprovalStatus.APPROVED
        if action == "suspend":
            locked.is_accepting_consultations = False
        locked.approval_note = reason
        locked.save(update_fields=[
            "approval_status", "is_approved", "is_accepting_consultations",
            "approval_note", "updated_at",
        ])

        # Audit event
        doctor_application_reviewed(
            user_id=str(profile.user_id),
            profile_id=str(profile.id),
            status=new_status,
            by_user=str(request.user.id),
        )

        # Notification
        notify_doctor_application_status(profile)

    # Return full updated detail
    detail = DoctorProfile.objects.select_related("user", "specialty").prefetch_related(
        "license_document"
    ).get(pk=profile.id)
    detail_serializer = DoctorApplicationDetailSerializer(
        detail, context={"request": request}
    )
    return Response(detail_serializer.data)


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
    attachment_counts = {
        state: ConsultationAttachment.objects.filter(status=state).count()
        for state in (
            AttachmentStatus.PENDING,
            AttachmentStatus.QUARANTINED,
            AttachmentStatus.REJECTED,
        )
    }
    specialty_counts = {
        "total": Specialty.objects.count(),
        "active": Specialty.objects.filter(is_active=True).count(),
        "inactive": Specialty.objects.filter(is_active=False).count(),
    }

    total_notifications = Notification.objects.count()

    return Response({
        "consultations": {
            "total": Consultation.objects.count(),
            **status_counts,
            "urgent": urgent,
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
        },
        "operations": {
            "total_notifications": total_notifications,
        },
        "specialties": specialty_counts,
        "attachments": {
            **attachment_counts,
            "retention_eligible": _get_retention_eligible_attachment_count(),
        },
        "messages": {
            "unread_messages": total_unread,
        },
        "generated_at": timezone.now().isoformat(),
    })


def _get_retention_eligible_attachment_count() -> int:
    from apps.attachments.services.retention import get_retention_cutoff

    cutoff = get_retention_cutoff()
    if cutoff is None:
        return 0
    return ConsultationAttachment.objects.filter(
        status=AttachmentStatus.DELETED,
        is_deleted=True,
        deleted_at__lt=cutoff,
        storage_deleted_at__isnull=True,
        consultation__status__in=[
            ConsultationStatus.COMPLETED,
            ConsultationStatus.CANCELLED,
        ],
    ).count()


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
    """Stream a doctor's license document to authorized staff only.

    Security: no storage path leaked, quarantined/rejected profiles denied,
    safe headers set, audit event recorded.
    """
    profile = get_object_or_404(DoctorProfile, id=profile_id)

    # Deny access for quarantined/unavailable profiles
    if profile.approval_status == DoctorProfile.ApprovalStatus.REJECTED:
        return Response(
            {"detail": "License document is not available for rejected applications.",
             "code": "document_unavailable"},
            status=status.HTTP_403_FORBIDDEN,
        )

    license_doc = get_object_or_404(LicenseDocument, doctor_profile=profile)

    # Deny quarantined documents
    from apps.attachments.choices import ScanStatus
    if license_doc.scan_status == ScanStatus.INFECTED:
        return Response(
            {"detail": "This document is quarantined and cannot be accessed.",
             "code": "document_quarantined"},
            status=status.HTTP_403_FORBIDDEN,
        )

    backend = get_storage_backend()
    stream = backend.open(license_doc.storage_key)
    if stream is None:
        return Response(
            {"detail": "License document not found on storage.", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Audit event
    doctor_license_document_accessed(
        actor_id=str(request.user.id),
        profile_id=str(profile.id),
        document_id=str(license_doc.id),
    )

    # Sanitize filename
    safe_name = license_doc.original_filename.replace(" ", "_")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._-")

    response = FileResponse(stream, as_attachment=True)
    response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    if license_doc.declared_mime_type:
        response["Content-Type"] = license_doc.declared_mime_type
    return response


# ── Admin User Management ────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdministrator])
def admin_user_list(request: Request) -> Response:
    """Paginated, filterable user list for administrators only."""
    queryset = User.objects.prefetch_related(
        "doctor_profile", "patient_profile"
    ).only(
        "id", "email", "first_name", "last_name", "role", "is_active",
        "is_staff", "date_joined", "last_login",
    )

    # Role filter
    role_f = request.query_params.get("role")
    if role_f:
        queryset = queryset.filter(role=role_f)

    # Active filter
    active_f = request.query_params.get("active")
    if active_f is not None and active_f.lower() in ("true", "1"):
        queryset = queryset.filter(is_active=True)
    elif active_f is not None and active_f.lower() in ("false", "0"):
        queryset = queryset.filter(is_active=False)

    # Search
    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(id__icontains=search)
        )

    # Date filters
    created_after = request.query_params.get("created_after")
    if created_after:
        queryset = queryset.filter(date_joined__gte=created_after)

    created_before = request.query_params.get("created_before")
    if created_before:
        queryset = queryset.filter(date_joined__lte=created_before)

    last_login_after = request.query_params.get("last_login_after")
    if last_login_after:
        queryset = queryset.filter(last_login__gte=last_login_after)

    last_login_before = request.query_params.get("last_login_before")
    if last_login_before:
        queryset = queryset.filter(last_login__lte=last_login_before)

    # Ordering
    ordering = request.query_params.get("ordering", "-date_joined")
    allowed_orderings = [
        "date_joined", "-date_joined",
        "last_login", "-last_login",
        "email", "-email",
        "role", "-role",
        "is_active", "-is_active",
        "first_name", "-first_name",
    ]
    if ordering not in allowed_orderings:
        ordering = "-date_joined"
    queryset = queryset.order_by(ordering)

    paginator = StaffPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = AdminUserListSerializer(
        page if page is not None else queryset, many=True,
        context={"request": request},
    )
    if page is not None:
        return paginator.get_paginated_response(serializer.data)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdministrator])
def admin_user_detail(request: Request, user_id: str) -> Response:
    """Safe administrative detail view."""
    user = get_object_or_404(
        User.objects.prefetch_related("doctor_profile", "patient_profile"),
        pk=user_id,
    )
    serializer = AdminUserDetailSerializer(
        user, context={"request": request},
    )
    return Response(serializer.data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def admin_user_status(request: Request, user_id: str) -> Response:
    """Activate or deactivate a user with safety checks."""
    serializer = AdminUserStatusSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    is_active = serializer.validated_data["is_active"]
    reason = serializer.validated_data["reason"]
    expected_is_active = serializer.validated_data.get("expected_is_active")

    from apps.accounts.services.admin_users import (
        activate_user,
        deactivate_user,
        AdminUserError,
        SelfActionForbidden,
        FinalAdministratorProtected,
        StateConflict,
    )

    try:
        if is_active:
            target = activate_user(
                actor=request.user,
                target_id=user_id,
                reason=reason,
                expected_active=expected_is_active,
            )
        else:
            target = deactivate_user(
                actor=request.user,
                target_id=user_id,
                reason=reason,
                expected_active=expected_is_active,
            )
    except SelfActionForbidden:
        return Response(
            {"detail": "You cannot deactivate your own account.",
             "code": "self_action_forbidden"},
            status=status.HTTP_409_CONFLICT,
        )
    except FinalAdministratorProtected:
        return Response(
            {"detail": "The final active administrator cannot be deactivated.",
             "code": "final_administrator_protected"},
            status=status.HTTP_409_CONFLICT,
        )
    except StateConflict as e:
        return Response(
            {"detail": e.detail, "code": e.code},
            status=status.HTTP_409_CONFLICT,
        )

    result = AdminUserDetailSerializer(
        target, context={"request": request},
    )
    notification_title = "Activated" if is_active else "Deactivated"
    return Response({
        "detail": f"User {notification_title}.",
        "user": result.data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def admin_user_revoke_sessions(request: Request, user_id: str) -> Response:
    """Revoke all outstanding sessions for a user."""
    serializer = AdminSessionRevocationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    reason = serializer.validated_data["reason"]

    from apps.accounts.services.admin_users import (
        revoke_sessions,
        AdminUserError,
        SelfActionForbidden,
    )

    try:
        revoked, target = revoke_sessions(
            actor=request.user,
            target_id=user_id,
            reason=reason,
        )
    except SelfActionForbidden:
        return Response(
            {"detail": "You cannot revoke sessions for your own account through this workflow.",
             "code": "self_action_forbidden"},
            status=status.HTTP_409_CONFLICT,
        )

    result = AdminUserDetailSerializer(
        target, context={"request": request},
    )
    return Response({
        "detail": f"{revoked} session(s) revoked.",
        "revoked_sessions": revoked,
        "user": result.data,
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def admin_user_role(request: Request, user_id: str) -> Response:
    """Change a user's role with safety checks."""
    serializer = AdminUserRoleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    new_role = serializer.validated_data["role"]
    reason = serializer.validated_data["reason"]
    expected_role = serializer.validated_data.get("expected_role")

    from apps.accounts.services.admin_users import (
        change_user_role,
        AdminUserError,
        SelfActionForbidden,
        FinalAdministratorProtected,
        InvalidRoleTransition,
        StateConflict,
    )

    try:
        target = change_user_role(
            actor=request.user,
            target_id=user_id,
            new_role=new_role,
            reason=reason,
            expected_role=expected_role,
        )
    except SelfActionForbidden:
        return Response(
            {"detail": "You cannot change your own role.",
             "code": "self_action_forbidden"},
            status=status.HTTP_409_CONFLICT,
        )
    except FinalAdministratorProtected:
        return Response(
            {"detail": "The final active administrator cannot be demoted.",
             "code": "final_administrator_protected"},
            status=status.HTTP_409_CONFLICT,
        )
    except InvalidRoleTransition:
        return Response(
            {"detail": "This role transition is not allowed.",
             "code": "invalid_role_transition"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except StateConflict as e:
        return Response(
            {"detail": e.detail, "code": e.code},
            status=status.HTTP_409_CONFLICT,
        )

    result = AdminUserDetailSerializer(
        target, context={"request": request},
    )
    return Response({
        "detail": "User role updated.",
        "user": result.data,
    })


# ── Privacy Deletion Admin Views ────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdministrator])
def privacy_deletion_list(request: Request) -> Response:
    """Administrator-only privacy deletion request queue."""
    queryset = AccountDeletionRequest.objects.select_related(
        "subject_user", "reviewed_by"
    )

    # Status filter
    status_f = request.query_params.get("status")
    if status_f:
        queryset = queryset.filter(status=status_f)

    # Requester role filter
    requester_role = request.query_params.get("requester_role")
    if requester_role:
        queryset = queryset.filter(subject_user__role=requester_role)

    # Date filters
    created_after = request.query_params.get("created_after")
    if created_after:
        queryset = queryset.filter(requested_at__gte=created_after)

    created_before = request.query_params.get("created_before")
    if created_before:
        queryset = queryset.filter(requested_at__lte=created_before)

    decided_after = request.query_params.get("decided_after")
    if decided_after:
        queryset = queryset.filter(reviewed_at__gte=decided_after)

    decided_before = request.query_params.get("decided_before")
    if decided_before:
        queryset = queryset.filter(reviewed_at__lte=decided_before)

    # Search — safe fields only
    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(
            Q(id__icontains=search)
            | Q(subject_user__first_name__icontains=search)
            | Q(subject_user__last_name__icontains=search)
            | Q(subject_user__email__icontains=search)
            | Q(subject_user__id__icontains=search)
        )

    # Ordering
    ordering = request.query_params.get("ordering", "-requested_at")
    allowed_orderings = [
        "requested_at", "-requested_at",
        "reviewed_at", "-reviewed_at",
        "completed_at", "-completed_at",
        "status", "-status",
    ]
    if ordering not in allowed_orderings:
        ordering = "-requested_at"
    queryset = queryset.order_by(ordering)

    paginator = StaffPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = AdminPrivacyDeletionListSerializer(
        page if page is not None else queryset, many=True
    )
    if page is not None:
        return paginator.get_paginated_response(serializer.data)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdministrator])
def privacy_deletion_detail(request: Request, request_id: str) -> Response:
    """Administrator-only privacy deletion request detail."""
    dr = get_object_or_404(
        AccountDeletionRequest.objects.select_related("subject_user", "reviewed_by"),
        pk=request_id,
    )

    privacy_deletion_request_viewed(
        actor_id=str(request.user.id),
        request_id=str(dr.id),
    )

    serializer = AdminPrivacyDeletionDetailSerializer(dr)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAdministrator])
@throttle_classes([PrivacySensitiveWriteThrottle])
def privacy_deletion_review(request: Request, request_id: str) -> Response:
    """Administrator approve or reject a deletion request."""
    serializer = PrivacyDeletionReviewInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    action = serializer.validated_data["action"]
    reason = serializer.validated_data.get("reason", "")
    expected_status = serializer.validated_data.get("expected_status")

    try:
        dr = AccountDeletionRequest.objects.get(id=request_id)
    except AccountDeletionRequest.DoesNotExist:
        return Response(
            {"detail": "Not found.", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    with transaction.atomic():
        locked = AccountDeletionRequest.objects.select_for_update().get(pk=dr.id)

        if action == "approve":
            if locked.status != DeletionStatus.PENDING:
                return Response(
                    {"detail": "This privacy request can no longer be reviewed.",
                     "code": "invalid_privacy_request_transition"},
                    status=status.HTTP_409_CONFLICT,
                )
            if expected_status is not None and locked.status != expected_status:
                return Response(
                    {"detail": "The request state changed concurrently.",
                     "code": "request_state_changed"},
                    status=status.HTTP_409_CONFLICT,
                )
            locked.status = DeletionStatus.APPROVED
            locked.reviewed_at = timezone.now()
            locked.reviewed_by = request.user
            locked.rejection_reason = ""
            locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "rejection_reason"])

            create_audit_event(
                event_type="privacy.deletion.approved",
                category=AuditEventCategory.PRIVACY,
                severity=AuditEventSeverity.INFO,
                result=AuditEventResult.SUCCESS,
                actor_id=str(request.user.id),
                actor_role=request.user.role,
                target_type="AccountDeletionRequest",
                target_id=str(locked.id),
                summary=f"Deletion request {locked.id} approved",
                retention_class=RetentionClass.PRIVACY_DECISION,
            )

            from apps.notifications.services import create_notification
            from apps.notifications.models import NotificationType
            try:
                create_notification(
                    recipient=locked.subject_user,
                    notification_type=NotificationType.PRIVACY_DELETION_APPROVED,
                    title="Deletion Request Approved",
                    body="Your account deletion request has been approved.",
                )
            except Exception:
                pass
        else:
            if locked.status != DeletionStatus.PENDING:
                return Response(
                    {"detail": "This privacy request can no longer be reviewed.",
                     "code": "invalid_privacy_request_transition"},
                    status=status.HTTP_409_CONFLICT,
                )
            if expected_status is not None and locked.status != expected_status:
                return Response(
                    {"detail": "The request state changed concurrently.",
                     "code": "request_state_changed"},
                    status=status.HTTP_409_CONFLICT,
                )
            locked.status = DeletionStatus.REJECTED
            locked.reviewed_at = timezone.now()
            locked.reviewed_by = request.user
            locked.rejection_reason = reason
            locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "rejection_reason"])

            create_audit_event(
                event_type="privacy.deletion.rejected",
                category=AuditEventCategory.PRIVACY,
                severity=AuditEventSeverity.INFO,
                result=AuditEventResult.DENIED,
                actor_id=str(request.user.id),
                actor_role=request.user.role,
                target_type="AccountDeletionRequest",
                target_id=str(locked.id),
                summary=f"Deletion request {locked.id} rejected",
                metadata={"reason_present": bool(reason)},
                retention_class=RetentionClass.PRIVACY_DECISION,
            )

            from apps.notifications.services import create_notification
            from apps.notifications.models import NotificationType
            try:
                create_notification(
                    recipient=locked.subject_user,
                    notification_type=NotificationType.PRIVACY_DELETION_REJECTED,
                    title="Deletion Request Rejected",
                    body="Your account deletion request has been reviewed.",
                )
            except Exception:
                pass

    detail = AccountDeletionRequest.objects.select_related(
        "subject_user", "reviewed_by"
    ).get(pk=request_id)
    result_serializer = AdminPrivacyDeletionDetailSerializer(detail)
    return Response(result_serializer.data)


# ── Audit Event Views ───────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdministrator])
def audit_event_list(request: Request) -> Response:
    """Administrator-only audit event list with filters."""
    queryset = AuditEvent.objects.all()

    # Event type filter
    event_type = request.query_params.get("event_type")
    if event_type:
        queryset = queryset.filter(event_type=event_type)

    # Category filter
    category = request.query_params.get("category")
    if category:
        queryset = queryset.filter(category=category)

    # Severity filter
    severity = request.query_params.get("severity")
    if severity:
        queryset = queryset.filter(severity=severity)

    # Result filter
    result = request.query_params.get("result")
    if result:
        queryset = queryset.filter(result=result)

    # Actor filter
    actor_id = request.query_params.get("actor_id")
    if actor_id:
        queryset = queryset.filter(actor_id=actor_id)

    # Target filter
    target_type = request.query_params.get("target_type")
    if target_type:
        queryset = queryset.filter(target_type=target_type)

    target_id = request.query_params.get("target_id")
    if target_id:
        queryset = queryset.filter(target_id=target_id)

    # Date filters
    created_after = request.query_params.get("created_after")
    if created_after:
        queryset = queryset.filter(occurred_at__gte=created_after)

    created_before = request.query_params.get("created_before")
    if created_before:
        queryset = queryset.filter(occurred_at__lte=created_before)

    # Request ID filter
    request_id = request.query_params.get("request_id")
    if request_id:
        queryset = queryset.filter(request_id__icontains=request_id)

    # Search — safe fields only
    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(
            Q(event_type__icontains=search)
            | Q(summary__icontains=search)
            | Q(target_type__icontains=search)
            | Q(target_id__icontains=search)
        )

    # Ordering
    ordering = request.query_params.get("ordering", "-occurred_at")
    allowed_orderings = [
        "occurred_at", "-occurred_at",
        "event_type", "-event_type",
        "category", "-category",
        "severity", "-severity",
        "result", "-result",
    ]
    if ordering not in allowed_orderings:
        ordering = "-occurred_at"
    queryset = queryset.order_by(ordering)

    paginator = StaffPagination()
    paginator.page_size = 50
    page = paginator.paginate_queryset(queryset, request)
    serializer = AuditEventListSerializer(
        page if page is not None else queryset, many=True
    )
    if page is not None:
        return paginator.get_paginated_response(serializer.data)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdministrator])
def audit_event_detail(request: Request, event_id: str) -> Response:
    """Administrator-only audit event detail."""
    event = get_object_or_404(AuditEvent, pk=event_id)
    serializer = AuditEventDetailSerializer(event)
    return Response(serializer.data)


def _sanitize_csv_value(value: str) -> str:
    """Neutralize CSV formula injection."""
    if not value:
        return value
    dangerous = ("=", "+", "-", "@")
    if value.startswith(dangerous):
        return "'" + value
    return value


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdministrator])
@throttle_classes([AuditExportThrottle])
def audit_event_csv_export(request: Request) -> Response:
    """Administrator-only sanitized CSV export of audit events."""
    from django.http import HttpResponse
    import csv
    import io

    max_rows = 10000
    date_after = request.query_params.get("created_after")
    date_before = request.query_params.get("created_before")

    if not date_after and not date_before:
        return Response(
            {"detail": "Date range required for CSV export. Use created_after and/or created_before.",
             "code": "date_range_required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queryset = AuditEvent.objects.all().order_by("-occurred_at")

    event_type = request.query_params.get("event_type")
    if event_type:
        queryset = queryset.filter(event_type=event_type)

    category = request.query_params.get("category")
    if category:
        queryset = queryset.filter(category=category)

    severity = request.query_params.get("severity")
    if severity:
        queryset = queryset.filter(severity=severity)

    result = request.query_params.get("result")
    if result:
        queryset = queryset.filter(result=result)

    actor_id = request.query_params.get("actor_id")
    if actor_id:
        queryset = queryset.filter(actor_id=actor_id)

    if date_after:
        queryset = queryset.filter(occurred_at__gte=date_after)

    if date_before:
        queryset = queryset.filter(occurred_at__lte=date_before)

    if queryset.count() > max_rows:
        queryset = queryset[:max_rows]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Event ID", "Timestamp", "Event Type", "Category", "Severity",
        "Result", "Actor ID", "Actor Name", "Actor Role",
        "Target Type", "Target ID", "Request ID", "Summary",
    ])

    for event in queryset.select_related():
        actor_name = ""
        actor_role = event.actor_role or ""
        if event.actor_id:
            from apps.accounts.models import User
            try:
                user = User.objects.get(id=event.actor_id)
                actor_name = user.full_name
            except User.DoesNotExist:
                pass

        writer.writerow([
            _sanitize_csv_value(str(event.id)),
            _sanitize_csv_value(event.occurred_at.isoformat()),
            _sanitize_csv_value(event.event_type),
            _sanitize_csv_value(event.category),
            _sanitize_csv_value(event.severity),
            _sanitize_csv_value(event.result),
            _sanitize_csv_value(str(event.actor_id) if event.actor_id else ""),
            _sanitize_csv_value(actor_name),
            _sanitize_csv_value(actor_role),
            _sanitize_csv_value(event.target_type),
            _sanitize_csv_value(event.target_id),
            _sanitize_csv_value(event.request_id),
            _sanitize_csv_value(event.summary),
        ])

    csv_content = output.getvalue()
    output.close()

    # Audit the export
    privacy_audit_export_created(actor_id=str(request.user.id))

    response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="audit-export.csv"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
