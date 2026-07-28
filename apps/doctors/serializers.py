import json
from decimal import Decimal

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


class DoctorSearchQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=120)
    specialty = serializers.UUIDField(required=False)
    specialty_slug = serializers.SlugField(required=False, max_length=255)
    language = serializers.ChoiceField(required=False, choices=sorted(ALLOWED_LANGUAGES))
    accepting = serializers.BooleanField(required=False)
    min_experience = serializers.IntegerField(required=False, min_value=0, max_value=70)
    min_fee = serializers.DecimalField(
        required=False,
        min_value=Decimal("0"),
        max_digits=10,
        decimal_places=2,
    )
    max_fee = serializers.DecimalField(
        required=False,
        min_value=Decimal("0"),
        max_digits=10,
        decimal_places=2,
    )
    max_response_minutes = serializers.IntegerField(
        required=False, min_value=1, max_value=1440
    )
    ordering = serializers.ChoiceField(
        required=False,
        default="relevance",
        choices=[
            "relevance",
            "name",
            "experience_desc",
            "fee_asc",
            "fee_desc",
            "response_time_asc",
            "newest",
        ],
    )
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(
        required=False, min_value=1, max_value=50, default=20
    )
    locale = serializers.ChoiceField(
        required=False, choices=["en", "ar", "ckb"]
    )

    def validate(self, attrs):
        min_fee = attrs.get("min_fee")
        max_fee = attrs.get("max_fee")
        if min_fee is not None and max_fee is not None and min_fee > max_fee:
            raise serializers.ValidationError(
                {"max_fee": "max_fee_must_be_greater_than_min_fee"}
            )
        return attrs


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
    specialty = serializers.SerializerMethodField()
    consultation_fee = serializers.SerializerMethodField()
    average_rating = serializers.FloatField(read_only=True, default=0.0)
    total_reviews = serializers.IntegerField(read_only=True, default=0)
    profile_summary = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "full_name",
            "specialty",
            "professional_title",
            "workplace_name",
            "years_of_experience",
            "consultation_fee",
            "languages",
            "is_accepting_consultations",
            "estimated_response_minutes",
            "average_rating",
            "total_reviews",
            "profile_summary",
            "available_actions",
        ]
        read_only_fields = fields

    def _specialty_name(self, obj) -> str | None:
        if obj.specialty is None:
            return None
        request = self.context.get("request")
        locale = ""
        if request is not None:
            locale = request.query_params.get("locale", "")
            if not locale:
                locale = request.headers.get("Accept-Language", "").split(",")[0]
        locale = locale.lower().split("-")[0]
        if locale == "ar":
            return obj.specialty.name_ar or obj.specialty.name
        if locale == "ckb":
            return obj.specialty.name_ckb or obj.specialty.name
        return obj.specialty.name_en or obj.specialty.name

    def get_specialty(self, obj) -> dict | None:
        if obj.specialty is None:
            return None
        return {
            "id": obj.specialty.id,
            "slug": obj.specialty.slug,
            "name": self._specialty_name(obj),
        }

    def get_consultation_fee(self, obj) -> dict | None:
        if obj.consultation_fee is None:
            return None
        return {
            "amount": format(obj.consultation_fee, ".2f"),
            "currency": "USD",
        }

    def get_profile_summary(self, obj) -> str:
        summary = " ".join((obj.biography or "").split())
        return summary[:240]

    def get_available_actions(self, obj) -> list[str]:
        actions = ["view"]
        if (
            obj.is_accepting_consultations
            and obj.user.is_active
            and obj.is_approved
            and obj.approval_status == DoctorProfile.ApprovalStatus.APPROVED
            and obj.specialty is not None
            and obj.specialty.is_active
        ):
            actions.append("start_consultation")
        return actions


class PublicDoctorDetailSerializer(PublicDoctorListSerializer):
    """Public-facing serializer for a single doctor profile (detail)."""

    unavailable_reason = serializers.SerializerMethodField()

    class Meta:
        model = DoctorProfile
        fields = PublicDoctorListSerializer.Meta.fields + [
            "qualifications",
            "biography",
            "created_at",
            "updated_at",
            "unavailable_reason",
        ]
        read_only_fields = fields

    def get_unavailable_reason(self, obj) -> str | None:
        if not obj.user.is_active:
            return "account_inactive"
        if (
            not obj.is_approved
            or obj.approval_status != DoctorProfile.ApprovalStatus.APPROVED
        ):
            return "profile_not_approved"
        if obj.specialty is None or not obj.specialty.is_active:
            return "specialty_inactive"
        if not obj.is_accepting_consultations:
            return "not_accepting_consultations"
        return None


class DoctorAvailabilitySerializer(serializers.ModelSerializer):
    """Serializer for DoctorAvailability."""

    version = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = DoctorAvailability
        fields = [
            "id",
            "day_of_week",
            "start_time",
            "end_time",
            "is_active",
            "updated_at",
            "version",
        ]
        read_only_fields = ["id", "updated_at", "version"]

    def validate(self, attrs):
        allowed = {"day_of_week", "start_time", "end_time", "is_active"}
        incoming = set(getattr(self, "initial_data", {}).keys())
        unknown = incoming - allowed
        if unknown:
            raise serializers.ValidationError(
                {field: ["field_not_allowed"] for field in sorted(unknown)}
            )

        start_time = attrs.get(
            "start_time", getattr(self.instance, "start_time", None)
        )
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start_time is not None and end_time is not None:
            if start_time == end_time:
                raise serializers.ValidationError(
                    {"end_time": ["invalid_time_range"]}
                )
            if start_time > end_time:
                raise serializers.ValidationError(
                    {"end_time": ["unsupported_cross_midnight"]}
                )
        return attrs


class DoctorAvailabilityMutationSerializer(DoctorAvailabilitySerializer):
    """Availability write payload with optional optimistic-concurrency value."""

    expected_updated_at = serializers.DateTimeField(
        required=False, write_only=True
    )

    class Meta(DoctorAvailabilitySerializer.Meta):
        fields = DoctorAvailabilitySerializer.Meta.fields + [
            "expected_updated_at"
        ]

    def validate(self, attrs):
        expected = attrs.pop("expected_updated_at", None)
        allowed = {
            "day_of_week",
            "start_time",
            "end_time",
            "is_active",
            "expected_updated_at",
        }
        incoming = set(getattr(self, "initial_data", {}).keys())
        unknown = incoming - allowed
        if unknown:
            raise serializers.ValidationError(
                {field: ["field_not_allowed"] for field in sorted(unknown)}
            )
        start_time = attrs.get(
            "start_time", getattr(self.instance, "start_time", None)
        )
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start_time is not None and end_time is not None:
            if start_time == end_time:
                raise serializers.ValidationError(
                    {"end_time": ["invalid_time_range"]}
                )
            if start_time > end_time:
                raise serializers.ValidationError(
                    {"end_time": ["unsupported_cross_midnight"]}
                )
        attrs["expected_updated_at"] = expected
        return attrs


class DoctorAcceptingStatusSerializer(serializers.Serializer):
    """Serializer for updating the doctor's accepting-consultations status."""

    is_accepting_consultations = serializers.BooleanField(required=True)
    expected_updated_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        allowed = {"is_accepting_consultations", "expected_updated_at"}
        unknown = set(getattr(self, "initial_data", {}).keys()) - allowed
        if unknown:
            raise serializers.ValidationError(
                {field: ["field_not_allowed"] for field in sorted(unknown)}
            )
        return attrs
