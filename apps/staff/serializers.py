"""Serializers for staff endpoints."""
from rest_framework import serializers

from apps.consultations.models import Consultation, ConsultationStatus


class StaffConsultationListSerializer(serializers.ModelSerializer):
    """Lightweight consultation list for staff views."""

    patient_name = serializers.CharField(
        source="patient.user.full_name", read_only=True, default=None
    )
    patient_email = serializers.EmailField(
        source="patient.user.email", read_only=True, default=None
    )
    doctor_name = serializers.CharField(
        source="doctor.user.full_name", read_only=True, default=None
    )
    doctor_email = serializers.EmailField(
        source="doctor.user.email", read_only=True, default=None
    )
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    priority_display = serializers.CharField(
        source="get_priority_display", read_only=True
    )

    class Meta:
        model = Consultation
        fields = [
            "id",
            "patient_name",
            "patient_email",
            "doctor_name",
            "doctor_email",
            "specialty_name",
            "status",
            "status_display",
            "priority",
            "priority_display",
            "description",
            "created_at",
            "updated_at",
            "submitted_at",
            "accepted_at",
        ]
        read_only_fields = fields


class TransferConsultationSerializer(serializers.Serializer):
    """Serializer for transferring a consultation."""

    doctor_id = serializers.UUIDField(required=True)
    reason = serializers.CharField(
        required=True, min_length=1, max_length=1000
    )


class PriorityUpdateSerializer(serializers.Serializer):
    """Serializer for updating consultation priority."""

    priority = serializers.ChoiceField(
        choices=["routine", "urgent", "emergency"],
        required=True,
    )


class DoctorWorkloadSerializer(serializers.Serializer):
    """Serializer for doctor workload summary."""

    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    specialty_name = serializers.CharField(read_only=True, default=None)
    is_approved = serializers.BooleanField(read_only=True)
    is_accepting_consultations = serializers.BooleanField(read_only=True)
    active_count = serializers.IntegerField(read_only=True)
    submitted_count = serializers.IntegerField(read_only=True)
    accepted_count = serializers.IntegerField(read_only=True)
    intake_completed_count = serializers.IntegerField(read_only=True)
    doctor_review_count = serializers.IntegerField(read_only=True)
    estimated_response_minutes = serializers.IntegerField(read_only=True, default=None)


# ── Doctor Application Serializers ─────────────────────────────────────────

from apps.doctors.models import DoctorProfile, LicenseDocument


def get_available_actions(profile: DoctorProfile, is_admin: bool) -> list[str]:
    """Return allowed review actions server-side based on status and role."""
    status = profile.approval_status
    if status == DoctorProfile.ApprovalStatus.PENDING:
        return ["approve", "reject"]
    if status == DoctorProfile.ApprovalStatus.APPROVED:
        if is_admin:
            return ["suspend"]
        return []
    if status == DoctorProfile.ApprovalStatus.REJECTED:
        return []
    if status == DoctorProfile.ApprovalStatus.SUSPENDED:
        if is_admin:
            return ["reactivate"]
        return []
    return []


def _mask_license_number(number: str) -> str:
    if not number:
        return ""
    if len(number) <= 4:
        return "****"
    return f"****{number[-4:]}"


class DoctorApplicationListSerializer(serializers.ModelSerializer):
    """Lightweight list serializer — no full license number."""

    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None
    )
    has_license_document = serializers.SerializerMethodField()
    license_document_verified = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = [
            "id", "user_id", "full_name", "email",
            "specialty_name", "professional_title",
            "years_of_experience", "workplace_name",
            "approval_status", "created_at", "updated_at",
            "has_license_document", "license_document_verified",
        ]

    def get_has_license_document(self, obj) -> bool:
        return hasattr(obj, "license_document") and obj.license_document is not None

    def get_license_document_verified(self, obj) -> bool:
        doc = getattr(obj, "license_document", None)
        return doc.is_verified if doc else False


class DoctorApplicationDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with license metadata and available actions."""

    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True, default="")
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None
    )
    license_number_masked = serializers.SerializerMethodField()
    has_license_document = serializers.SerializerMethodField()
    license_document_verified = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = [
            "id", "user_id", "full_name", "email", "phone_number",
            "specialty_name", "professional_title", "workplace_name",
            "biography", "qualifications", "years_of_experience",
            "consultation_fee", "languages", "estimated_response_minutes",
            "approval_status", "approval_note", "created_at", "updated_at",
            "license_number_masked", "has_license_document",
            "license_document_verified", "available_actions",
        ]

    def get_license_number_masked(self, obj) -> str:
        return _mask_license_number(obj.license_number)

    def get_has_license_document(self, obj) -> bool:
        return hasattr(obj, "license_document") and obj.license_document is not None

    def get_license_document_verified(self, obj) -> bool:
        doc = getattr(obj, "license_document", None)
        return doc.is_verified if doc else False

    def get_available_actions(self, obj) -> list[str]:
        is_admin = False
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            from apps.accounts.models import UserRole
            is_admin = request.user.role == UserRole.ADMINISTRATOR
        return get_available_actions(obj, is_admin)


class DoctorApplicationReviewSerializer(serializers.Serializer):
    """Validate review action payload."""

    action = serializers.ChoiceField(
        choices=["approve", "reject", "suspend", "reactivate"],
        required=True,
    )
    reason = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=500
    )
    expected_status = serializers.ChoiceField(
        choices=["pending", "approved", "rejected", "suspended"],
        required=False,
    )

    def validate_reason(self, value):
        if self.initial_data.get("action") in ("reject", "suspend", "reactivate"):
            if not value or not value.strip():
                raise serializers.ValidationError(
                    "Reason is required for this action."
                )
        return value.strip() if value else ""
