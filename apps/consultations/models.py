from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class ConsultationStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    SUBMITTED = "submitted", _("Submitted")
    ACCEPTED = "accepted", _("Accepted")
    INTAKE_IN_PROGRESS = "intake_in_progress", _("Intake in Progress")
    INTAKE_COMPLETED = "intake_completed", _("Intake Completed")
    DOCTOR_REVIEW = "doctor_review", _("Doctor Review")
    AWAITING_PATIENT_RESPONSE = "awaiting_patient_response", _("Awaiting Patient Response")
    AWAITING_DOCTOR_RESPONSE = "awaiting_doctor_response", _("Awaiting Doctor Response")
    UNDER_REVIEW = "under_review", _("Under Review")
    FOLLOW_UP_REQUIRED = "follow_up_required", _("Follow-up Required")
    PHYSICAL_VISIT_REQUIRED = "physical_visit_required", _("Physical Visit Required")
    TRANSFERRED = "transferred", _("Transferred")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    EMERGENCY_ESCALATED = "emergency_escalated", _("Emergency Escalated")


class Priority(models.TextChoices):
    LOW = "low", _("Low")
    MEDIUM = "medium", _("Medium")
    HIGH = "high", _("High")
    URGENT = "urgent", _("Urgent")


class Consultation(BaseModel):
    """A consultation request from a patient to a doctor."""

    patient = models.ForeignKey(
        "patients.PatientProfile",
        on_delete=models.CASCADE,
        related_name="consultations",
        verbose_name=_("patient"),
    )
    doctor = models.ForeignKey(
        "doctors.DoctorProfile",
        on_delete=models.CASCADE,
        related_name="consultations",
        verbose_name=_("doctor"),
    )
    specialty = models.ForeignKey(
        "specialties.Specialty",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations",
        verbose_name=_("specialty"),
    )
    status = models.CharField(
        _("status"),
        max_length=30,
        choices=ConsultationStatus.choices,
        default=ConsultationStatus.SUBMITTED,
    )
    priority = models.CharField(
        _("priority"),
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    description = models.TextField(
        _("description"), blank=True,
        help_text=_("Initial description of the consultation request."),
    )
    cancellation_reason = models.TextField(
        _("cancellation reason"), blank=True,
        help_text=_("Reason for cancellation (required when cancelling)."),
    )
    submitted_at = models.DateTimeField(_("submitted at"), blank=True, null=True)
    accepted_at = models.DateTimeField(_("accepted at"), blank=True, null=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), blank=True, null=True)

    class Meta:
        verbose_name = _("consultation")
        verbose_name_plural = _("consultations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["patient", "status"]),
            models.Index(fields=["doctor", "status"]),
            models.Index(fields=["specialty", "status"]),
        ]

    def __str__(self) -> str:
        return f"Consultation {self.id} - {self.patient} -> Dr. {self.doctor}"
