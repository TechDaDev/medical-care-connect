import json

from django.db import transaction
from rest_framework import serializers

from apps.doctors.models import DoctorAvailability, DoctorProfile


class DoctorOwnProfileReadSerializer(serializers.ModelSerializer):
    """Safe read serializer for the doctor's own profile.

    Exposes user info, professional data, and safe license metadata.
    Does NOT expose the raw storage key or URL of the license document.
    """

    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None
    )
    has_license_document = serializers.SerializerMethodField()
    license_document_verified = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "specialty",
            "specialty_name",
            "professional_title",
            "workplace_name",
            "qualifications",
            "biography",
            "years_of_experience",
            "consultation_fee",
            "languages",
            "is_approved",
            "approval_status",
            "is_accepting_consultations",
            "estimated_response_minutes",
            "has_license_document",
            "license_document_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_has_license_document(self, obj) -> bool:
        return hasattr(obj, "license_document") and obj.license_document is not None

    def get_license_document_verified(self, obj) -> bool:
        if hasattr(obj, "license_document") and obj.license_document is not None:
            return obj.license_document.is_verified
        return False


ALLOWED_LANGUAGES = {"ar", "en", "ckb"}


class DoctorOwnProfileUpdateSerializer(serializers.ModelSerializer):
    """Strict update serializer for doctor's own professional profile.

    Only fields a doctor is allowed to edit are included.
    Sensitive fields (license_number, approval_status, is_approved,
    approval_note, is_accepting_consultations, medical_license_document)
    are deliberately absent so they cannot be set through this endpoint.
    """

    languages = serializers.JSONField(required=False)

    class Meta:
        model = DoctorProfile
        fields = [
            "specialty",
            "professional_title",
            "workplace_name",
            "qualifications",
            "biography",
            "years_of_experience",
            "consultation_fee",
            "languages",
            "estimated_response_minutes",
        ]

    def validate_specialty(self, value):
        from apps.specialties.models import Specialty

        if not Specialty.objects.filter(id=value.id, is_active=True).exists():
            raise serializers.ValidationError("Selected specialty is not available.")
        return value

    def validate_years_of_experience(self, value):
        if value < 0 or value > 70:
            raise serializers.ValidationError("Years of experience must be between 0 and 70.")
        return value

    def validate_consultation_fee(self, value):
        if value < 0:
            raise serializers.ValidationError("Consultation fee cannot be negative.")
        return value

    def validate_languages(self, value):
        if not isinstance(value, list) or len(value) < 1:
            raise serializers.ValidationError("Provide at least one language.")
        seen = set()
        for lang in value:
            if lang not in ALLOWED_LANGUAGES:
                raise serializers.ValidationError(f"Unsupported language: {lang}")
            if lang in seen:
                raise serializers.ValidationError(f"Duplicate language: {lang}")
            seen.add(lang)
        return value

    def validate_estimated_response_minutes(self, value):
        if value < 1 or value > 1440:
            raise serializers.ValidationError("Response time must be between 1 and 1440 minutes.")
        return value

    def validate(self, attrs):
        """Reject unknown fields not in the allowed set."""
        allowed = set(self.get_fields().keys())
        incoming = set(self.initial_data.keys()) if hasattr(self, "initial_data") else set()
        unknown = incoming - allowed
        if unknown:
            raise serializers.ValidationError(
                {field: ["This field is not allowed."] for field in sorted(unknown)}
            )
        return attrs

    def update(self, instance, validated_data):
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            instance.refresh_from_db()
        return instance


class DoctorProfileDetailSerializer(serializers.ModelSerializer):
    """DEPRECATED: Kept for backward compatibility. Prefer DoctorOwnProfileReadSerializer."""

    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None
    )
    has_license_document = serializers.SerializerMethodField()
    license_document_verified = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "specialty",
            "specialty_name",
            "professional_title",
            "workplace_name",
            "qualifications",
            "biography",
            "years_of_experience",
            "consultation_fee",
            "languages",
            "is_approved",
            "approval_status",
            "is_accepting_consultations",
            "estimated_response_minutes",
            "has_license_document",
            "license_document_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_has_license_document(self, obj) -> bool:
        return hasattr(obj, "license_document") and obj.license_document is not None

    def get_license_document_verified(self, obj) -> bool:
        if hasattr(obj, "license_document") and obj.license_document is not None:
            return obj.license_document.is_verified
        return False


class PublicDoctorListSerializer(serializers.ModelSerializer):
    """Public-facing serializer for the doctor directory (list)."""

    full_name = serializers.CharField(source="user.full_name", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None
    )

    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "specialty",
            "specialty_name",
            "professional_title",
            "qualifications",
            "biography",
            "workplace_name",
            "years_of_experience",
            "consultation_fee",
            "languages",
            "is_accepting_consultations",
            "estimated_response_minutes",
        ]
        read_only_fields = fields


class PublicDoctorDetailSerializer(serializers.ModelSerializer):
    """Public-facing serializer for a single doctor profile (detail)."""

    full_name = serializers.CharField(source="user.full_name", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None
    )

    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "specialty",
            "specialty_name",
            "professional_title",
            "qualifications",
            "biography",
            "workplace_name",
            "years_of_experience",
            "consultation_fee",
            "languages",
            "is_accepting_consultations",
            "estimated_response_minutes",
            "created_at",
        ]
        read_only_fields = fields


class DoctorAvailabilitySerializer(serializers.ModelSerializer):
    """Serializer for DoctorAvailability."""

    day_of_week_display = serializers.CharField(
        source="get_day_of_week_display", read_only=True
    )

    class Meta:
        model = DoctorAvailability
        fields = [
            "id",
            "doctor",
            "day_of_week",
            "day_of_week_display",
            "start_time",
            "end_time",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "doctor", "created_at", "updated_at"]


class DoctorAcceptingStatusSerializer(serializers.Serializer):
    """Serializer for updating the doctor's accepting-consultations status."""

    is_accepting_consultations = serializers.BooleanField(required=True)
