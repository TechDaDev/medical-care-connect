from uuid import uuid4

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.managers import UserManager


class UserRole(models.TextChoices):
    """Enumeration of possible user roles in the system."""

    PATIENT = "patient", _("Patient")
    DOCTOR = "doctor", _("Doctor")
    COORDINATOR = "coordinator", _("Coordinator")
    ADMINISTRATOR = "administrator", _("Administrator")


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model with email-based authentication and role support."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    email = models.EmailField(
        _("email address"),
        unique=True,
        max_length=255,
        help_text=_("Required. Used for login."),
        error_messages={
            "unique": _("A user with this email already exists."),
        },
    )
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    phone_number = models.CharField(_("phone number"), max_length=20, blank=True)
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.PATIENT,
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Designates whether this user should be treated as active."),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    date_joined = models.DateTimeField(_("date joined"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return self.email

    @property
    def full_name(self) -> str:
        """Return the full name. Falls back to email if name fields are empty."""
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.email
