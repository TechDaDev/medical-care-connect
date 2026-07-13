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


def get_attachment_actions(attachment, user) -> dict:
    """Return action permissions for an attachment based on user role and state."""
    result = {
        "can_download": False,
        "can_delete": False,
        "can_restore": False,
        "can_view_audit": False,
    }
    consultation = attachment.consultation

    if user.role in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        result["can_download"] = attachment.is_available
        result["can_delete"] = not attachment.is_deleted
        result["can_restore"] = attachment.is_deleted
        result["can_view_audit"] = True
        return result

    is_patient = user.role == UserRole.PATIENT and consultation.patient.user == user
    is_doctor = user.role == UserRole.DOCTOR and consultation.doctor.user == user

    if not (is_patient or is_doctor):
        return result

    result["can_download"] = attachment.is_available

    if is_patient:
        from apps.consultations.models import ConsultationStatus as CS
        result["can_delete"] = (
            not attachment.is_deleted
            and attachment.uploaded_by == user
            and consultation.status in (CS.SUBMITTED, CS.DRAFT)
        )
    elif is_doctor:
        result["can_delete"] = (
            not attachment.is_deleted
            and attachment.uploaded_by == user
        )

    return result
