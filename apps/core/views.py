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
    """Check dependencies required to safely serve requests."""
    db_ok = _check_database()
    storage_ok = _check_attachment_storage()
    scanner_mode = getattr(settings, "ATTACHMENT_SCAN_MODE", "disabled")
    scanner_ok = _check_scanner()
    scanner_required = scanner_mode == "clamav"
    ready = db_ok and storage_ok and (scanner_ok or not scanner_required)
    payload = {
        "status": "ready" if ready else "unavailable",
        "database": db_ok,
        "attachment_storage": storage_ok,
        "scanner_available": scanner_ok,
        "scanner_required": scanner_required,
    }
    return Response(payload, status=200 if ready else 503)


# ── Operations: Status ──

@api_view(["GET"])
@authentication_classes([CookieJWTAuthentication])
@permission_classes([IsAuthenticated, IsAdministrator])
def operations_status(request):
    """Safe operational state. Admin only."""
    db_ok = _check_database()
    storage_ok = _check_attachment_storage()
    scanner = _scanner_status()
    degraded = _degraded(db_ok, storage_ok, scanner)
    notification_count = _get_notification_count() if db_ok else -1
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
        "scanner": scanner,
        "ai_enabled": getattr(settings, "AI_INTAKE_ENABLED", False),
        "error_monitor_provider": getattr(settings, "ERROR_MONITOR_PROVIDER", "disabled"),
        "latest_migration": _get_latest_migration() if db_ok else "",
        "retention_candidates": _get_retention_candidates() if db_ok else -1,
        "notifications_total_in_app": notification_count,
        "health_status": "healthy",
        "readiness_status": "ready" if not degraded else "degraded",
        "background_tasks": {
            "configured": False,
            "status": "not_configured",
        },
        "backup": _backup_status(),
        "degraded_components": degraded,
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
            ConsultationAttachment.objects.exclude(size_bytes__isnull=True)
            .values_list("size_bytes", flat=True)
        )
        total_users = User.objects.count()
        total_in_app_notifications = Notification.objects.count()
        retention_count = _get_retention_candidates()
    except Exception:
        return Response({"error": "metrics_unavailable"}, status=503)

    return Response({
        "uptime_seconds": uptime,
        "users": {"total": total_users, **users_by_role},
        "consultations": consultations_by_status,
        "attachments": {"by_status": attachments_by_status, "total_bytes": total_bytes},
        "notifications_total_in_app": total_in_app_notifications,
        "retention_candidates": retention_count,
        "backup": _backup_status(),
        "scanner": _scanner_status(),
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
        backend = get_storage_backend()
        backend_path = getattr(backend, "_root", None)
        if backend_path is not None:
            return backend_path.exists()
        check = getattr(backend, "check_access", None)
        if check is not None:
            return check()
        return True
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


def _check_scanner() -> bool:
    """Check if the configured scanner is reachable."""
    try:
        from apps.attachments.services.scanning.factory import get_scanner, clear_scanner_cache
        clear_scanner_cache()
        scanner = get_scanner()
        return scanner.is_available()
    except Exception:
        return False


def _backup_status() -> dict:
    """Return backup-relevant operational state.  No secrets."""
    from apps.attachments.services.factory import get_storage_backend, clear_backend_cache
    storage_ok = False
    try:
        clear_backend_cache()
        backend = get_storage_backend()
        backend_path = getattr(backend, "_root", None)
        if backend_path is not None:
            storage_ok = backend_path.exists()
        else:
            check = getattr(backend, "check_access", None)
            if check is not None:
                storage_ok = check()
    except Exception:
        pass

    MAX_AGE = getattr(settings, "BACKUP_MAX_AGE_HOURS", 30)
    return {
        "storage_available": storage_ok,
        "max_age_hours": MAX_AGE,
        "degraded": False,  # Set externally via cron result
    }


def _scanner_status() -> dict:
    """Return scanner-relevant operational state.  No secrets."""
    mode = getattr(settings, "ATTACHMENT_SCAN_MODE", "disabled")
    available = _check_scanner()
    return {
        "mode": mode,
        "available": available,
        # No persistent scanner-check record exists. Do not invent one.
        "last_successful_check": None,
        "required": mode == "clamav",
    }


def _degraded(db_ok: bool, storage_ok: bool, scanner: dict | None = None) -> list:
    degraded = []
    if not db_ok:
        degraded.append("database")
    if not storage_ok:
        degraded.append("attachment_storage")
    scanner = scanner or _scanner_status()
    if scanner["required"] and not scanner["available"]:
        degraded.append("scanner")
    return degraded


def _get_notification_count() -> int:
    try:
        from apps.notifications.models import Notification
        return Notification.objects.count()
    except Exception:
        return -1


def _get_latest_migration() -> str:
    try:
        from django.db.migrations.recorder import MigrationRecorder
        latest = MigrationRecorder.Migration.objects.order_by("-applied").first()
        return str(latest.name) if latest else ""
    except Exception:
        return ""
