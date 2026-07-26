"""
Audit event service — writes to AuditEvent DB table and stdout.

Privacy-safe: no medical content, passwords, tokens, or raw request bodies.
"""

import json

from apps.core.logging import SafeLogger
from apps.core.models import AuditEvent, AuditEventCategory, AuditEventSeverity, AuditEventResult, RetentionClass

_logger = SafeLogger("mcc.audit")


def _sanitize_metadata(metadata: dict | None) -> dict | None:
    """Remove sensitive keys from metadata."""
    if not metadata:
        return None
    sensitive_keys = {
        "password", "token", "secret", "cookie", "authorization", "csrf",
        "storage_key", "signed_url", "medical_record", "message_body",
        "attachment_content", "raw_request", "private_key", "api_key",
        "refresh_token", "access_token", "session_key",
    }
    safe = {}
    for k, v in metadata.items():
        k_lower = k.lower().replace("-", "_").replace(" ", "_")
        if any(s in k_lower for s in sensitive_keys):
            safe[k] = "[REDACTED]"
        elif isinstance(v, dict):
            safe[k] = _sanitize_metadata(v)
        elif isinstance(v, (list, tuple)):
            if len(json.dumps(v)) > 1000:
                safe[k] = f"[{len(v)} items, truncated]"
            else:
                safe[k] = v
        else:
            # Limit string values
            if isinstance(v, str) and len(v) > 500:
                safe[k] = v[:500] + "..."
            else:
                safe[k] = v
    return safe


def create_audit_event(
    event_type: str,
    category: str,
    *,
    severity: str = AuditEventSeverity.INFO,
    result: str = AuditEventResult.SUCCESS,
    actor_id: str | None = None,
    actor_role: str | None = None,
    target_type: str = "",
    target_id: str | None = None,
    request_id: str | None = None,
    summary: str = "",
    metadata: dict | None = None,
    source: str = "",
    retention_class: str = RetentionClass.OPERATIONAL,
) -> AuditEvent:
    """Create an audit event record and log to stdout."""
    safe_meta = _sanitize_metadata(metadata) if metadata else None

    event = AuditEvent.objects.create(
        event_type=event_type,
        category=category,
        severity=severity,
        result=result,
        actor_id=actor_id,
        actor_role=actor_role,
        target_type=target_type,
        target_id=str(target_id) if target_id else "",
        request_id=request_id or "",
        summary=summary,
        metadata=safe_meta,
        source=source,
        retention_class=retention_class,
    )

    # Also log to stdout
    _logger.info(
        f"audit.{event_type}",
        event_id=str(event.id),
        category=category,
        severity=severity,
        result=result,
        actor_id=actor_id or "",
        target_type=target_type,
        target_id=str(target_id) if target_id else "",
        summary=summary,
    )

    return event
