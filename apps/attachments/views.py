"""Attachment views — upload, list, detail, download, delete, restore."""

import hashlib
import logging
import os
import uuid

from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import UserRole
from apps.attachments.choices import AttachmentCategory, AttachmentEventType, AttachmentStatus, ScanStatus
from apps.attachments.models import AttachmentAuditEvent, ConsultationAttachment
from apps.attachments.permissions import IsDoctor, IsPatient, IsStaff
from apps.attachments.serializers import AttachmentListSerializer, AttachmentUploadSerializer
from apps.attachments.services.factory import get_storage_backend
from apps.attachments.services.scanning import (
    ClamavAttachmentScanner,
    DisabledAttachmentScanner,
    ScanVerdict,
)
from apps.attachments.validators import ALLOWED_EXTENSIONS, AttachmentFileValidator
from apps.core.security_events import (
    attachment_deleted,
    attachment_downloaded,
    attachment_uploaded,
)

logger = logging.getLogger(__name__)

PATIENT_CATEGORIES = {
    AttachmentCategory.MEDICAL_REPORT,
    AttachmentCategory.LABORATORY_RESULT,
    AttachmentCategory.MEDICAL_IMAGE,
    AttachmentCategory.REFERRAL,
    AttachmentCategory.CONSENT_DOCUMENT,
    AttachmentCategory.OTHER,
}

STAFF_ONLY_CATEGORIES = {AttachmentCategory.IDENTITY_DOCUMENT}


def _get_consultation(pk):
    from apps.consultations.models import Consultation
    return get_object_or_404(Consultation, pk=pk)


def _is_participant(user, consultation) -> bool:
    if user.role in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        return True
    if user.role == UserRole.PATIENT:
        try:
            return consultation.patient.user == user
        except AttributeError:
            return False
    if user.role == UserRole.DOCTOR:
        try:
            return consultation.doctor.user == user
        except AttributeError:
            return False
    return False


def _generate_storage_key(consultation_id: uuid.UUID) -> str:
    """Server-generated opaque key. Never derived from original filename."""
    object_id = uuid.uuid4().hex
    return f"{consultation_id.hex}/{object_id}"


def _audit(attachment, actor, event_type, metadata=None, ip_hash=""):
    AttachmentAuditEvent.objects.create(
        attachment=attachment,
        actor=actor,
        event_type=event_type,
        safe_metadata=metadata or {},
        request_ip_hash=ip_hash,
    )


def _safe_display_name(original: str, ext: str) -> str:
    """Strip extension from original and rebuild safely."""
    base = os.path.splitext(os.path.basename(original))[0]
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in base)
    return f"{safe}{ext}"


