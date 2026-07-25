from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class NotificationType(models.TextChoices):
    NEW_MESSAGE = "new_message", _("New Message")
    CONSULTATION_ACCEPTED = "consultation_accepted", _("Consultation Accepted")
    CONSULTATION_CANCELLED = "consultation_cancelled", _("Consultation Cancelled")
    INTAKE_COMPLETED = "intake_completed", _("Intake Completed")
    RECORD_CONFIRMED = "record_confirmed", _("Record Confirmed")
    RECORD_REVISION_REQUESTED = "record_revision_requested", _("Record Revision Requested")
    STATUS_CHANGE = "status_change", _("Status Change")
    # Phase 11 — Reviews
    REVIEW_AVAILABLE = "review_available", _("Review Available")
    REVIEW_RESPONSE = "review_response", _("Review Response")
    MODERATION_STATE = "moderation_state", _("Moderation State")
    REPORT_RESOLUTION = "report_resolution", _("Report Resolution")
    DOCTOR_APPLICATION = "doctor_application", _("Doctor Application")
    DOCTOR_APPLICATION_STATUS = "doctor_application_status", _("Doctor Application Status")
    ACCOUNT_STATUS_CHANGE = "account_status_change", _("Account Status Change")


class Notification(BaseModel):
    """An in-app notification for a user."""

    recipient = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("recipient"),
    )
    notification_type = models.CharField(
        _("notification type"),
        max_length=40,
        choices=NotificationType.choices,
    )
    title = models.CharField(_("title"), max_length=255)
    body = models.TextField(_("body"), blank=True)
    consultation = models.ForeignKey(
        "consultations.Consultation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name=_("consultation"),
    )
    related_message = models.ForeignKey(
        "messaging.ConsultationMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name=_("related message"),
    )
    is_read = models.BooleanField(_("is read"), default=False)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["notification_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.notification_type}: {self.title[:50]}"
