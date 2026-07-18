from rest_framework.permissions import BasePermission

from apps.accounts.models import UserRole


class IsPatient(BasePermission):
    """Grant access if the authenticated user has the patient role."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.PATIENT
        )


class IsDoctor(BasePermission):
    """Grant access if the authenticated user has the doctor role."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.DOCTOR
        )


class IsApprovedDoctor(BasePermission):
    """Grant doctor-only operational access after staff approval."""

    def has_permission(self, request, view):
        profile = getattr(request.user, "doctor_profile", None)
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.DOCTOR
            and profile
            and profile.is_approved
        )


class IsCoordinator(BasePermission):
    """Grant access if the authenticated user has the coordinator role."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.COORDINATOR
        )


class IsAdministrator(BasePermission):
    """Grant access if the authenticated user has the administrator role."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.ADMINISTRATOR
        )


class IsDoctorOrAdministrator(BasePermission):
    """Grant access to doctors and administrators."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (UserRole.DOCTOR, UserRole.ADMINISTRATOR)
        )


class IsCoordinatorOrAdministrator(BasePermission):
    """Grant access to coordinators and administrators."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR)
        )
