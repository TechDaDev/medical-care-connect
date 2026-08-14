"""Doctor-only consultation contracts. Keep patient/staff serializers isolated."""

from datetime import date

from django.utils import timezone
from rest_framework import serializers

from apps.ai_intake.models import AIIntakeSession
from apps.attachments.choices import AttachmentStatus, ScanStatus
from apps.consultations.doctor_actions import doctor_action_policy
from apps.consultations.models import Consultation, ConsultationStatus
from apps.consultations.timeline import build_doctor_timeline
from apps.medical_records.models import ClinicalOutcome
from apps.medical_records.doctor_services import CREATE_ALLOWED_STATUSES


def _localized_specialty(specialty, request) -> dict | None:
    if specialty is None:
        return None
    language = request.headers.get("Accept-Language", "en").split(",")[0].lower()
    if language.startswith("ar"):
        name = specialty.name_ar or specialty.name
    elif language.startswith("ckb") or language.startswith("ku"):
        name = specialty.name_ckb or specialty.name
    else:
        name = specialty.name_en or specialty.name
    return {"id": specialty.id, "name": name}


def _age(date_of_birth) -> int | None:
    if not date_of_birth:
        return None
    today = date.today()
    return today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )


def _age_group(value: int | None) -> str | None:
    if value is None:
        return None
    if value < 13:
        return "child"
    if value < 18:
        return "adolescent"
    if value < 65:
        return "adult"
    return "older_adult"


class DoctorConsultationQueueSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    unread_messages = serializers.IntegerField(read_only=True)
    needs_doctor_action = serializers.SerializerMethodField()
    doctor_action_type = serializers.SerializerMethodField()
    has_completed_intake = serializers.SerializerMethodField()
    has_medical_record = serializers.SerializerMethodField()
    attachment_count = serializers.IntegerField(read_only=True)
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = Consultation
        fields = [
            "id", "status", "priority", "patient", "specialty",
            "created_at", "updated_at", "submitted_at", "accepted_at",
            "unread_messages", "needs_doctor_action", "doctor_action_type",
            "has_completed_intake", "has_medical_record", "attachment_count",
            "available_actions",
        ]
        read_only_fields = fields

    def _policy(self, obj):
        cache = getattr(obj, "_doctor_policy_cache", None)
        if cache is None:
            cache = doctor_action_policy(obj, self.context["doctor"])
            obj._doctor_policy_cache = cache
        return cache

    def get_patient(self, obj):
        age = _age(obj.patient.date_of_birth)
        return {
            "id": obj.patient_id,
            "display_name": obj.patient.user.full_name,
            "age_group": _age_group(age),
            "gender": obj.patient.gender or None,
        }

    def get_specialty(self, obj):
        return _localized_specialty(obj.specialty, self.context["request"])

    def get_needs_doctor_action(self, obj):
        return self._policy(obj).needs_doctor_action or obj.unread_messages > 0

    def get_doctor_action_type(self, obj):
        return self._policy(obj).doctor_action_type or (
            "reply_to_patient" if obj.unread_messages > 0 else None
        )

    def get_has_completed_intake(self, obj):
        try:
            return obj.intake_session.status in {
                "awaiting_patient_review",
                "correction_in_progress",
                "confirmed",
                "submitted_to_doctor",
            }
        except (AttributeError, AIIntakeSession.DoesNotExist):
            return False

    def get_has_medical_record(self, obj):
        try:
            return obj.medical_record is not None
        except AttributeError:
            return False

    def get_available_actions(self, obj):
        return self._policy(obj).available_actions


class DoctorConsultationDetailSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()
    action_reasons = serializers.SerializerMethodField()
    intake = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    internal_notes = serializers.SerializerMethodField()
    medical_record = serializers.SerializerMethodField()
    generated_at = serializers.SerializerMethodField()

    class Meta:
        model = Consultation
        fields = [
            "id", "status", "priority", "patient", "specialty", "description",
            "created_at", "updated_at", "submitted_at", "accepted_at",
            "completed_at", "cancelled_at", "timeline", "actions",
            "action_reasons", "intake", "messages", "attachments",
            "internal_notes", "medical_record", "generated_at",
        ]
        read_only_fields = fields

    def _policy(self, obj):
        return doctor_action_policy(obj, self.context["doctor"])

    def get_patient(self, obj):
        patient = obj.patient
        return {
            "id": patient.id,
            "display_name": patient.user.full_name,
            "date_of_birth": patient.date_of_birth,
            "age": _age(patient.date_of_birth),
            "gender": patient.gender or None,
            "preferred_language": patient.preferred_language or None,
            "blood_type": patient.blood_type or None,
        }

    def get_specialty(self, obj):
        return _localized_specialty(obj.specialty, self.context["request"])

    def get_timeline(self, obj):
        return build_doctor_timeline(obj)

    def get_actions(self, obj):
        return self._policy(obj).actions

    def get_action_reasons(self, obj):
        return self._policy(obj).reasons

    def get_intake(self, obj):
        try:
            session = obj.intake_session
        except (AttributeError, AIIntakeSession.DoesNotExist):
            session = None
        if session is None:
            return {
                "exists": False, "status": None, "question_count": 0,
                "answered_count": 0, "is_complete": False,
                "emergency_detected": False, "completed_at": None,
                "doctor_safe_summary": None,
            }
        answered = getattr(session, "doctor_answered_count", None)
        if answered is None:
            answered = session.messages.filter(role="patient").count()
        return {
            "exists": True,
            "status": session.status,
            "question_count": session.question_count,
            "answered_count": answered,
            "is_complete": session.status in {
                "awaiting_patient_review", "confirmed", "submitted_to_doctor"
            },
            "emergency_detected": session.emergency_detected,
            "completed_at": session.completed_at,
            "doctor_safe_summary": _doctor_safe_summary(session.collected_data),
        }

    def get_messages(self, obj):
        return {
            "unread_count": getattr(obj, "unread_messages", 0),
            "last_message_at": getattr(obj, "last_message_at", None),
            "patient_awaiting_response": (
                obj.status == ConsultationStatus.AWAITING_DOCTOR_RESPONSE
            ),
        }

    def get_attachments(self, obj):
        return {
            "total": getattr(obj, "attachment_total", 0),
            "available": getattr(obj, "attachment_available", 0),
            "pending_scan": getattr(obj, "attachment_pending", 0),
            "quarantined": getattr(obj, "attachment_quarantined", 0),
            "rejected": getattr(obj, "attachment_rejected", 0),
            "can_upload": self._policy(obj).actions["can_upload_attachment"],
            "upload_unavailable_reason": self._policy(obj).reasons["attachment"],
        }

    def get_internal_notes(self, obj):
        return {
            "count": getattr(obj, "internal_note_count", 0),
            "latest_at": getattr(obj, "latest_internal_note_at", None),
        }

    def get_medical_record(self, obj):
        try:
            record = obj.medical_record
        except AttributeError:
            record = None
        return {
            "exists": record is not None,
            "id": record.id if record else None,
            "status": record.status if record else None,
            "can_view_summary": self._policy(obj).actions["can_view_record_summary"],
            "can_create_record": record is None and obj.status in CREATE_ALLOWED_STATUSES,
            "action_path": (
                f"/app/doctor/medical-records/{record.id}"
                if record
                else f"/app/doctor/consultations/{obj.id}/medical-record"
            ),
        }

    def get_generated_at(self, obj):
        return timezone.now()


def _doctor_safe_summary(data) -> dict | None:
    if not isinstance(data, dict) or not data:
        return None
    return {
        "reported_concern": data.get("chief_complaint"),
        "symptoms": data.get("symptoms") or [],
        "duration": data.get("symptom_duration"),
        "severity": data.get("severity"),
        "medications": data.get("current_medications") or [],
        "allergies": data.get("allergies") or [],
        "history": {
            "chronic_conditions": data.get("chronic_conditions") or [],
            "surgical_history": data.get("surgical_history") or [],
            "family_history": data.get("family_history") or [],
        },
    }


