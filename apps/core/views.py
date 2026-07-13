"""
Health, readiness, diagnostics, and metrics endpoints.

- GET /api/health/           — process alive only, no DB
- GET /api/readiness/        — DB + attachment backend check
- GET /api/staff/operations/status/   — admin diagnostics
- GET /api/staff/operations/metrics/  — aggregated counts
"""

import time

from django.conf import settings
from django.db import connection, ProgrammingError
from django.db.utils import OperationalError
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.authentication import CookieJWTAuthentication
from apps.accounts.permissions import IsAdministrator

_start_time = time.time()


# ── Health ──

@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def health(request):
    """Return 200 OK. No database query."""
    return Response({"status": "healthy"})


# ── Readiness ──

@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def readiness(request):
    """Check database + attachment backend."""
    db_ok = _check_database()
    storage_ok = _check_attachment_storage()
    if not db_ok:
        return Response({"status": "unhealthy", "database": False}, status=503)
    return Response({
        "status": "ready",
        "database": db_ok,
        "attachment_storage": storage_ok,
    })


# ── Operations: Status ──

@api_view(["GET"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated, IsAdministrator])
def operations_status(request):
    """Safe operational state. Admin only."""
    db_ok = _check_database()
    storage_ok = _check_attachment_storage()
    return Response({
        "version": getattr(settings, "APP_VERSION", "0.0.0"),
        "release": getattr(settings, "APP_RELEASE", ""),
        "commit": (getattr(settings, "GIT_COMMIT_SHA", "")[:8]
                   if getattr(settings, "GIT_COMMIT_SHA", "") else ""),
        "environment": "production" if not settings.DEBUG else "development",
        "database_available": db_ok,
        "attachment_backend_provider": getattr(settings, "ATTACHMENT_STORAGE_BACKEND", "local"),
        "attachment_root_writable": storage_ok,
        "attachment_scan_mode": getattr(settings, "ATTACHMENT_SCAN_MODE", "disabled"),
        "ai_enabled": getattr(settings, "AI_INTAKE_ENABLED", False),
        "error_monitor_provider": getattr(settings, "ERROR_MONITOR_PROVIDER", "disabled"),
        "latest_migration": _get_latest_migration() if db_ok else "",
        "retention_candidates": _get_retention_candidates() if db_ok else -1,
        "degraded_components": _degraded(db_ok, storage_ok),
    })


# ── Operations: Metrics ──

@api_view(["GET"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated, IsAdministrator])
def operations_metrics(request):
    """Aggregated operational metrics. Admin only."""
    uptime = int(time.time() - _start_time)
    try:
        from apps.accounts.models import User, UserRole
        from apps.consultations.models import Consultation, ConsultationStatus
        from apps.attachments.models import ConsultationAttachment
        from apps.attachments.choices import AttachmentStatus
        from apps.notifications.models import Notification

        users_by_role = {}
        for r, _ in UserRole.choices:
            users_by_role[r] = User.objects.filter(role=r).count()

        consultations_by_status = {}
        for s, _ in ConsultationStatus.choices:
            consultations_by_status[s] = Consultation.objects.filter(status=s).count()

        attachments_by_status = {}
        for s, _ in AttachmentStatus.choices:
            attachments_by_status[s] = ConsultationAttachment.objects.filter(status=s).count()

        total_bytes = sum(
            ConsultationAttachment.objects.exclude(size__isnull=True)
            .values_list("size", flat=True)
        )
        total_users = User.objects.count()
        pending_notifications = Notification.objects.count()
        retention_count = _get_retention_candidates()
    except Exception:
        import traceback; traceback.print_exc()
        return Response({"error": "metrics_unavailable"}, status=503)

    return Response({
        "uptime_seconds": uptime,
        "users": {"total": total_users, **users_by_role},
        "consultations": consultations_by_status,
        "attachments": {"by_status": attachments_by_status, "total_bytes": total_bytes},
        "notifications_pending": pending_notifications,
        "retention_candidates": retention_count,
    })


# ── Helpers ──

def _check_database() -> bool:
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
            return True
    except (OperationalError, ProgrammingError):
        return False


def _check_attachment_storage() -> bool:
    try:
        from apps.attachments.services.factory import clear_backend_cache, get_storage_backend
        clear_backend_cache()
        return get_storage_backend()._root.exists()
    except Exception:
        return False


def _get_retention_candidates() -> int:
    from datetime import timedelta
    from django.utils import timezone
    from apps.attachments.models import ConsultationAttachment
    days = getattr(settings, "ATTACHMENT_RETENTION_DAYS", 90)
    if days <= 0:
        return 0
    cutoff = timezone.now() - timedelta(days=days)
    return ConsultationAttachment.objects.filter(
        deleted_at__isnull=False, deleted_at__lt=cutoff
    ).count()


def _get_latest_migration() -> str:
    try:
        from django.db.migrations.recorder import MigrationRecorder
        latest = MigrationRecorder.Migration.objects.order_by("-applied").first()
        return str(latest.name) if latest else ""
    except Exception:
        return ""


def _degraded(db_ok: bool, storage_ok: bool) -> list:
    d = []
    if not db_ok:
        d.append("database")
    if not storage_ok:
        d.append("attachment_storage")
    return d
