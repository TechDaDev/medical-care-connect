from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class RecordStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    FINALIZED = "finalized", _("Finalized")


class ClinicalOutcome(models.TextChoices):
    REMOTE_CARE_COMPLETED = "remote_care_completed", _("Remote care completed")
    FOLLOW_UP_REQUIRED = "follow_up_required", _("Follow-up required")
    PHYSICAL_VISIT_REQUIRED = "physical_visit_required", _("Physical visit required")
    TRANSFERRED = "transferred", _("Transferred")
    EMERGENCY_ESCALATED = "emergency_escalated", _("Emergency escalated")


class MedicalRecordDraft(BaseModel):
    """Structured medical record draft generated from an AI intake session."""

    consultation = models.OneToOneField(
        "consultations.Consultation",
        on_delete=models.CASCADE,
        related_name="medical_record",
        verbose_name=_("consultation"),
    )
    intake_session = models.OneToOneField(
        "ai_intake.AIIntakeSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_record",
        verbose_name=_("intake session"),
    )
    status = models.CharField(
        _("status"),
        max_length=15,
        choices=RecordStatus.choices,
        default=RecordStatus.DRAFT,
    )
    version = models.PositiveIntegerField(_("version"), default=1)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_medical_records",
        verbose_name=_("created by"),
    )

    # ── Clinical sections ─────────────────────────────────────────
    chief_complaint = models.TextField(_("chief complaint"), blank=True)
    history_of_present_illness = models.TextField(
        _("history of present illness"), blank=True
    )
    symptoms = models.JSONField(_("symptoms"), default=list, blank=True)
    severity = models.IntegerField(
        _("severity"), null=True, blank=True
    )
    onset_date = models.DateField(_("onset date"), null=True, blank=True)
    duration = models.CharField(_("duration"), max_length=100, blank=True)
    location = models.CharField(_("location"), max_length=255, blank=True)
    triggers = models.TextField(_("triggers"), blank=True)
    relieving_factors = models.TextField(_("relieving factors"), blank=True)

    # ── History sections ──────────────────────────────────────────
    past_medical_history = models.TextField(
        _("past medical history"), blank=True
    )
    medications = models.JSONField(
        _("medications"), default=list, blank=True
    )
    allergies = models.JSONField(
        _("allergies"), default=list, blank=True
    )
    family_history = models.TextField(_("family history"), blank=True)
    social_history = models.TextField(_("social history"), blank=True)
    review_of_systems = models.TextField(
        _("review of systems"), blank=True
    )

    # ── Metadata ──────────────────────────────────────────────────
    additional_notes = models.TextField(_("additional notes"), blank=True)
    doctor_notes = models.TextField(_("doctor notes"), blank=True)
    clinical_summary = models.TextField(_("clinical summary"), blank=True)
    assessment = models.TextField(_("assessment"), blank=True)
    working_diagnosis = models.TextField(_("working diagnosis"), blank=True)
    differential_considerations = models.TextField(
        _("differential considerations"), blank=True
    )
    recommendations = models.TextField(_("recommendations"), blank=True)
    treatment_plan = models.TextField(_("treatment plan"), blank=True)
    follow_up_plan = models.TextField(_("follow-up plan"), blank=True)
    physical_visit_reason = models.TextField(_("physical visit reason"), blank=True)
    warning_signs = models.TextField(_("warning signs"), blank=True)
    patient_instructions = models.TextField(_("patient instructions"), blank=True)
    provenance = models.JSONField(_("provenance"), default=dict, blank=True)
    finalized_at = models.DateTimeField(
        _("finalized at"), null=True, blank=True
    )
    finalized_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finalized_medical_records",
        verbose_name=_("finalized by"),
    )
    clinical_outcome = models.CharField(
        _("clinical outcome"),
        max_length=32,
        choices=ClinicalOutcome.choices,
        blank=True,
    )
    outcome_recorded_at = models.DateTimeField(
        _("outcome recorded at"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("medical record draft")
        verbose_name_plural = _("medical record drafts")

    def __str__(self) -> str:
        return f"Record {self.id} — Consultation {self.consultation_id}"


class MedicalRecordAction(BaseModel):
    """Clinical-write idempotency ledger; stores metadata, never narrative."""

    record = models.ForeignKey(
        MedicalRecordDraft,
        on_delete=models.CASCADE,
        related_name="actions",
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="medical_record_actions",
    )
    action = models.CharField(max_length=24)
    client_request_id = models.UUIDField()
    request_fingerprint = models.CharField(max_length=64)
    result_version = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "client_request_id"],
                name="medical_record_unique_actor_request",
            )
        ]
        indexes = [
            models.Index(fields=["record", "-created_at"]),
            models.Index(fields=["actor", "client_request_id"]),
        ]
