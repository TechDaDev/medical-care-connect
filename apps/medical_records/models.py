from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class RecordStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    FINALIZED = "finalized", _("Finalized")


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
    finalized_at = models.DateTimeField(
        _("finalized at"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("medical record draft")
        verbose_name_plural = _("medical record drafts")

    def __str__(self) -> str:
        return f"Record {self.id} — Consultation {self.consultation_id}"
