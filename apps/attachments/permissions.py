from rest_framework.permissions import BasePermission

from apps.accounts.models import UserRole


class IsPatient(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == UserRole.PATIENT)


class IsDoctor(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == UserRole.DOCTOR)


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR)
        )


class IsParticipant(BasePermission):
    """Check user is patient, assigned doctor, or staff for the consultation."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        consultation = obj if hasattr(obj, "patient") else getattr(obj, "consultation", None)
        if not consultation:
            return False
        if user.role in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
            return True
        if user.role == UserRole.PATIENT:
            return consultation.patient.user == user
        if user.role == UserRole.DOCTOR:
            return consultation.doctor.user == user
        return False
