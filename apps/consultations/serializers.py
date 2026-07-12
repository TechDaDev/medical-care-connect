from rest_framework import serializers

from apps.consultations.models import Consultation


class ConsultationSerializer(serializers.ModelSerializer):
    """Serializer for Consultation create/update."""

    patient_name = serializers.CharField(
        source="patient.user.full_name", read_only=True, default=None
    )
    doctor_name = serializers.CharField(
        source="doctor.user.full_name", read_only=True, default=None
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
            "patient",
            "patient_name",
            "doctor",
            "doctor_name",
            "specialty",
            "specialty_name",
            "status",
            "status_display",
            "priority",
            "priority_display",
            "description",
            "cancellation_reason",
            "submitted_at",
            "accepted_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "patient",
            "patient_name",
            "doctor_name",
            "specialty_name",
            "status",
            "status_display",
            "priority_display",
            "cancellation_reason",
            "submitted_at",
            "accepted_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]


class ConsultationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new consultation."""

    class Meta:
        model = Consultation
        fields = [
            "doctor",
            "specialty",
            "priority",
            "description",
        ]

    def validate_doctor(self, value):
        if not value.is_approved:
            raise serializers.ValidationError(
                "This doctor is not approved to receive consultations."
            )
        if not value.is_accepting_consultations:
            raise serializers.ValidationError(
                "This doctor is not currently accepting consultations."
            )
        if not value.user.is_active:
            raise serializers.ValidationError(
                "This doctor account is not active."
            )
        return value


class ConsultationCancelSerializer(serializers.Serializer):
    """Serializer for cancelling a consultation."""

    cancellation_reason = serializers.CharField(required=True, min_length=1)
