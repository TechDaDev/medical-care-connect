from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import UserRole
from apps.core.models import BaseModel


class DoctorProfile(BaseModel):
    """Profile information for a doctor user."""

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="doctor_profile",
        verbose_name=_("user"),
    )
    specialty = models.ForeignKey(
        "specialties.Specialty",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctor_profiles",
        verbose_name=_("specialty"),
    )
    professional_title = models.CharField(_("professional title"), max_length=255, blank=True)
    license_number = models.CharField(
        _("license number"), max_length=100, unique=True, blank=True
    )
    qualifications = models.TextField(
        _("qualifications"), blank=True,
        help_text=_("List of medical qualifications, one per line."),
    )
    biography = models.TextField(_("biography"), blank=True)
    years_of_experience = models.PositiveIntegerField(
        _("years of experience"), default=0
    )
    consultation_fee = models.DecimalField(
        _("consultation fee"), max_digits=10, decimal_places=2, default=0.00
    )
    languages = models.JSONField(
        _("languages"), default=list, blank=True,
        help_text=_("List of languages the doctor speaks, e.g. [\"English\", \"Arabic\"]"),
    )
    is_approved = models.BooleanField(
        _("approved"),
        default=False,
        help_text=_("Designates whether this doctor has been approved by a coordinator or admin."),
    )
    is_accepting_consultations = models.BooleanField(
        _("accepting consultations"),
        default=False,
        help_text=_("Designates whether the doctor is currently accepting new consultations."),
    )
    estimated_response_minutes = models.PositiveIntegerField(
        _("estimated response time (minutes)"), default=60
    )

    class Meta:
        verbose_name = _("doctor profile")
        verbose_name_plural = _("doctor profiles")
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self) -> str:
        return f"Dr. {self.user.full_name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.user.role != UserRole.DOCTOR:
            raise ValidationError(
                _("Doctor profile can only be linked to a user with the doctor role.")
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Weekday(models.TextChoices):
    MONDAY = "monday", _("Monday")
    TUESDAY = "tuesday", _("Tuesday")
    WEDNESDAY = "wednesday", _("Wednesday")
    THURSDAY = "thursday", _("Thursday")
    FRIDAY = "friday", _("Friday")
    SATURDAY = "saturday", _("Saturday")
    SUNDAY = "sunday", _("Sunday")


class DoctorAvailability(BaseModel):
    """Availability slot for a doctor."""

    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name="availability_slots",
        verbose_name=_("doctor"),
    )
    day_of_week = models.CharField(
        _("day of week"),
        max_length=10,
        choices=Weekday.choices,
    )
    start_time = models.TimeField(_("start time"))
    end_time = models.TimeField(_("end time"))
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("doctor availability")
        verbose_name_plural = _("doctor availabilities")
        ordering = ["doctor", "day_of_week", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "day_of_week", "start_time", "end_time"],
                name="unique_doctor_availability_slot",
            ),
            models.CheckConstraint(
                check=models.Q(start_time__lt=models.F("end_time")),
                name="avail_start_before_end",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.doctor} - {self.day_of_week} {self.start_time}-{self.end_time}"
