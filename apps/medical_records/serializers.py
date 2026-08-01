from rest_framework import serializers

from apps.consultations.models import ConsultationStatus
from apps.medical_records.doctor_services import (
    DOCTOR_AUTHORED_FIELDS,
    validate_record_for_finalization,
)
from apps.medical_records.models import ClinicalOutcome, MedicalRecordDraft, RecordStatus


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
            "clinical_summary", "assessment", "working_diagnosis",
            "recommendations", "treatment_plan", "follow_up_plan",
            "physical_visit_reason", "warning_signs", "patient_instructions",
            "finalized_at", "created_at", "updated_at",
        ]
        read_only_fields = fields


class PatientMedicalRecordListSerializer(serializers.ModelSerializer):
    consultation_id = serializers.UUIDField(read_only=True)
    doctor = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
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


class DoctorMedicalRecordQuerySerializer(serializers.Serializer):
    record_status = serializers.ChoiceField(
        choices=RecordStatus.choices, required=False
    )
    consultation_status = serializers.ChoiceField(
        choices=ConsultationStatus.choices, required=False
    )
    patient = serializers.UUIDField(required=False)
    specialty = serializers.UUIDField(required=False)
    needs_doctor_action = serializers.BooleanField(required=False)
    created_after = serializers.DateField(required=False)
    created_before = serializers.DateField(required=False)
    updated_after = serializers.DateField(required=False)
    search = serializers.CharField(required=False, max_length=100, trim_whitespace=True)
    ordering = serializers.ChoiceField(
        choices=("updated_at", "-updated_at", "created_at", "-created_at", "status"),
        required=False,
    )


class DoctorMedicalRecordListSerializer(serializers.ModelSerializer):
    consultation_id = serializers.UUIDField(read_only=True)
    patient = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    record_status = serializers.CharField(source="status", read_only=True)
    consultation_status = serializers.CharField(
        source="consultation.status", read_only=True
    )
    needs_doctor_action = serializers.SerializerMethodField()
    completion_blocked_reason = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()

    def get_patient(self, obj):
        return {
            "id": obj.consultation.patient_id,
            "display_name": obj.consultation.patient.user.full_name,
        }

    def get_specialty(self, obj):
        specialty = obj.consultation.specialty
        return None if specialty is None else {"id": specialty.id, "name": specialty.name}

    def get_needs_doctor_action(self, obj):
        return obj.status == RecordStatus.DRAFT

    def get_completion_blocked_reason(self, obj):
        return "medical_record_not_finalized" if obj.status == RecordStatus.DRAFT else None

    def get_available_actions(self, obj):
        actions = ["view", "open_consultation"]
        if obj.status == RecordStatus.DRAFT:
            actions.extend(["edit", "finalize"])
        return actions

    class Meta:
        model = MedicalRecordDraft
        fields = [
            "id", "consultation_id", "patient", "specialty", "record_status",
            "consultation_status", "created_at", "updated_at", "finalized_at",
            "needs_doctor_action", "completion_blocked_reason", "available_actions",
        ]
        read_only_fields = fields


