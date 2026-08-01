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
    completed_at = models.DateTimeField(_("completed at"), blank=True, null=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), blank=True, null=True)
    client_request_id = models.UUIDField(
        _("client request ID"),
        null=True,
        blank=True,
        help_text=_("Patient-scoped idempotency key for consultation creation."),
    )

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
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "client_request_id"],
                name="consultation_unique_patient_request_id",
            ),
        ]

    def __str__(self) -> str:
        return f"Consultation {self.id} - {self.patient} -> Dr. {self.doctor}"


class DoctorConsultationAction(BaseModel):
    """Append-only doctor workflow event and idempotency marker."""

    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name="doctor_actions",
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="doctor_consultation_actions",
    )
    action = models.CharField(max_length=40)
    old_status = models.CharField(max_length=30, choices=ConsultationStatus.choices)
    new_status = models.CharField(max_length=30, choices=ConsultationStatus.choices)
    reason = models.TextField(blank=True, max_length=1000)
    target_doctor = models.ForeignKey(
        "doctors.DoctorProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_doctor_actions",
    )
    client_request_id = models.UUIDField()

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "client_request_id"],
                name="doctor_action_unique_actor_request_id",
            ),
        ]
        indexes = [
            models.Index(fields=["consultation", "created_at"]),
            models.Index(fields=["consultation", "action"]),
        ]


class ConsultationTransfer(BaseModel):
    """Records a consultation transfer between doctors."""

    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name="transfers",
        verbose_name=_("consultation"),
    )
    previous_doctor = models.ForeignKey(
        "doctors.DoctorProfile",
        on_delete=models.SET_NULL,
        null=True,
        related_name="transfers_out",
        verbose_name=_("previous doctor"),
    )
    new_doctor = models.ForeignKey(
        "doctors.DoctorProfile",
        on_delete=models.SET_NULL,
        null=True,
        related_name="transfers_in",
        verbose_name=_("new doctor"),
    )
    transferred_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="initiated_transfers",
        verbose_name=_("transferred by"),
    )
    reason = models.TextField(
        _("reason"),
        max_length=1000,
        help_text=_("Reason for the transfer."),
    )

    class Meta:
        verbose_name = _("consultation transfer")
        verbose_name_plural = _("consultation transfers")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Transfer {self.id}: {self.consultation.id}"


class ConsultationPriorityChange(BaseModel):
    """Audit log for priority changes on consultations."""

    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name="priority_changes",
        verbose_name=_("consultation"),
    )
    previous_priority = models.CharField(
        _("previous priority"),
        max_length=10,
    )
    new_priority = models.CharField(
        _("new priority"),
        max_length=10,
    )
    changed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="priority_changes",
        verbose_name=_("changed by"),
    )
    reason = models.TextField(
        _("reason"),
        max_length=500,
        blank=True,
        help_text=_("Optional reason for the priority change."),
    )

    class Meta:
        verbose_name = _("consultation priority change")
        verbose_name_plural = _("consultation priority changes")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"Priority {self.consultation.id}: "
            f"{self.previous_priority} → {self.new_priority}"
        )
