from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class IntakeSessionStatus(models.TextChoices):
    NOT_STARTED = "not_started", _("Not Started")
    IN_PROGRESS = "in_progress", _("In Progress")
    AWAITING_PATIENT = "awaiting_patient", _("Awaiting Patient")
    READY_FOR_REVIEW = "ready_for_review", _("Ready for Review")
    CONFIRMED = "confirmed", _("Confirmed")
    EMERGENCY_STOPPED = "emergency_stopped", _("Emergency Stopped")
    FAILED = "failed", _("Failed")


class EmergencyLevel(models.TextChoices):
    NONE = "none", _("None")
    WARNING = "warning", _("Warning")
    URGENT = "urgent", _("Urgent")
    EMERGENCY = "emergency", _("Emergency")


class IntakeLanguage(models.TextChoices):
    ENGLISH = "en", _("English")
    ARABIC = "ar", _("Arabic")
    KURDISH = "ku", _("Kurdish")


class AIIntakeSession(BaseModel):
    """One AI intake session per consultation."""

    consultation = models.OneToOneField(
        "consultations.Consultation",
        on_delete=models.CASCADE,
        related_name="intake_session",
        verbose_name=_("consultation"),
    )
    status = models.CharField(
        _("status"),
        max_length=25,
        choices=IntakeSessionStatus.choices,
        default=IntakeSessionStatus.NOT_STARTED,
    )
    language = models.CharField(
        _("language"),
        max_length=10,
        choices=IntakeLanguage.choices,
        default=IntakeLanguage.ENGLISH,
    )
    current_question = models.TextField(_("current question"), blank=True)
    question_count = models.PositiveIntegerField(_("question count"), default=0)
    emergency_detected = models.BooleanField(_("emergency detected"), default=False)
    emergency_level = models.CharField(
        _("emergency level"),
        max_length=15,
        choices=EmergencyLevel.choices,
        default=EmergencyLevel.NONE,
    )
    emergency_reasons = models.JSONField(_("emergency reasons"), default=list, blank=True)
    collected_data = models.JSONField(_("collected data"), default=dict, blank=True)
    missing_fields = models.JSONField(_("missing fields"), default=list, blank=True)
    ai_provider = models.CharField(_("AI provider"), max_length=30, blank=True)
    ai_model = models.CharField(_("AI model"), max_length=60, blank=True)
    prompt_version = models.CharField(_("prompt version"), max_length=30, blank=True)
    started_at = models.DateTimeField(_("started at"), blank=True, null=True)
    completed_at = models.DateTimeField(_("completed at"), blank=True, null=True)
    confirmed_at = models.DateTimeField(_("confirmed at"), blank=True, null=True)
    last_ai_request_at = models.DateTimeField(_("last AI request at"), blank=True, null=True)
    input_tokens = models.PositiveIntegerField(_("input tokens"), default=0)
    output_tokens = models.PositiveIntegerField(_("output tokens"), default=0)
    total_tokens = models.PositiveIntegerField(_("total tokens"), default=0)
    error_code = models.CharField(_("error code"), max_length=30, blank=True)
    error_message = models.TextField(_("error message"), blank=True)

    class Meta:
        verbose_name = _("AI intake session")
        verbose_name_plural = _("AI intake sessions")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["emergency_level"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"Intake {self.id} — {self.get_status_display()}"


class AIIntakeMessage(BaseModel):
    """A single message in an intake session conversation."""

    session = models.ForeignKey(
        AIIntakeSession,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("session"),
    )
    role = models.CharField(
        _("role"),
        max_length=10,
        choices=[("system", "System"), ("assistant", "Assistant"), ("patient", "Patient")],
    )
    content = models.TextField(_("content"))
    sequence_number = models.PositiveIntegerField(_("sequence number"))
    structured_data = models.JSONField(_("structured data"), null=True, blank=True)
    emergency_flags = models.JSONField(_("emergency flags"), default=list, blank=True)

    class Meta:
        verbose_name = _("AI intake message")
        verbose_name_plural = _("AI intake messages")
        unique_together = [("session", "sequence_number")]
        ordering = ["sequence_number"]

    def __str__(self) -> str:
        preview = self.content[:60]
        return f"[{self.sequence_number}] {self.role}: {preview}"
