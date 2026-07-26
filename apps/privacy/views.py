"""
Privacy views.

Export endpoints:
  POST   /api/privacy/exports/
  GET    /api/privacy/exports/
  GET    /api/privacy/exports/<uuid:id>/
  GET    /api/privacy/exports/<uuid:id>/download/
  DELETE /api/privacy/exports/<uuid:id>/

Account endpoints:
  POST   /api/privacy/account/deactivate/
  POST   /api/privacy/account/reactivate/

Deletion endpoints:
  POST   /api/privacy/deletion-requests/
  GET    /api/privacy/deletion-requests/
  GET    /api/privacy/deletion-requests/<uuid:id>/
  POST   /api/privacy/deletion-requests/<uuid:id>/cancel/

Staff deletion endpoints:
  POST   /api/staff/privacy/deletion-requests/<uuid:id>/approve/
  POST   /api/staff/privacy/deletion-requests/<uuid:id>/reject/
"""

import os
import json
import zipfile
import io
import hashlib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, authenticate
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.authentication import CookieJWTAuthentication
from apps.accounts.permissions import IsPatient, IsAdministrator
from apps.accounts.throttles import AdminSensitiveWriteThrottle
from apps.core.security_events import (
    data_export_requested, data_export_completed,
    account_deactivated,
)
from apps.privacy.models import (
    DataExportRequest, AccountDeletionRequest,
    ExportStatus, DeletionStatus,
)
from apps.privacy.serializers import (
    DataExportRequestSerializer, DataExportCreateSerializer,
    AccountDeletionRequestSerializer, AccountDeletionReviewSerializer,
    DeactivationSerializer,
)

User = get_user_model()


# ── Data Export ─────────────────────────────────────────────────────────