# ── Upload ──────────────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_attachment(request, consultation_id):
    """Upload a file to a consultation. Multipart/form-data."""
    consultation = _get_consultation(consultation_id)
    user = request.user

    if not _is_participant(user, consultation):
        return Response(
            {"detail": "Not a participant of this consultation.",
             "code": "attachment_permission_denied"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Patient: server-authoritative lifecycle policy controls upload.
    if user.role == UserRole.PATIENT:
        from apps.consultations.patient_actions import patient_action_policy
        if not patient_action_policy(consultation).actions["can_upload_attachment"]:
            return Response(
                {"detail": "Cannot upload to a cancelled consultation.",
                 "code": "attachment_permission_denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

    serializer = AttachmentUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    uploaded_file = serializer.validated_data["file"]
    category = serializer.validated_data["category"]
    description = serializer.validated_data.get("description", "")

    # Identity documents: staff only
    if category == AttachmentCategory.IDENTITY_DOCUMENT and user.role not in (
        UserRole.COORDINATOR, UserRole.ADMINISTRATOR
    ):
        return Response(
            {"detail": "Only staff can upload identity documents.",
             "code": "attachment_permission_denied"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Patient category restrictions
    if user.role == UserRole.PATIENT and category not in PATIENT_CATEGORIES:
        return Response(
            {"detail": "Category not allowed for patient upload.",
             "code": "attachment_permission_denied"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Validate file
    validator = AttachmentFileValidator()
    is_valid, error_code, sha256 = validator(uploaded_file)
    if not is_valid:
        return Response(
            {"detail": "File validation failed.", "code": error_code},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Duplicate check within consultation (same sha256)
    existing = ConsultationAttachment.objects.filter(
        consultation=consultation,
        sha256=sha256,
        is_deleted=False,
    ).first()
    if existing:
        # Return conflict — client may reference existing safely
        return Response(
            {"detail": "Duplicate attachment.", "code": "duplicate_attachment",
             "existing_id": str(existing.id)},
            status=status.HTTP_409_CONFLICT,
        )

    # Generate storage key
    ext = validator._safe_extension(uploaded_file.name)
    storage_key = _generate_storage_key(consultation_id)
    safe_name = _safe_display_name(uploaded_file.name, ext)

    from apps.attachments.validators import ALLOWED_MIME_TYPES

    attachment = ConsultationAttachment.objects.create(
        consultation=consultation,
        uploaded_by=user,
        storage_provider=settings.ATTACHMENT_STORAGE_BACKEND,
        storage_key=storage_key,
        original_filename=uploaded_file.name,
        safe_display_name=safe_name,
        extension=ext,
        declared_mime_type=uploaded_file.content_type or "",
        detected_mime_type=uploaded_file.content_type or "",
        size_bytes=uploaded_file.size or 0,
        sha256=sha256,
        category=category,
        description=description,
        status=AttachmentStatus.AVAILABLE,
    )

    # Persist to storage
    backend = get_storage_backend()
    try:
        backend.save(uploaded_file, storage_key)
    except Exception as exc:
        logger.error("Storage save failed for attachment %s", attachment.id)
        attachment.status = AttachmentStatus.REJECTED
        attachment.save(update_fields=["status"])
        _audit(attachment, user, AttachmentEventType.STORAGE_ERROR,
               {"error": "storage_write_failed"})
        return Response(
            {"detail": "Storage error.", "code": "attachment_storage_error"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Scan
    scan_mode = getattr(settings, "ATTACHMENT_SCAN_MODE", "disabled")
    if scan_mode == "clamav":
        scanner = ClamavAttachmentScanner()
    else:
        scanner = DisabledAttachmentScanner()

    try:
        scan_result = scanner.scan(backend, storage_key)
        attachment.scan_status = scan_result.verdict.value
        attachment.scan_provider = scan_result.provider
        if scan_result.reference:
            attachment.scan_reference = scan_result.reference
        attachment.scan_completed_at = timezone.now()

        # Fail-closed on scan failure in clamav mode
        if scan_mode == "clamav" and scan_result.verdict == ScanVerdict.FAILED:
            attachment.status = AttachmentStatus.QUARANTINED
        elif scan_result.verdict == ScanVerdict.INFECTED:
            attachment.status = AttachmentStatus.QUARANTINED
            attachment.is_deleted = True
            attachment.deleted_at = timezone.now()
            # Delete from storage
            try:
                backend.delete(storage_key)
            except Exception:
                pass
    except Exception as exc:
        logger.error("Scan failed for attachment %s", attachment.id)
        attachment.scan_status = ScanStatus.FAILED
        if scan_mode == "clamav":
            attachment.status = AttachmentStatus.QUARANTINED
    attachment.save(update_fields=[
        "scan_status", "scan_provider", "scan_reference", "scan_completed_at", "status",
        "is_deleted", "deleted_at",
    ])

    _audit(attachment, user, AttachmentEventType.UPLOADED, {
        "size": attachment.size_bytes,
        "category": category,
        "status": attachment.status,
    })
    attachment_uploaded(
        str(attachment.id),
        str(attachment.consultation_id),
        str(request.user.id),
        attachment.category,
    )

    data = AttachmentListSerializer(attachment, context={"request": request}).data
    return Response(data, status=status.HTTP_201_CREATED)


# ── List ────────────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_attachments(request, consultation_id):
    """List safe metadata for all non-deleted attachments in a consultation."""
    consultation = _get_consultation(consultation_id)
    if not _is_participant(request.user, consultation):
        return Response(
            {"detail": "Not a participant.", "code": "attachment_permission_denied"},
            status=status.HTTP_403_FORBIDDEN,
        )

    qs = ConsultationAttachment.objects.filter(
        consultation=consultation,
        is_deleted=False,
    ).order_by("-created_at")

    page = request.GET.get("page", 1)
    page_size = min(int(request.GET.get("page_size", 20)), 100)
    start = (int(page) - 1) * page_size
    end = start + page_size
    total = qs.count()
    results = qs[start:end]

    return Response({
        "count": total,
        "next": None,
        "previous": None,
        "results": AttachmentListSerializer(results, many=True, context={"request": request}).data,
    })


# ── Detail ──────────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attachment_detail(request, attachment_id):
    """Return safe metadata for a single attachment."""
    attachment = get_object_or_404(ConsultationAttachment, pk=attachment_id)
    if not _is_participant(request.user, attachment.consultation):
        return Response(
            {"detail": "Not a participant.", "code": "attachment_permission_denied"},
            status=status.HTTP_403_FORBIDDEN,
        )
    data = AttachmentListSerializer(attachment, context={"request": request}).data
    _audit(attachment, request.user, AttachmentEventType.VIEWED)
    return Response(data)


# ── Download ────────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_attachment(request, attachment_id):
    """Stream the file through an authorized endpoint.

    Never redirects to a public URL. Records download audit event.
    """
    attachment = get_object_or_404(ConsultationAttachment, pk=attachment_id)
    if not _is_participant(request.user, attachment.consultation):
        return Response(
            {"detail": "Not a participant.", "code": "attachment_permission_denied"},
            status=status.HTTP_403_FORBIDDEN,
        )

    if not attachment.is_available:
        if attachment.status == AttachmentStatus.QUARANTINED:
            code = "attachment_quarantined"
        elif attachment.status in (AttachmentStatus.REJECTED, AttachmentStatus.DELETED):
            code = "attachment_not_available"
        else:
            code = "attachment_not_available"
        return Response(
            {"detail": "Attachment is not available.", "code": code},
            status=status.HTTP_410_GONE,
        )

    # Enforce scan status
    scan_mode = getattr(settings, "ATTACHMENT_SCAN_MODE", "disabled")
    if scan_mode == "clamav":
        if attachment.scan_status != ScanStatus.CLEAN:
            logger.warning(
                "Blocked download of attachment %s with scan_status=%s",
                attachment.id, attachment.scan_status,
            )
            code_map = {
                ScanStatus.PENDING: "attachment_scan_pending",
                ScanStatus.INFECTED: "attachment_quarantined",
                ScanStatus.FAILED: "attachment_scan_failed",
                ScanStatus.SUSPICIOUS: "attachment_quarantined",
            }
            return Response(
                {"detail": "Attachment is not available for download.",
                 "code": code_map.get(attachment.scan_status, "attachment_not_available")},
                status=status.HTTP_423_LOCKED,
            )

    backend = get_storage_backend()
    file_obj = backend.open(attachment.storage_key)
    if file_obj is None:
        logger.error("Storage object missing for attachment %s", attachment.id)
        return Response(
            {"detail": "Storage object not found.", "code": "attachment_storage_error"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    safe_name = attachment.safe_display_name or attachment.original_filename
    response = FileResponse(
        file_obj,
        content_type=attachment.detected_mime_type or "application/octet-stream",
        as_attachment=True,
        filename=safe_name,
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"

    _audit(attachment, request.user, AttachmentEventType.DOWNLOADED, {
        "size": attachment.size_bytes,
    })
    attachment_downloaded(
        str(attachment.id),
        str(attachment.consultation_id),
        str(request.user.id),
    )

    return response


# ── Delete (soft) ──────────────────────────────────────────────────────────


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_attachment(request, attachment_id):
    """Soft-delete an attachment. Staff may require a reason."""
    attachment = get_object_or_404(ConsultationAttachment, pk=attachment_id)
    user = request.user

    if not _is_participant(user, attachment.consultation):
        return Response(
            {"detail": "Not a participant.", "code": "attachment_permission_denied"},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Patient: may delete own before doctor review
    if user.role == UserRole.PATIENT:
        if attachment.uploaded_by != user:
            return Response(
                {"detail": "Can only delete own uploads.", "code": "attachment_permission_denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        from apps.consultations.models import ConsultationStatus as CS
        if attachment.consultation.status not in (CS.SUBMITTED, CS.DRAFT):
            return Response(
                {"detail": "Cannot delete after consultation is in progress.",
                 "code": "attachment_retention_locked"},
                status=status.HTTP_409_CONFLICT,
            )

    # Staff: reason required
    if user.role in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        reason = request.data.get("reason", "")
        if not reason:
            return Response(
                {"detail": "Deletion reason required for staff.",
                 "code": "deletion_reason_required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        attachment.deletion_reason = reason
        attachment.deleted_by = user

    # Doctor: may delete own upload before confirmed record
    if user.role == UserRole.DOCTOR:
        if attachment.uploaded_by != user:
            return Response(
                {"detail": "Can only delete own uploads.", "code": "attachment_permission_denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

    # Soft delete
    attachment.is_deleted = True
    attachment.status = AttachmentStatus.DELETED
    attachment.deleted_at = timezone.now()
    if not attachment.deleted_by:
        attachment.deleted_by = user
    attachment.save(update_fields=[
        "is_deleted", "status", "deleted_at", "deleted_by", "deletion_reason",
    ])

    _audit(attachment, user, AttachmentEventType.DELETED, {
        "reason": attachment.deletion_reason or "user_request",
    })
    attachment_deleted(
        str(attachment.id),
        str(attachment.consultation_id),
        str(request.user.id),
    )

    # Delete physical object for local development
    if settings.ATTACHMENT_STORAGE_BACKEND == "local":
        backend = get_storage_backend()
        try:
            backend.delete(attachment.storage_key)
        except Exception as exc:
            logger.warning("Physical delete failed for %s: %s", attachment.id, exc)

    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Restore (staff only) ────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStaff])
def restore_attachment(request, attachment_id):
    """Restore a soft-deleted attachment if storage object exists."""
    attachment = get_object_or_404(ConsultationAttachment, pk=attachment_id)
    if not attachment.is_deleted:
        return Response(
            {"detail": "Attachment is not deleted.", "code": "attachment_not_deleted"},
            status=status.HTTP_409_CONFLICT,
        )

    backend = get_storage_backend()
    if not backend.exists(attachment.storage_key):
        return Response(
            {"detail": "Storage object no longer exists. Cannot restore.",
             "code": "attachment_storage_error"},
            status=status.HTTP_410_GONE,
        )

    attachment.is_deleted = False
    attachment.status = AttachmentStatus.AVAILABLE
    attachment.deleted_at = None
    attachment.deleted_by = None
    attachment.deletion_reason = ""
    attachment.save(update_fields=[
        "is_deleted", "status", "deleted_at", "deleted_by", "deletion_reason",
    ])

    _audit(attachment, request.user, AttachmentEventType.RESTORED)
    data = AttachmentListSerializer(attachment, context={"request": request}).data
    return Response(data)