class DoctorIntakeSerializer(serializers.ModelSerializer):
    """Doctor-safe intake projection.

    Shows patient-confirmed structured data, original answers, provenance,
    uncertainty, missing/non-blocking information, emergency state, version
    metadata, and an explicit AI-assisted disclaimer.  Never exposes hidden
    prompts, provider credentials, raw provider responses, or chain-of-thought.
    """

    session_id = serializers.UUIDField(source="id", read_only=True)
    consultation_id = serializers.UUIDField(read_only=True)
    answered_count = serializers.SerializerMethodField()
    patient_answers = serializers.SerializerMethodField()
    doctor_safe_summary = serializers.SerializerMethodField()
    field_projection = serializers.SerializerMethodField()
    patient_confirmed = serializers.SerializerMethodField()
    ai_assisted = serializers.SerializerMethodField()
    uncertainty_fields = serializers.SerializerMethodField()
    missing_non_blocking = serializers.SerializerMethodField()
    can_begin_review = serializers.SerializerMethodField()
    patient = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    consultation_status = serializers.CharField(source="consultation.status", read_only=True)
    ai_disclaimer_key = serializers.SerializerMethodField()
    structured_fields = serializers.SerializerMethodField()
    missing_blocking_fields = serializers.SerializerMethodField()
    missing_non_blocking_fields = serializers.SerializerMethodField()
    uncertain_fields = serializers.SerializerMethodField()
    unknown_fields = serializers.SerializerMethodField()
    declined_fields = serializers.SerializerMethodField()
    emergency = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    medical_record = serializers.SerializerMethodField()

    class Meta:
        model = AIIntakeSession
        fields = [
            "session_id", "consultation_id", "status", "started_at", "completed_at",
            "confirmed_at", "submitted_at", "question_count", "answered_count",
            "language", "prompt_version", "schema_version",
            "emergency_detected", "emergency_level",
            "patient_confirmed", "ai_assisted",
            "patient_answers", "doctor_safe_summary", "field_projection",
            "missing_fields", "uncertainty_fields", "missing_non_blocking",
            "can_begin_review",
            "patient", "specialty", "consultation_status", "ai_disclaimer_key",
            "structured_fields", "missing_blocking_fields",
            "missing_non_blocking_fields", "uncertain_fields", "unknown_fields",
            "declined_fields", "emergency", "messages", "medical_record",
        ]
        read_only_fields = fields

    def get_answered_count(self, obj):
        return sum(message.role == "patient" for message in obj.messages.all())

    def get_patient_answers(self, obj):
        question = ""
        answers = []
        for message in obj.messages.all():
            if message.role == "assistant":
                question = message.content
            elif message.role == "patient":
                answers.append({
                    "id": message.id,
                    "question_label": question,
                    "answer": message.content,
                    "created_at": message.created_at,
                })
        return answers

    def get_doctor_safe_summary(self, obj):
        return _doctor_safe_summary(obj.collected_data)

    def get_patient_confirmed(self, obj):
        return obj.status in {"confirmed", "submitted_to_doctor"}

    def get_ai_assisted(self, obj):
        # Always AI-assisted: displayed as a disclaimer, never as doctor-authored.
        return True

    def get_uncertainty_fields(self, obj):
        metadata = obj.field_metadata or {}
        return sorted(
            name for name, entry in metadata.items()
            if (entry or {}).get("status") == "uncertain"
        )

    def get_missing_non_blocking(self, obj):
        try:
            from apps.ai_intake.services.completeness import evaluate_completeness
            return evaluate_completeness(obj).missing_non_blocking_fields
        except Exception:
            return []

    def get_field_projection(self, obj):
        """Structured per-field values with status/source/provenance."""
        metadata = obj.field_metadata or {}
        projection = {}
        safe_message_ids = {
            str(message.id) for message in obj.messages.all()
            if message.role in {"patient", "assistant"}
        }
        for name, entry in metadata.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("status") not in {
                "answered", "unknown", "declined", "uncertain", "not_applicable",
            }:
                continue
            projection[name] = {
                "value": entry.get("value"),
                "status": entry.get("status"),
                "source": entry.get("source"),
                "confirmed_by_patient": entry.get("confirmed_by_patient", False),
                "evidence_message_ids": [
                    str(message_id) for message_id in entry.get("evidence_message_ids", [])
                    if str(message_id) in safe_message_ids
                ],
            }
        return projection

    def get_can_begin_review(self, obj):
        policy = doctor_action_policy(obj.consultation, self.context["doctor"])
        return policy.actions["can_begin_review"]

    def get_patient(self, obj):
        patient = obj.consultation.patient
        return {"id": patient.id, "display_name": patient.user.full_name}

    def get_specialty(self, obj):
        specialty = obj.consultation.specialty
        if specialty is None:
            return None
        language = "ckb" if obj.language in {"ckb", "ku"} else obj.language
        name = getattr(specialty, f"name_{language}", "") or specialty.name
        return {"id": specialty.id, "name": name}

    def get_ai_disclaimer_key(self, obj):
        return "ai_intake.not_clinically_verified"

    def get_structured_fields(self, obj):
        return [
            {"field": name, "display_value": entry["value"], **{
                key: entry[key] for key in (
                    "status", "source", "confirmed_by_patient", "evidence_message_ids"
                )
            }}
            for name, entry in self.get_field_projection(obj).items()
        ]

    def get_missing_blocking_fields(self, obj):
        return list(obj.missing_fields or [])

    def get_missing_non_blocking_fields(self, obj):
        return self.get_missing_non_blocking(obj)

    def _fields_with_status(self, obj, status_value):
        return sorted(
            name for name, entry in (obj.field_metadata or {}).items()
            if isinstance(entry, dict) and entry.get("status") == status_value
        )

    def get_uncertain_fields(self, obj):
        return self._fields_with_status(obj, "uncertain")

    def get_unknown_fields(self, obj):
        return self._fields_with_status(obj, "unknown")

    def get_declined_fields(self, obj):
        return self._fields_with_status(obj, "declined")

    def get_emergency(self, obj):
        return {
            "detected": obj.emergency_detected,
            "level": obj.emergency_level,
            "reason_codes": list(obj.emergency_reasons or []),
            "escalated_at": obj.emergency_escalated_at,
            "normal_intake_stopped": obj.status == "emergency_stopped",
            "emergency_services_contacted": False,
            "clinician_review_status": "unreviewed",
        }

    def get_messages(self, obj):
        messages = [
            message for message in obj.messages.all()
            if message.role in {"patient", "assistant"}
        ][-40:]
        return [{
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "sequence_number": message.sequence_number,
            "created_at": message.created_at,
        } for message in messages]

    def get_medical_record(self, obj):
        try:
            record = obj.consultation.medical_record
        except AttributeError:
            record = None
        if record is not None:
            return {
                "exists": True,
                "id": str(record.id),
                "status": record.status,
                "action_path": f"/app/doctor/medical-records/{record.id}",
                "unavailable_reason": None,
            }
        reason = (
            "intake_not_submitted"
            if obj.status != "submitted_to_doctor"
            else "draft_not_available"
        )
        return {
            "exists": False, "id": None, "status": None,
            "action_path": None, "unavailable_reason": reason,
        }


class DoctorAcceptSerializer(serializers.Serializer):
    expected_status = serializers.ChoiceField(
        choices=ConsultationStatus.choices,
        default=ConsultationStatus.SUBMITTED,
    )
    expected_updated_at = serializers.DateTimeField(required=False, allow_null=True)
    client_request_id = serializers.UUIDField()


class DoctorTransitionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=[
        "begin_review", "request_patient_response", "mark_awaiting_doctor",
        "require_follow_up", "require_physical_visit", "transfer", "complete",
        "emergency_escalate",
    ])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    target_doctor_id = serializers.UUIDField(required=False, allow_null=True)
    expected_status = serializers.ChoiceField(choices=ConsultationStatus.choices)
    expected_updated_at = serializers.DateTimeField(required=False, allow_null=True)
    client_request_id = serializers.UUIDField()
    outcome = serializers.ChoiceField(choices=ClinicalOutcome.choices, required=False)
    medical_record_id = serializers.UUIDField(required=False)
    confirmation = serializers.BooleanField(required=False)
