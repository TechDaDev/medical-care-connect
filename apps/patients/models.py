from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import UserRole
from apps.core.models import BaseModel


class Gender(models.TextChoices):
    MALE = "male", _("Male")
    FEMALE = "female", _("Female")
    OTHER = "other", _("Other")
    PREFER_NOT_TO_SAY = "prefer_not_to_say", _("Prefer not to say")


class BloodType(models.TextChoices):
    A_POSITIVE = "A+", "A+"
    A_NEGATIVE = "A-", "A-"
    B_POSITIVE = "B+", "B+"
    B_NEGATIVE = "B-", "B-"
    AB_POSITIVE = "AB+", "AB+"
    AB_NEGATIVE = "AB-", "AB-"
    O_POSITIVE = "O+", "O+"
    O_NEGATIVE = "O-", "O-"
    UNKNOWN = "unknown", _("Unknown")


class PreferredLanguage(models.TextChoices):
    ENGLISH = "en", _("English")
    ARABIC = "ar", _("Arabic")
    KURDISH = "ku", _("Kurdish")


class PatientProfile(BaseModel):
    """Profile information for a patient user."""

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="patient_profile",
        verbose_name=_("user"),
    )
    date_of_birth = models.DateField(_("date of birth"), blank=True, null=True)
    gender = models.CharField(
        _("gender"),
        max_length=20,
        choices=Gender.choices,
        default=Gender.PREFER_NOT_TO_SAY,
    )
    preferred_language = models.CharField(
        _("preferred language"),
        max_length=10,
        choices=PreferredLanguage.choices,
        default=PreferredLanguage.ENGLISH,
    )
    address = models.TextField(_("address"), blank=True)
    emergency_contact_name = models.CharField(
        _("emergency contact name"), max_length=255, blank=True
    )
    emergency_contact_phone = models.CharField(
        _("emergency contact phone"), max_length=20, blank=True
    )
    blood_type = models.CharField(
        _("blood type"),
        max_length=10,
        choices=BloodType.choices,
        default=BloodType.UNKNOWN,
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("patient profile")
        verbose_name_plural = _("patient profiles")

    def __str__(self) -> str:
        return f"Patient: {self.user.full_name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.user.role != UserRole.PATIENT:
            raise ValidationError(
                _("Patient profile can only be linked to a user with the patient role.")
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
