import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from apps.accounts.permissions import IsAdministrator
from apps.accounts.throttles import AdminSensitiveWriteThrottle
from apps.attachments.choices import AttachmentEventType, AttachmentStatus, ScanStatus
from apps.attachments.models import AttachmentAuditEvent, ConsultationAttachment
from apps.attachments.services.factory import get_storage_backend
from apps.attachments.services.scanning import (
    ClamavAttachmentScanner,
    ScanVerdict,
)
from apps.consultations.models import ConsultationStatus
from apps.core.audit_service import create_audit_event
from apps.core.models import (
    AuditEventCategory,
    AuditEventResult,
    AuditEventSeverity,
    RetentionClass,
)
from apps.specialties.models import Specialty
from apps.staff.phase_e_serializers import (
    AdminAttachmentDetailSerializer,
    AdminAttachmentListSerializer,
    AttachmentAdminActionSerializer,
    SpecialtyAdminDetailSerializer,
    SpecialtyAdminListSerializer,
    SpecialtyAdminWriteSerializer,
    SpecialtyReorderSerializer,
    specialty_admin_queryset,
)
from apps.staff.views import StaffPagination


def _request_id(request) -> str:
    return request.headers.get("X-Request-ID", "")[:100]


def _audit_admin_action(
    request,
    event_type: str,
    target_type: str,
    target_id,
    *,
    result: str = AuditEventResult.SUCCESS,
    metadata: dict | None = None,
) -> None:
    create_audit_event(
        event_type,
        AuditEventCategory.SYSTEM,
        severity=(
            AuditEventSeverity.WARNING
            if result != AuditEventResult.SUCCESS
            else AuditEventSeverity.INFO
        ),
        result=result,
        actor_id=str(request.user.id),
        actor_role=request.user.role,
        target_type=target_type,
        target_id=str(target_id),
        request_id=_request_id(request),
        summary=event_type.replace("_", " "),
        metadata=metadata,
        source="staff.phase_e",
        retention_class=RetentionClass.SECURITY_CRITICAL,
    )


def _attachment_audit(attachment, request, event_type, metadata=None) -> None:
    AttachmentAuditEvent.objects.create(
        attachment=attachment,
        actor=request.user,
        event_type=event_type,
        safe_metadata=metadata or {},
    )


@api_view(["GET", "POST"])
@permission_classes([IsAdministrator])
def specialty_admin_list_create(request):
    if request.method == "POST":
        serializer = SpecialtyAdminWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            specialty = serializer.save()
            _audit_admin_action(
                request, "specialty_created", "specialty", specialty.id
            )
        detail = specialty_admin_queryset().get(pk=specialty.pk)
        return Response(
            SpecialtyAdminDetailSerializer(detail).data,
            status=status.HTTP_201_CREATED,
        )

    queryset = specialty_admin_queryset()
    active = request.query_params.get("active")
    if active in ("true", "1"):
        queryset = queryset.filter(is_active=True)
    elif active in ("false", "0"):
        queryset = queryset.filter(is_active=False)

    search = request.query_params.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(name_en__icontains=search)
            | Q(name_ar__icontains=search)
            | Q(name_ckb__icontains=search)
            | Q(slug__icontains=search)
        )

    ordering = request.query_params.get("ordering", "display_order")
    ordering_map = {
        "display_order": "display_order",
        "-display_order": "-display_order",
        "name_en": "name_en",
        "-name_en": "-name_en",
        "doctor_count": "doctor_count",
        "-doctor_count": "-doctor_count",
        "created_at": "created_at",
        "-created_at": "-created_at",
    }
    queryset = queryset.order_by(ordering_map.get(ordering, "display_order"), "id")
    paginator = StaffPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(
        SpecialtyAdminListSerializer(page, many=True).data
    )


