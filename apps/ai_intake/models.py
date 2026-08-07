from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class IntakeSessionStatus(models.TextChoices):
    NOT_STARTED = "not_started", _("Not Started")
    IN_PROGRESS = "in_progress", _("In Progress")
    AWAITING_PATIENT_REVIEW = "awaiting_patient_review", _("Awaiting Patient Review")
    CORRECTION_IN_PROGRESS = "correction_in_progress", _("Correction In Progress")
    CONFIRMED = "confirmed", _("Confirmed")
    SUBMITTED_TO_DOCTOR = "submitted_to_doctor", _("Submitted To Doctor")
    EMERGENCY_STOPPED = "emergency_stopped", _("Emergency Stopped")
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable", _("Temporarily Unavailable")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


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
    """One AI intake session per consultation.

    The deterministic backend controls all state transitions, completion
    gates, emergency stops, confirmation, and submission.  DeepSeek only
    assists with conversational wording and structured extraction.
    """

    consultation = models.OneToOneField(
        "consultations.Consultation",
        on_delete=models.CASCADE,
        related_name="intake_session",
        verbose_name=_("consultation"),
    )
    status = models.CharField(
        _("status"),
        max_length=30,
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
    emergency_escalated_at = models.DateTimeField(_("emergency escalated at"), blank=True, null=True)

    # ── Structured per-field metadata ──────────────────────────────
    # Maps allowlisted field name -> {
    #   value, status (missing|answered|unknown|declined|not_applicable|uncertain),
    #   source (patient_message|patient_profile|intake_extraction|patient_correction),
    #   confidence ("low"|"medium"|"high" — internal only, never shown as medical
    #   certainty), evidence_message_ids: [uuid], confirmed_by_patient: bool
    # }
    field_metadata = models.JSONField(_("field metadata"), default=dict, blank=True)

    # Conditional-relevance rules the backend accepted from the AI.
    suggested_relevant_fields = models.JSONField(
        _("suggested relevant fields"), default=list, blank=True
    )

    # Backward-compatible summary derived from field_metadata.
    collected_data = models.JSONField(_("collected data"), default=dict, blank=True)
    missing_fields = models.JSONField(_("missing fields"), default=list, blank=True)

    patient_review_summary = models.JSONField(
        _("patient review summary"), default=dict, blank=True
    )
    confirmation_snapshot = models.JSONField(
        _("confirmation snapshot"), default=dict, blank=True
    )
    confirmed_at = models.DateTimeField(_("confirmed at"), blank=True, null=True)
    submitted_at = models.DateTimeField(_("submitted at"), blank=True, null=True)

    ai_provider = models.CharField(_("AI provider"), max_length=30, blank=True)
    ai_model = models.CharField(_("AI model"), max_length=60, blank=True)
    prompt_version = models.CharField(_("prompt version"), max_length=30, blank=True)
    schema_version = models.CharField(_("schema version"), max_length=30, blank=True)

    started_at = models.DateTimeField(_("started at"), blank=True, null=True)
    completed_at = models.DateTimeField(_("completed at"), blank=True, null=True)
    last_ai_request_at = models.DateTimeField(_("last AI request at"), blank=True, null=True)
    provider_calls = models.PositiveIntegerField(_("provider calls"), default=0)

    input_tokens = models.PositiveIntegerField(_("input tokens"), default=0)
    output_tokens = models.PositiveIntegerField(_("output tokens"), default=0)
    total_tokens = models.PositiveIntegerField(_("total tokens"), default=0)
    retry_count = models.PositiveIntegerField(_("retry count"), default=0)

    # Safe machine error code only — never raw provider text.
    error_code = models.CharField(_("error code"), max_length=40, blank=True)

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
    client_request_id = models.UUIDField(
        _("client request ID"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("AI intake message")
        verbose_name_plural = _("AI intake messages")
        unique_together = [
            ("session", "sequence_number"),
            ("session", "client_request_id"),
        ]
        ordering = ["sequence_number"]

    def __str__(self) -> str:
        preview = self.content[:60]
        return f"[{self.sequence_number}] {self.role}: {preview}"


class IntakeIdempotencyLedger(BaseModel):
    """Idempotency + audit metadata ledger.

    Stores only safe metadata — never message content, symptoms, medications,
    summaries, prompts, or provider response bodies.
    """

    session = models.ForeignKey(
        AIIntakeSession,
        on_delete=models.CASCADE,
        related_name="idempotency_ledger",
    )
    action = models.CharField(max_length=24)  # answer|confirm|submit|correction|emergency
    client_request_id = models.UUIDField()
    result_code = models.CharField(max_length=40, blank=True)
    provider_call_count = models.PositiveIntegerField(default=0)
    state_before = models.CharField(max_length=30, blank=True)
    state_after = models.CharField(max_length=30, blank=True)
    token_delta = models.PositiveIntegerField(default=0)
    emergency_level_code = models.CharField(max_length=15, blank=True)
    prompt_version = models.CharField(max_length=30, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "action", "client_request_id"],
                name="intake_unique_session_action_request",
            )
        ]
        indexes = [
            models.Index(fields=["session", "-created_at"]),
            models.Index(fields=["session", "action", "client_request_id"]),
        ]