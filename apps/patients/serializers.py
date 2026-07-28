import re
from datetime import date

from rest_framework import serializers

from apps.consultations.models import Consultation, ConsultationStatus
from apps.medical_records.models import RecordStatus
from apps.messaging.services import consultation_allows_messaging
from apps.patients.models import PatientProfile


class PatientProfileSerializer(serializers.ModelSerializer):
    """Serializer for the PatientProfile model."""

    class Meta:
        model = PatientProfile
        fields = [
            "id",
            "user",
            "date_of_birth",
            "gender",
            "preferred_language",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
            "blood_type",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]


class PatientProfileDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer including user info."""

    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)

    class Meta:
        model = PatientProfile
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "date_of_birth",
            "gender",
            "preferred_language",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
            "blood_type",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s-]{5,19}$")


class PatientMedicalRecordQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RecordStatus.choices, required=False)
    doctor = serializers.UUIDField(required=False)
    specialty = serializers.UUIDField(required=False)
    created_after = serializers.DateField(required=False)
    created_before = serializers.DateField(required=False)
    search = serializers.CharField(required=False, max_length=100, trim_whitespace=True)
    ordering = serializers.ChoiceField(
        choices=[
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
            "finalized_at",
            "-finalized_at",
        ],
        required=False,
    )

    def validate(self, attrs):
        if (
            attrs.get("created_after")
            and attrs.get("created_before")
            and attrs["created_after"] > attrs["created_before"]
        ):
            raise serializers.ValidationError(
                "created_after must not be later than created_before."
            )
        return attrs


class PatientMessageThreadQuerySerializer(serializers.Serializer):
    unread_only = serializers.BooleanField(required=False)
    consultation_status = serializers.ChoiceField(
        choices=ConsultationStatus.choices,
        required=False,
    )
    doctor = serializers.UUIDField(required=False)
    search = serializers.CharField(required=False, max_length=100, trim_whitespace=True)
    ordering = serializers.ChoiceField(
        choices=[
            "last_message_at",
            "-last_message_at",
            "unread_count",
            "-unread_count",
        ],
        required=False,
    )


class PatientProfileUpdateSerializer(serializers.ModelSerializer):
    """Explicit patient-owned profile fields with cross-field validation."""

    class Meta:
        model = PatientProfile
        fields = [
            "date_of_birth",
            "gender",
            "preferred_language",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
            "blood_type",
            "notes",
        ]

    def validate_date_of_birth(self, value):
        if value is None:
            return value
        today = date.today()
        if value > today:
            raise serializers.ValidationError("Date of birth cannot be in future.")
        try:
            oldest = today.replace(year=today.year - 120)
        except ValueError:
            oldest = today.replace(year=today.year - 120, day=28)
        if value < oldest:
            raise serializers.ValidationError("Date of birth is not plausible.")
        return value

    def validate_address(self, value):
        value = value.strip()
        if len(value) > 1000:
            raise serializers.ValidationError("Address exceeds 1000 characters.")
        return value

    def validate_notes(self, value):
        value = value.strip()
        if len(value) > 2000:
            raise serializers.ValidationError("Notes exceed 2000 characters.")
        return value

    def validate_emergency_contact_name(self, value):
        value = value.strip()
        if value and len(value) < 2:
            raise serializers.ValidationError("Enter at least 2 characters.")
        return value

    def validate_emergency_contact_phone(self, value):
        value = value.strip()
        if value and not PHONE_PATTERN.fullmatch(value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value.replace(" ", "").replace("-", "")

    def validate(self, attrs):
        name = attrs.get(
            "emergency_contact_name",
            self.instance.emergency_contact_name if self.instance else "",
        )
        phone = attrs.get(
            "emergency_contact_phone",
            self.instance.emergency_contact_phone if self.instance else "",
        )
        if bool(name) != bool(phone):
            raise serializers.ValidationError({
                "emergency_contact": (
                    "Emergency contact name and phone must be provided together."
                )
            })
        return attrs


class PatientProfileCompositeSerializer(serializers.Serializer):
    """Patient-safe account, profile, and completion contract."""

    def to_representation(self, profile):
        user = profile.user
        return {
            "account": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "date_joined": user.date_joined,
                "updated_at": user.updated_at,
            },
            "profile": {
                "id": profile.id,
                "date_of_birth": profile.date_of_birth,
                "gender": profile.gender,
                "preferred_language": profile.preferred_language,
                "address": profile.address,
                "emergency_contact_name": profile.emergency_contact_name,
                "emergency_contact_phone": profile.emergency_contact_phone,
                "blood_type": profile.blood_type,
                "notes": profile.notes,
                "created_at": profile.created_at,
                "updated_at": profile.updated_at,
            },
            "completion": self.context["completion"],
            "generated_at": self.context["generated_at"],
        }


class PatientMessageThreadSerializer(serializers.ModelSerializer):
    consultation_id = serializers.UUIDField(source="id", read_only=True)
    consultation_status = serializers.CharField(source="status", read_only=True)
    doctor = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    messaging_available = serializers.SerializerMethodField()
    unavailable_reason = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(read_only=True)
    last_message_at = serializers.DateTimeField(read_only=True)
    last_message_sender_role = serializers.CharField(read_only=True)

    def get_doctor(self, obj):
        return {
            "id": obj.doctor_id,
            "full_name": obj.doctor.user.full_name,
            "specialty_name": obj.specialty.name if obj.specialty else None,
        }

    def get_last_message_preview(self, obj):
        content = (obj.last_message_content or "").strip()
        return content[:117] + "..." if len(content) > 120 else content

    def get_messaging_available(self, obj):
        return consultation_allows_messaging(obj)

    def get_unavailable_reason(self, obj):
        return None if consultation_allows_messaging(obj) else "conversation_closed"

    def get_available_actions(self, obj):
        return ["open"]

    class Meta:
        model = Consultation
        fields = [
            "consultation_id",
            "consultation_status",
            "doctor",
            "unread_count",
            "last_message_at",
            "last_message_preview",
            "last_message_sender_role",
            "messaging_available",
            "unavailable_reason",
            "available_actions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
