from uuid import uuid4

from django.db import models


class BaseModel(models.Model):
    """Abstract base model with UUID primary key and timestamp fields."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditEventCategory(models.TextChoices):
    ACCOUNT = "account", "Account"
    PRIVACY = "privacy", "Privacy"
    DOCTOR = "doctor", "Doctor"
    CONSULTATION = "consultation", "Consultation"
    SECURITY = "security", "Security"
    SYSTEM = "system", "System"


class AuditEventSeverity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"


class AuditEventResult(models.TextChoices):
    SUCCESS = "success", "Success"
    DENIED = "denied", "Denied"
    FAILED = "failed", "Failed"


class RetentionClass(models.TextChoices):
    SECURITY_CRITICAL = "security_critical", "Security Critical"
    PRIVACY_DECISION = "privacy_decision", "Privacy Decision"
    OPERATIONAL = "operational", "Operational"
    INFORMATIONAL = "informational", "Informational"


class AuditEvent(BaseModel):
    """Append-only audit event store. No update/delete after creation."""

    event_type = models.CharField(max_length=100, db_index=True)
    category = models.CharField(
        max_length=30, choices=AuditEventCategory.choices, db_index=True
    )
    severity = models.CharField(
        max_length=20, choices=AuditEventSeverity.choices, default=AuditEventSeverity.INFO
    )
    result = models.CharField(
        max_length=20, choices=AuditEventResult.choices, default=AuditEventResult.SUCCESS
    )
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor_id = models.UUIDField(null=True, blank=True)
    actor_role = models.CharField(max_length=20, null=True, blank=True)
    target_type = models.CharField(max_length=50, blank=True, default="")
    target_id = models.CharField(max_length=255, blank=True, default="")
    request_id = models.CharField(max_length=100, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    metadata = models.JSONField(null=True, blank=True)
    source = models.CharField(max_length=100, blank=True, default="")
    retention_class = models.CharField(
        max_length=30, choices=RetentionClass.choices, default=RetentionClass.OPERATIONAL
    )

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["category", "severity"]),
            models.Index(fields=["actor_id", "occurred_at"]),
        ]
        # Prevent accidental update/delete at model level
        # Permissions are enforced at the view layer

    def __str__(self):
        return f"{self.event_type} [{self.result}] @ {self.occurred_at}"