class DoctorMedicalRecordDetailSerializer(serializers.ModelSerializer):
    consultation_id = serializers.UUIDField(read_only=True)
    record_status = serializers.CharField(source="status", read_only=True)
    patient = serializers.SerializerMethodField()
    consultation = serializers.SerializerMethodField()
    patient_reported = serializers.SerializerMethodField()
    intake_reference = serializers.SerializerMethodField()
    doctor_authored = serializers.SerializerMethodField()
    ai_suggestions = serializers.SerializerMethodField()
    validation = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()
    action_reasons = serializers.SerializerMethodField()
    finalized_by = serializers.SerializerMethodField()

    def get_patient(self, obj):
        patient = obj.consultation.patient
        return {
            "id": patient.id,
            "display_name": patient.user.full_name,
            "date_of_birth": patient.date_of_birth,
            "gender": patient.gender or None,
            "preferred_language": patient.preferred_language or None,
            "blood_type": patient.blood_type or None,
        }

    def get_consultation(self, obj):
        consultation = obj.consultation
        return {
            "status": consultation.status,
            "priority": consultation.priority,
            "specialty_name": consultation.specialty.name if consultation.specialty else None,
            "description": consultation.description,
            "created_at": consultation.created_at,
            "updated_at": consultation.updated_at,
        }

    def get_patient_reported(self, obj):
        return {
            "reported_concern": obj.chief_complaint or None,
            "symptoms": obj.symptoms,
            "duration": obj.duration or None,
            "severity": obj.severity,
            "chronic_conditions": obj.past_medical_history or None,
            "current_medications": obj.medications,
            "allergies": obj.allergies,
            "family_history": obj.family_history or None,
            "additional_information": obj.additional_notes or None,
        }

    def get_intake_reference(self, obj):
        intake = obj.intake_session
        return {
            "exists": intake is not None,
            "is_complete": bool(intake and intake.status in {"ready_for_review", "confirmed"}),
            "emergency_detected": bool(intake and intake.emergency_detected),
            "summary_available": bool(intake and intake.collected_data),
            "action_path": (
                f"/app/doctor/consultations/{obj.consultation_id}#intake" if intake else None
            ),
        }

    def get_doctor_authored(self, obj):
        return {field: getattr(obj, field) for field in DOCTOR_AUTHORED_FIELDS}

    def get_ai_suggestions(self, obj):
        return {
            "available": False,
            "fields": None,
            "generated_at": None,
            "disclaimer_key": "doctorMedicalRecords.aiUnavailable",
        }

    def get_validation(self, obj):
        value = validate_record_for_finalization(obj)
        return {
            "can_finalize": value.can_finalize,
            "missing_fields": value.missing_fields,
            "warnings": value.warnings,
            "blocking_errors": value.blocking_errors,
        }

    def get_actions(self, obj):
        editable = obj.status == RecordStatus.DRAFT
        validation = validate_record_for_finalization(obj)
        consultation_open = obj.consultation.status not in {
            ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED
        }
        return {
            "can_edit": editable and consultation_open,
            "can_finalize": validation.can_finalize,
            "can_amend": False,
            "can_print": obj.status == RecordStatus.FINALIZED,
            "can_complete_consultation": obj.status == RecordStatus.FINALIZED,
            "can_require_follow_up": obj.status == RecordStatus.FINALIZED,
            "can_require_physical_visit": obj.status == RecordStatus.FINALIZED,
        }

    def get_action_reasons(self, obj):
        return {
            "edit": None if obj.status == RecordStatus.DRAFT else "medical_record_finalized",
            "finalize": None if validate_record_for_finalization(obj).can_finalize else "record_incomplete",
            "amend": "amendment_not_supported",
            "complete_consultation": (
                None if obj.status == RecordStatus.FINALIZED else "medical_record_not_finalized"
            ),
        }

    def get_finalized_by(self, obj):
        if obj.finalized_by is None:
            return None
        return {"id": obj.finalized_by_id, "display_name": obj.finalized_by.full_name}

    class Meta:
        model = MedicalRecordDraft
        fields = [
            "id", "consultation_id", "record_status", "version", "patient",
            "consultation", "patient_reported", "intake_reference", "doctor_authored",
            "ai_suggestions", "validation", "actions", "action_reasons", "provenance",
            "clinical_outcome", "outcome_recorded_at", "created_at", "updated_at",
            "finalized_at", "finalized_by",
        ]
        read_only_fields = fields


class CreateMedicalRecordSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField()


class DoctorAuthoredFieldsSerializer(serializers.Serializer):
    clinical_summary = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    assessment = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    working_diagnosis = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    differential_considerations = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    recommendations = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    treatment_plan = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    follow_up_plan = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    physical_visit_reason = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    warning_signs = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    patient_instructions = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    doctor_notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)

    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "field_not_editable" for field in sorted(unknown)}
            )
        return super().to_internal_value(data)


class UpdateDoctorMedicalRecordSerializer(serializers.Serializer):
    doctor_authored = DoctorAuthoredFieldsSerializer()
    expected_version = serializers.IntegerField(min_value=1)
    client_request_id = serializers.UUIDField()


class FinalizeDoctorMedicalRecordSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    client_request_id = serializers.UUIDField()
    confirmation = serializers.BooleanField()


class ClinicalOutcomeSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=ClinicalOutcome.choices)
    medical_record_id = serializers.UUIDField()
    confirmation = serializers.BooleanField()