@api_view(["POST", "GET"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def export_list_create(request):
    if request.method == "POST":
        serializer = DataExportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        export = DataExportRequest.objects.create(
            requested_by=request.user,
            subject_user=request.user,
            status=ExportStatus.PENDING,
        )
        data_export_requested(str(request.user.id))
        out = DataExportRequestSerializer(export).data
        return Response(out, status=status.HTTP_201_CREATED)

    # GET — list own exports
    qs = DataExportRequest.objects.filter(subject_user=request.user)
    # Staff can list exports for their own user only unless admin
    if request.user.role == "administrator":
        subject = request.query_params.get("subject_user")
        if subject:
            qs = DataExportRequest.objects.filter(subject_user_id=subject)
    serializer = DataExportRequestSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(["GET", "DELETE"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def export_detail(request, id):
    try:
        export = DataExportRequest.objects.get(id=id)
    except DataExportRequest.DoesNotExist:
        return Response({"detail": "Not found.", "code": "not_found"}, status=404)

    # Only owner or admin
    if export.subject_user != request.user and request.user.role != "administrator":
        return Response({"detail": "Permission denied.", "code": "permission_denied"}, status=403)

    if request.method == "DELETE":
        if export.status in (ExportStatus.EXPIRED, ExportStatus.COMPLETED):
            export.status = ExportStatus.DELETED
            export.save(update_fields=["status"])
            return Response(status=204)
        return Response({"detail": "Cannot delete active export.", "code": "conflict"}, status=409)

    serializer = DataExportRequestSerializer(export)
    return Response(serializer.data)


@api_view(["GET"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def export_download(request, id):
    try:
        export = DataExportRequest.objects.get(id=id)
    except DataExportRequest.DoesNotExist:
        return Response({"detail": "Not found.", "code": "not_found"}, status=404)

    if export.subject_user != request.user and request.user.role != "administrator":
        return Response({"detail": "Permission denied.", "code": "permission_denied"}, status=403)

    if export.status == ExportStatus.EXPIRED:
        return Response({"detail": "Export expired.", "code": "expired"}, status=410)
    if export.status == ExportStatus.DELETED:
        return Response({"detail": "Export deleted.", "code": "deleted"}, status=410)
    if export.status != ExportStatus.COMPLETED:
        return Response({"detail": "Export not ready.", "code": "not_ready"}, status=409)

    if not export.storage_key or not export.storage_provider:
        return Response({"detail": "Export file unavailable.", "code": "storage_error"}, status=503)

    from apps.attachments.services.factory import get_storage_backend
    backend = get_storage_backend()
    try:
        f = backend.open(export.storage_key)
        if f is None:
            raise FileNotFoundError
        content = f.read()
        f.close()
    except Exception:
        return Response({"detail": "Export file unavailable.", "code": "storage_error"}, status=503)

    response = Response(content, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="export-{export.id}.zip"'
    return response


# ── Account Deactivation ────────────────────────────────────────────────


@api_view(["POST"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def deactivate_account(request):
    serializer = DeactivationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = authenticate(
        email=request.user.email,
        password=serializer.validated_data["password"],
    )
    if user is None:
        return Response({"detail": "Invalid password.", "code": "authentication_failed"}, status=403)

    user.is_active = False
    user.save(update_fields=["is_active"])
    account_deactivated(str(user.id))
    return Response({"detail": "Account deactivated."})


@api_view(["POST"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated, IsAdministrator])
def reactivate_account(request):
    user_id = request.data.get("user_id", "")
    if not user_id:
        return Response({"detail": "user_id required.", "code": "validation_error"}, status=400)
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"detail": "Not found.", "code": "not_found"}, status=404)
    user.is_active = True
    user.save(update_fields=["is_active"])
    return Response({"detail": "Account reactivated."})


# ── Deletion Requests ──────────────────────────────────────────────────


@api_view(["POST", "GET"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def deletion_list_create(request):
    if request.method == "POST":
        reason = request.data.get("reason", "")
        existing = AccountDeletionRequest.objects.filter(
            subject_user=request.user,
            status__in=(DeletionStatus.PENDING, DeletionStatus.APPROVED, DeletionStatus.SCHEDULED),
        ).first()
        if existing:
            return Response(
                {"detail": "Active deletion request exists.", "code": "conflict"},
                status=409,
            )
        dr = AccountDeletionRequest.objects.create(
            subject_user=request.user,
            requested_by=request.user,
            reason=reason,
        )
        return Response(AccountDeletionRequestSerializer(dr).data, status=201)

    # GET list
    if request.user.role == "administrator":
        qs = AccountDeletionRequest.objects.all()
    else:
        qs = AccountDeletionRequest.objects.filter(subject_user=request.user)
    return Response(AccountDeletionRequestSerializer(qs, many=True).data)


@api_view(["GET", "POST"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated])
def deletion_detail_cancel(request, id):
    try:
        dr = AccountDeletionRequest.objects.get(id=id)
    except AccountDeletionRequest.DoesNotExist:
        return Response({"detail": "Not found.", "code": "not_found"}, status=404)

    if request.method == "GET":
        if dr.subject_user != request.user and request.user.role != "administrator":
            return Response({"detail": "Permission denied.", "code": "permission_denied"}, status=403)
        return Response(AccountDeletionRequestSerializer(dr).data)

    # POST — cancel
    if dr.subject_user != request.user:
        return Response({"detail": "Permission denied.", "code": "permission_denied"}, status=403)
    if dr.status not in (DeletionStatus.PENDING,):
        return Response({"detail": "Cannot cancel in current state.", "code": "conflict"}, status=409)
    dr.status = DeletionStatus.CANCELLED
    dr.save(update_fields=["status"])
    return Response(AccountDeletionRequestSerializer(dr).data)


# ── Staff: Deletion Review ──────────────────────────────────────────────


@api_view(["POST"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated, IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def deletion_approve(request, id):
    from apps.core.audit_service import create_audit_event
    from apps.core.models import AuditEventCategory, AuditEventSeverity, AuditEventResult, RetentionClass

    try:
        dr = AccountDeletionRequest.objects.get(id=id)
    except AccountDeletionRequest.DoesNotExist:
        return Response({"detail": "Not found.", "code": "not_found"}, status=404)

    serializer = AccountDeletionReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        locked = AccountDeletionRequest.objects.select_for_update().get(pk=dr.id)

        if locked.status != DeletionStatus.PENDING:
            return Response(
                {"detail": "This privacy request can no longer be reviewed.",
                 "code": "invalid_privacy_request_transition"},
                status=status.HTTP_409_CONFLICT,
            )

        expected_status = serializer.validated_data.get("expected_status")
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

        # Audit event
        create_audit_event(
            event_type="privacy.deletion.approved",
            category=AuditEventCategory.PRIVACY,
            severity=AuditEventSeverity.INFO,
            result=AuditEventResult.SUCCESS,
            actor_id=str(request.user.id),
            actor_role=request.user.role,
            target_type="AccountDeletionRequest",
            target_id=str(locked.id),
            summary=f"Deletion request {locked.id} approved for user {locked.subject_user_id}",
            retention_class=RetentionClass.PRIVACY_DECISION,
        )

    # Notify requester
    from apps.notifications.services import create_notification
    from apps.notifications.models import NotificationType
    try:
        create_notification(
            recipient=dr.subject_user,
            notification_type=NotificationType.PRIVACY_DELETION_APPROVED,
            title="Deletion Request Approved",
            body="Your account deletion request has been approved.",
        )
    except Exception:
        pass

    return Response(AccountDeletionRequestSerializer(locked).data)


@api_view(["POST"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated, IsAdministrator])
@throttle_classes([AdminSensitiveWriteThrottle])
def deletion_reject(request, id):
    from apps.core.audit_service import create_audit_event
    from apps.core.models import AuditEventCategory, AuditEventSeverity, AuditEventResult, RetentionClass

    try:
        dr = AccountDeletionRequest.objects.get(id=id)
    except AccountDeletionRequest.DoesNotExist:
        return Response({"detail": "Not found.", "code": "not_found"}, status=404)

    serializer = AccountDeletionReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    reject_reason = serializer.validated_data.get("rejection_reason", "")
    expected_status = serializer.validated_data.get("expected_status")

    with transaction.atomic():
        locked = AccountDeletionRequest.objects.select_for_update().get(pk=dr.id)

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
        locked.rejection_reason = reject_reason
        locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "rejection_reason"])

        # Audit event
        create_audit_event(
            event_type="privacy.deletion.rejected",
            category=AuditEventCategory.PRIVACY,
            severity=AuditEventSeverity.INFO,
            result=AuditEventResult.DENIED,
            actor_id=str(request.user.id),
            actor_role=request.user.role,
            target_type="AccountDeletionRequest",
            target_id=str(locked.id),
            summary=f"Deletion request {locked.id} rejected for user {locked.subject_user_id}",
            metadata={"reason_present": bool(reject_reason)},
            retention_class=RetentionClass.PRIVACY_DECISION,
        )

    # Notify requester
    from apps.notifications.services import create_notification
    from apps.notifications.models import NotificationType
    try:
        create_notification(
            recipient=dr.subject_user,
            notification_type=NotificationType.PRIVACY_DELETION_REJECTED,
            title="Deletion Request Rejected",
            body="Your account deletion request has been reviewed.",
        )
    except Exception:
        pass

    return Response(AccountDeletionRequestSerializer(locked).data)
