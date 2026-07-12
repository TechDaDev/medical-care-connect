from rest_framework import serializers

from apps.medical_records.models import MedicalRecordDraft


class MedicalRecordDraftSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalRecordDraft
        read_only_fields = [
            "id", "consultation", "intake_session", "status",
            "created_at", "updated_at", "finalized_at",
        ]
        fields = [
            "id",
            "consultation",
            "intake_session",
            "status",
            "chief_complaint",
            "history_of_present_illness",
            "symptoms",
            "severity",
            "onset_date",
            "duration",
            "location",
            "triggers",
            "relieving_factors",
            "past_medical_history",
            "medications",
            "allergies",
            "family_history",
            "social_history",
            "review_of_systems",
            "additional_notes",
            "doctor_notes",
            "finalized_at",
            "created_at",
            "updated_at",
        ]


class MedicalRecordDraftUpdateSerializer(serializers.ModelSerializer):
    """Doctor-only updates to the draft record."""

    class Meta:
        model = MedicalRecordDraft
        fields = [
            "chief_complaint",
            "history_of_present_illness",
            "symptoms",
            "severity",
            "onset_date",
            "duration",
            "location",
            "triggers",
            "relieving_factors",
            "past_medical_history",
            "medications",
            "allergies",
            "family_history",
            "social_history",
            "review_of_systems",
            "additional_notes",
            "doctor_notes",
        ]


class RecordConfirmSerializer(serializers.Serializer):
    confirmed = serializers.BooleanField(required=True)
