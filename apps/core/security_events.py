"""
Privacy-safe security event logging service.

Events are logged via SafeLogger — no medical content, passwords, raw IP,
tokens, file bytes, or original filenames (unless sanitized).

Events:
  auth.login.success / failed / logout / refresh.failed
  csrf.failed / permission.denied / throttle.exceeded
  attachment.uploaded / downloaded / deleted / quarantined
  consultation.transferred / priority_changed
  account.deactivated
  data.export.requested / completed
  restore.executed / backup.failed
"""

from apps.core.logging import SafeLogger

_logger = SafeLogger("mcc.security")


def _safe_event(event: str, **kwargs):
    """Log security event with safe kwargs only."""
    safe = {}
    for k, v in kwargs.items():
        if v is not None:
            safe[k] = v
    _logger.info(f"security.{event}", **safe)


# ── Auth ──

def auth_login_success(user_id: str, role: str, method: str = "password"):
    _safe_event("auth.login.success", user_id=user_id, role=role, auth_method=method)


def auth_login_failed(identifier: str, reason: str = "invalid_credentials"):
    _safe_event("auth.login.failed", reason=reason)


def auth_logout(user_id: str):
    _safe_event("auth.logout", user_id=user_id)


def auth_refresh_failed(reason: str = "invalid_token"):
    _safe_event("auth.refresh.failed", reason=reason)


# ── Request security ──

def csrf_failed(user_id: str = "", path: str = ""):
    _safe_event("csrf.failed", user_id=user_id, path=path)


def permission_denied(user_id: str, role: str, path: str, required_perm: str = ""):
    _safe_event("permission.denied", user_id=user_id, role=role, path=path, required_perm=required_perm)


def throttle_exceeded(user_id: str = "", path: str = "", rate: str = ""):
    _safe_event("throttle.exceeded", user_id=user_id, path=path, rate=rate)


# ── Attachments ──

def attachment_uploaded(attachment_id: str, consultation_id: str, user_id: str, category: str = ""):
    _safe_event("attachment.uploaded", attachment_id=attachment_id, consultation_id=consultation_id,
                user_id=user_id, category=category)


def attachment_downloaded(attachment_id: str, consultation_id: str, user_id: str):
    _safe_event("attachment.downloaded", attachment_id=attachment_id, consultation_id=consultation_id,
                user_id=user_id)


def attachment_deleted(attachment_id: str, consultation_id: str, user_id: str):
    _safe_event("attachment.deleted", attachment_id=attachment_id, consultation_id=consultation_id,
                user_id=user_id)


def attachment_quarantined(attachment_id: str, reason: str = ""):
    _safe_event("attachment.quarantined", attachment_id=attachment_id, reason=reason)


# ── Consultations ──

def consultation_transferred(consultation_id: str, from_doctor: str = "", to_doctor: str = "", by_user: str = ""):
    _safe_event("consultation.transferred", consultation_id=consultation_id,
                from_doctor=from_doctor, to_doctor=to_doctor, by_user=by_user)


def consultation_priority_changed(consultation_id: str, old: str = "", new: str = "", by_user: str = ""):
    _safe_event("consultation.priority_changed", consultation_id=consultation_id,
                old_priority=old, new_priority=new, by_user=by_user)


# ── Account ──

def account_deactivated(user_id: str, by_user: str = ""):
    _safe_event("account.deactivated", user_id=user_id, by_user=by_user)


def doctor_application_created(user_id: str, profile_id: str):
    _safe_event("doctor.application.created", user_id=user_id, profile_id=profile_id)


def doctor_application_reviewed(user_id: str, profile_id: str, status: str, by_user: str):
    _safe_event("doctor.application.reviewed", user_id=user_id, profile_id=profile_id,
                status=status, by_user=by_user)


def doctor_profile_updated(user_id: str, profile_id: str, changed_fields: list[str]):
    _safe_event("doctor.profile.updated", user_id=user_id, profile_id=profile_id,
                changed_fields=",".join(changed_fields))


# ── Data ──

def data_export_requested(user_id: str):
    _safe_event("data.export.requested", user_id=user_id)


def data_export_completed(export_id: str):
    _safe_event("data.export.completed", export_id=export_id)


# ── Operations ──

def restore_executed(backup_type: str = ""):
    _safe_event("restore.executed", backup_type=backup_type)


def backup_failed(backup_type: str = "", reason: str = ""):
    _safe_event("backup.failed", backup_type=backup_type, reason=reason)
