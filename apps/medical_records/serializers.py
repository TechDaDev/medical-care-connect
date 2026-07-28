from rest_framework import serializers

from apps.medical_records.models import MedicalRecordDraft


class MedicalRecordDraftSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalRecordDraft
        fields = [
            "id", "consultation", "intake_session", "status",
            "chief_complaint", "history_of_present_illness", "symptoms",
            "severity", "onset_date", "duration", "location", "triggers",
            "relieving_factors", "past_medical_history", "medications",
            "allergies", "family_history", "social_history",
            "review_of_systems", "additional_notes", "doctor_notes",
            "finalized_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "consultation", "intake_session", "status",
            "created_at", "updated_at", "finalized_at",
        ]


class PatientMedicalRecordSerializer(serializers.ModelSerializer):
    """Patient-safe record; excludes doctor notes and intake/provider internals."""

    consultation_id = serializers.UUIDField(read_only=True)
    doctor = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()

    def get_doctor(self, obj):
        return {
            "id": obj.consultation.doctor_id,
            "full_name": obj.consultation.doctor.user.full_name,
            "specialty_name": (
                obj.consultation.specialty.name
                if obj.consultation.specialty
                else None
            ),
        }

    def get_specialty(self, obj):
        specialty = obj.consultation.specialty
        if specialty is None:
            return None
        return {"id": specialty.id, "name": specialty.name}

    class Meta:
        model = MedicalRecordDraft
        fields = [
            "id", "consultation_id", "doctor", "specialty",
            "status", "chief_complaint",
            "history_of_present_illness", "symptoms", "severity", "onset_date",
            "duration", "location", "triggers", "relieving_factors",
            "past_medical_history", "medications", "allergies",
            "family_history", "social_history", "review_of_systems",
            "finalized_at", "created_at", "updated_at",
        ]
        read_only_fields = fields


class PatientMedicalRecordListSerializer(serializers.ModelSerializer):
    consultation_id = serializers.UUIDField(read_only=True)
    doctor = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    chief_complaint_summary = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()

    def get_doctor(self, obj):
        return {
            "id": obj.consultation.doctor_id,
            "full_name": obj.consultation.doctor.user.full_name,
            "specialty_name": (
                obj.consultation.specialty.name
                if obj.consultation.specialty
                else None
            ),
        }

    def get_specialty(self, obj):
        specialty = obj.consultation.specialty
        return None if specialty is None else {
            "id": specialty.id,
            "name": specialty.name,
        }

    def get_chief_complaint_summary(self, obj):
        complaint = obj.chief_complaint.strip()
        return complaint[:157] + "..." if len(complaint) > 160 else complaint

    def get_available_actions(self, obj):
        return ["view"]

    class Meta:
        model = MedicalRecordDraft
        fields = [
            "id",
            "consultation_id",
            "doctor",
            "specialty",
            "status",
            "chief_complaint_summary",
            "finalized_at",
            "created_at",
            "updated_at",
            "available_actions",
        ]
        read_only_fields = fields


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