@api_view(["GET", "PATCH"])
@permission_classes([IsAdministrator])
def specialty_admin_detail(request, specialty_id):
    if request.method == "GET":
        specialty = get_object_or_404(specialty_admin_queryset(), pk=specialty_id)
        return Response(SpecialtyAdminDetailSerializer(specialty).data)

    with transaction.atomic():
        specialty = get_object_or_404(
            Specialty.objects.select_for_update(), pk=specialty_id
        )
        serializer = SpecialtyAdminWriteSerializer(
            specialty, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        expected = serializer.validated_data.get("expected_updated_at")
        if expected is None:
            return Response(
                {
                    "detail": "expected_updated_at is required.",
                    "code": "expected_updated_at_required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if specialty.updated_at != expected:
            return Response(
                {"detail": "Specialty changed since it was loaded.", "code": "conflict"},
                status=status.HTTP_409_CONFLICT,
            )
        serializer.save()
        _audit_admin_action(
            request, "specialty_updated", "specialty", specialty.id
        )
    detail = specialty_admin_queryset().get(pk=specialty.pk)
    return Response(SpecialtyAdminDetailSerializer(detail).data)


@api_view(["POST"])
@permission_classes([IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def specialty_admin_activate(request, specialty_id):
    return _set_specialty_active(request, specialty_id, True)


@api_view(["POST"])
@permission_classes([IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def specialty_admin_deactivate(request, specialty_id):
    return _set_specialty_active(request, specialty_id, False)


def _set_specialty_active(request, specialty_id, active):
    with transaction.atomic():
        specialty = get_object_or_404(
            Specialty.objects.select_for_update(), pk=specialty_id
        )
        usage = specialty_admin_queryset().get(pk=specialty_id)
        if not active and usage.active_consultation_count:
            return Response(
                {
                    "detail": "This specialty is still used by active consultations.",
                    "code": "specialty_in_use",
                    "usage": {
                        "active_doctors": usage.active_doctor_count,
                        "active_consultations": usage.active_consultation_count,
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        if specialty.is_active != active:
            specialty.is_active = active
            specialty.save(update_fields=["is_active", "updated_at"])
            _audit_admin_action(
                request,
                "specialty_activated" if active else "specialty_deactivated",
                "specialty",
                specialty.id,
                metadata={
                    "active_doctor_count": usage.active_doctor_count,
                    "active_consultation_count": usage.active_consultation_count,
                },
            )
    detail = specialty_admin_queryset().get(pk=specialty.pk)
    return Response(SpecialtyAdminDetailSerializer(detail).data)


@api_view(["POST"])
@permission_classes([IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def specialty_admin_reorder(request):
    serializer = SpecialtyReorderSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    items = sorted(
        serializer.validated_data["items"],
        key=lambda item: (item["display_order"], str(item["id"])),
    )
    with transaction.atomic():
        locked = {
            item.id: item
            for item in Specialty.objects.select_for_update().filter(
                id__in=[entry["id"] for entry in items]
            )
        }
        changed_at = timezone.now()
        for display_order, entry in enumerate(items, start=1):
            locked[entry["id"]].display_order = display_order
            locked[entry["id"]].updated_at = changed_at
        Specialty.objects.bulk_update(
            locked.values(), ["display_order", "updated_at"]
        )
        _audit_admin_action(
            request,
            "specialty_reordered",
            "specialty_collection",
            "all",
            metadata={"count": len(items)},
        )
    queryset = specialty_admin_queryset().order_by("display_order", "id")
    return Response(SpecialtyAdminListSerializer(queryset, many=True).data)


@api_view(["GET"])
@permission_classes([IsAdministrator])
def attachment_admin_list(request):
    queryset = ConsultationAttachment.objects.select_related("consultation")
    owner_type = request.query_params.get("owner_type", "").strip()
    if owner_type and owner_type != "consultation":
        queryset = queryset.none()
    status_filter = request.query_params.get("status")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    mime_type = request.query_params.get("mime_type", "").strip()
    if mime_type:
        queryset = queryset.filter(detected_mime_type__icontains=mime_type)
    scanner_result = request.query_params.get("scanner_result")
    if scanner_result:
        queryset = queryset.filter(scan_status=scanner_result)
    created_after = request.query_params.get("created_after")
    if created_after:
        queryset = queryset.filter(created_at__gte=created_after)
    created_before = request.query_params.get("created_before")
    if created_before:
        queryset = queryset.filter(created_at__lte=created_before)
    size_min = request.query_params.get("size_min")
    if size_min and size_min.isdigit():
        queryset = queryset.filter(size_bytes__gte=int(size_min))
    size_max = request.query_params.get("size_max")
    if size_max and size_max.isdigit():
        queryset = queryset.filter(size_bytes__lte=int(size_max))
    search = request.query_params.get("search", "").strip()
    if search:
        search_filter = Q(safe_display_name__icontains=search)
        try:
            search_filter |= Q(pk=uuid.UUID(search))
        except ValueError:
            pass
        queryset = queryset.filter(search_filter)

    ordering = request.query_params.get("ordering", "-created_at")
    allowed = {
        "created_at", "-created_at", "updated_at", "-updated_at",
        "size_bytes", "-size_bytes", "status", "-status",
        "scan_status", "-scan_status",
    }
    queryset = queryset.order_by(ordering if ordering in allowed else "-created_at", "id")
    paginator = StaffPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(
        AdminAttachmentListSerializer(page, many=True).data
    )


@api_view(["GET"])
@permission_classes([IsAdministrator])
def attachment_admin_detail(request, attachment_id):
    attachment = get_object_or_404(
        ConsultationAttachment.objects.select_related(
            "consultation"
        ).prefetch_related("audit_events"),
        pk=attachment_id,
    )
    _attachment_audit(
        attachment, request, AttachmentEventType.ADMIN_VIEWED, {"result": "success"}
    )
    _audit_admin_action(
        request, "attachment_admin_viewed", "attachment", attachment.id
    )
    return Response(AdminAttachmentDetailSerializer(attachment).data)


def _locked_attachment_action(request, attachment_id):
    serializer = AttachmentAdminActionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    attachment = get_object_or_404(
        ConsultationAttachment.objects.select_for_update().select_related(
            "consultation"
        ),
        pk=attachment_id,
    )
    if attachment.status != serializer.validated_data["expected_status"]:
        return None, None, Response(
            {"detail": "Attachment status changed.", "code": "status_conflict"},
            status=status.HTTP_409_CONFLICT,
        )
    return attachment, serializer.validated_data["reason"], None


@api_view(["POST"])
@permission_classes([IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def attachment_admin_rescan(request, attachment_id):
    if getattr(settings, "ATTACHMENT_SCAN_MODE", "disabled") != "clamav":
        return Response(
            {"detail": "Attachment scanner is unavailable.", "code": "scanner_unavailable"},
            status=status.HTTP_409_CONFLICT,
        )
    with transaction.atomic():
        attachment, reason, error = _locked_attachment_action(request, attachment_id)
        if error:
            return error
        if attachment.status not in (
            AttachmentStatus.PENDING,
            AttachmentStatus.QUARANTINED,
            AttachmentStatus.AVAILABLE,
        ) or attachment.scan_status == ScanStatus.PENDING:
            return Response(
                {"detail": "Attachment cannot be rescanned.", "code": "invalid_transition"},
                status=status.HTTP_409_CONFLICT,
            )
        previous_status = attachment.status
        attachment.scan_status = ScanStatus.PENDING
        attachment.save(update_fields=["scan_status", "updated_at"])
        _attachment_audit(
            attachment,
            request,
            AttachmentEventType.RESCAN_REQUESTED,
            {"previous_status": previous_status, "reason_present": True},
        )
        _audit_admin_action(
            request,
            "attachment_rescan_requested",
            "attachment",
            attachment.id,
            metadata={
                "previous_status": previous_status,
                "reason_present": bool(reason),
            },
        )
        try:
            result = ClamavAttachmentScanner().scan(
                get_storage_backend(), attachment.storage_key
            )
        except Exception:
            attachment.scan_status = ScanStatus.FAILED
            attachment.status = AttachmentStatus.QUARANTINED
            attachment.quarantine_reason = ScanStatus.FAILED
            attachment.scan_provider = "clamav"
            attachment.scan_reference = ""
            attachment.scan_completed_at = timezone.now()
            attachment.save(update_fields=[
                "scan_status", "status", "quarantine_reason", "scan_provider",
                "scan_reference", "scan_completed_at", "updated_at",
            ])
            failure_metadata = {
                "action": "rescan",
                "previous_status": previous_status,
                "new_status": attachment.status,
                "scanner_verdict": attachment.scan_status,
            }
            _attachment_audit(
                attachment,
                request,
                AttachmentEventType.ADMIN_ACTION_FAILED,
                failure_metadata,
            )
            _audit_admin_action(
                request,
                "attachment_admin_action_failed",
                "attachment",
                attachment.id,
                result=AuditEventResult.FAILED,
                metadata=failure_metadata,
            )
            return Response(
                {"detail": "Attachment scan failed.", "code": "scanner_failed"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        attachment.scan_status = result.verdict.value
        attachment.scan_provider = result.provider[:50]
        attachment.scan_reference = ""
        attachment.scan_completed_at = timezone.now()
        if result.verdict in (
            ScanVerdict.SUSPICIOUS,
            ScanVerdict.INFECTED,
            ScanVerdict.FAILED,
        ):
            attachment.status = AttachmentStatus.QUARANTINED
            attachment.quarantine_reason = result.verdict.value
        elif (
            result.verdict == ScanVerdict.CLEAN
            and previous_status != AttachmentStatus.QUARANTINED
        ):
            attachment.status = AttachmentStatus.AVAILABLE
            attachment.quarantine_reason = ""
        attachment.save(update_fields=[
            "scan_status", "scan_provider", "scan_reference",
            "scan_completed_at", "status", "quarantine_reason", "updated_at",
        ])
        _attachment_audit(
            attachment,
            request,
            AttachmentEventType.SCAN_COMPLETED,
            {
                "previous_status": previous_status,
                "new_status": attachment.status,
                "scanner_verdict": attachment.scan_status,
            },
        )
        if (
            attachment.status == AttachmentStatus.QUARANTINED
            and previous_status != AttachmentStatus.QUARANTINED
        ):
            quarantine_metadata = {
                "previous_status": previous_status,
                "new_status": attachment.status,
                "scanner_verdict": attachment.scan_status,
            }
            _attachment_audit(
                attachment,
                request,
                AttachmentEventType.QUARANTINED,
                quarantine_metadata,
            )
            _audit_admin_action(
                request,
                "attachment_quarantined",
                "attachment",
                attachment.id,
                metadata=quarantine_metadata,
            )
        _audit_admin_action(
            request,
            "attachment_scan_completed",
            "attachment",
            attachment.id,
            metadata={
                "previous_status": previous_status,
                "new_status": attachment.status,
                "scanner_verdict": attachment.scan_status,
            },
        )
    attachment = ConsultationAttachment.objects.prefetch_related(
        "audit_events"
    ).get(pk=attachment.id)
    return Response(AdminAttachmentDetailSerializer(attachment).data)


@api_view(["POST"])
@permission_classes([IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def attachment_admin_reject(request, attachment_id):
    with transaction.atomic():
        attachment, reason, error = _locked_attachment_action(request, attachment_id)
        if error:
            return error
        if attachment.status not in (
            AttachmentStatus.PENDING,
            AttachmentStatus.QUARANTINED,
        ):
            return Response(
                {"detail": "Attachment cannot be rejected.", "code": "invalid_transition"},
                status=status.HTTP_409_CONFLICT,
            )
        previous = attachment.status
        attachment.status = AttachmentStatus.REJECTED
        attachment.rejection_reason = reason
        attachment.save(update_fields=["status", "rejection_reason", "updated_at"])
        _attachment_audit(
            attachment,
            request,
            AttachmentEventType.REJECTED,
            {
                "previous_status": previous,
                "new_status": attachment.status,
                "reason_present": True,
            },
        )
        _audit_admin_action(
            request,
            "attachment_rejected",
            "attachment",
            attachment.id,
            metadata={
                "previous_status": previous,
                "new_status": attachment.status,
                "reason_present": True,
            },
        )
    return Response(AdminAttachmentDetailSerializer(attachment).data)


@api_view(["POST"])
@permission_classes([IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def attachment_admin_release(request, attachment_id):
    with transaction.atomic():
        attachment, reason, error = _locked_attachment_action(request, attachment_id)
        if error:
            return error
        if not (
            attachment.status == AttachmentStatus.QUARANTINED
            and attachment.scan_status == ScanStatus.CLEAN
            and attachment.scan_provider
            and attachment.scan_provider != "disabled"
        ):
            return Response(
                {"detail": "Verified clean scan required.", "code": "release_not_safe"},
                status=status.HTTP_409_CONFLICT,
            )
        attachment.status = AttachmentStatus.AVAILABLE
        attachment.quarantine_reason = ""
        attachment.save(update_fields=["status", "quarantine_reason", "updated_at"])
        _attachment_audit(
            attachment,
            request,
            AttachmentEventType.RELEASED,
            {
                "previous_status": AttachmentStatus.QUARANTINED,
                "new_status": AttachmentStatus.AVAILABLE,
                "scanner_verdict": ScanStatus.CLEAN,
                "reason_present": bool(reason),
            },
        )
        _audit_admin_action(
            request,
            "attachment_released",
            "attachment",
            attachment.id,
            metadata={
                "previous_status": AttachmentStatus.QUARANTINED,
                "new_status": AttachmentStatus.AVAILABLE,
                "scanner_verdict": ScanStatus.CLEAN,
                "reason_present": True,
            },
        )
    return Response(AdminAttachmentDetailSerializer(attachment).data)


@api_view(["POST"])
@permission_classes([IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def attachment_admin_retention_delete(request, attachment_id):
    with transaction.atomic():
        attachment, reason, error = _locked_attachment_action(request, attachment_id)
        if error:
            return error
        from apps.staff.phase_e_serializers import attachment_retention_eligible

        if not attachment_retention_eligible(attachment):
            return Response(
                {"detail": "Attachment is blocked by retention policy.", "code": "retention_blocked"},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            get_storage_backend().delete(attachment.storage_key)
        except Exception:
            _attachment_audit(
                attachment,
                request,
                AttachmentEventType.ADMIN_ACTION_FAILED,
                {"action": "retention_delete"},
            )
            _audit_admin_action(
                request,
                "attachment_admin_action_failed",
                "attachment",
                attachment.id,
                result=AuditEventResult.FAILED,
                metadata={"action": "retention_delete"},
            )
            return Response(
                {"detail": "Storage deletion failed.", "code": "storage_delete_failed"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        attachment.storage_deleted_at = timezone.now()
        attachment.deletion_reason = reason
        attachment.deleted_by = request.user
        attachment.save(update_fields=[
            "storage_deleted_at", "deletion_reason", "deleted_by", "updated_at",
        ])
        _attachment_audit(
            attachment,
            request,
            AttachmentEventType.RETENTION_DELETED,
            {"reason_present": True, "result": "success"},
        )
        _audit_admin_action(
            request,
            "attachment_retention_deleted",
            "attachment",
            attachment.id,
            metadata={"reason_present": True, "result": "success"},
        )
    return Response(AdminAttachmentDetailSerializer(attachment).data)


@api_view(["GET"])
@permission_classes([IsAdministrator])
def attachment_admin_download(request, attachment_id):
    attachment = get_object_or_404(ConsultationAttachment, pk=attachment_id)
    if not attachment.is_available:
        return Response(
            {"detail": "Attachment is not available.", "code": "attachment_not_available"},
            status=status.HTTP_409_CONFLICT,
        )
    try:
        stream = get_storage_backend().open(attachment.storage_key)
    except Exception:
        stream = None
    if stream is None:
        return Response(
            {"detail": "Attachment file is unavailable.", "code": "storage_unavailable"},
            status=status.HTTP_404_NOT_FOUND,
        )
    _attachment_audit(
        attachment, request, AttachmentEventType.DOWNLOADED, {"admin": True}
    )
    _audit_admin_action(
        request, "attachment_admin_downloaded", "attachment", attachment.id
    )
    response = FileResponse(
        stream,
        as_attachment=True,
        filename=attachment.safe_display_name or f"attachment-{attachment.id}",
        content_type="application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response
