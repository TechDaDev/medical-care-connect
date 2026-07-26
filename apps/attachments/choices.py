from django.db import models
from django.utils.translation import gettext_lazy as _


class AttachmentCategory(models.TextChoices):
    MEDICAL_REPORT = "medical_report", _("Medical Report")
    LABORATORY_RESULT = "laboratory_result", _("Laboratory Result")
    MEDICAL_IMAGE = "medical_image", _("Medical Image")
    REFERRAL = "referral", _("Referral")
    IDENTITY_DOCUMENT = "identity_document", _("Identity Document")
    CONSENT_DOCUMENT = "consent_document", _("Consent Document")
    OTHER = "other", _("Other")


class AttachmentStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    AVAILABLE = "available", _("Available")
    QUARANTINED = "quarantined", _("Quarantined")
    REJECTED = "rejected", _("Rejected")
    DELETED = "deleted", _("Deleted")


class ScanStatus(models.TextChoices):
    NOT_REQUIRED = "not_required", _("Not Required")
    PENDING = "pending", _("Pending")
    CLEAN = "clean", _("Clean")
    SUSPICIOUS = "suspicious", _("Suspicious")
    INFECTED = "infected", _("Infected")
    FAILED = "failed", _("Failed")


class AttachmentEventType(models.TextChoices):
    UPLOADED = "uploaded", _("Uploaded")
    VALIDATED = "validated", _("Validated")
    SCAN_STARTED = "scan_started", _("Scan Started")
    SCAN_COMPLETED = "scan_completed", _("Scan Completed")
    VIEWED = "viewed", _("Viewed")
    DOWNLOADED = "downloaded", _("Downloaded")
    DELETED = "deleted", _("Deleted")
    RESTORED = "restored", _("Restored")
    REJECTED = "rejected", _("Rejected")
    STORAGE_ERROR = "storage_error", _("Storage Error")
    ADMIN_VIEWED = "admin_viewed", _("Admin Viewed")
    RESCAN_REQUESTED = "rescan_requested", _("Rescan Requested")
    QUARANTINED = "quarantined", _("Quarantined")
    RELEASED = "released", _("Released")
    RETENTION_DELETED = "retention_deleted", _("Retention Deleted")
    ADMIN_ACTION_FAILED = "admin_action_failed", _("Admin Action Failed")
