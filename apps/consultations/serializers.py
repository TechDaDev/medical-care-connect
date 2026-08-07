import re

from rest_framework import serializers

from apps.consultations.models import Consultation, ConsultationStatus, Priority


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


class ConsultationCreateSerializer(serializers.Serializer):
    """Strict patient consultation-creation input."""

    doctor = serializers.UUIDField()
    description = serializers.CharField(
        trim_whitespace=False,
        max_length=2000,
    )
    client_request_id = serializers.UUIDField()
    expected_doctor_updated_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
    )
    specialty = serializers.UUIDField(required=False, allow_null=True)
    priority = serializers.ChoiceField(
        required=False,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )

    def validate_description(self, value: str) -> str:
        normalized = re.sub(r"\s+", " ", value).strip()
        meaningful = [character for character in normalized if character.isalnum()]
        if len(meaningful) < 20:
            raise serializers.ValidationError(
                "description_too_short",
                code="description_too_short",
            )
        if len({character.casefold() for character in meaningful}) <= 2:
            raise serializers.ValidationError(
                "description_not_meaningful",
                code="description_not_meaningful",
            )
        return normalized

    def validate(self, attrs):
        allowed = set(self.fields)
        unknown = set(self.initial_data) - allowed
        if unknown:
            raise serializers.ValidationError(
                {
                    field: ["unknown_field"]
                    for field in sorted(unknown)
                }
            )
        return attrs


class ConsultationCreateResponseSerializer(serializers.ModelSerializer):
    """Safe authoritative consultation-creation response."""

    doctor = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    next_path = serializers.SerializerMethodField()

    class Meta:
        model = Consultation
        fields = [
            "id",
            "status",
            "doctor",
            "specialty",
            "created_at",
            "submitted_at",
            "next_path",
        ]
        read_only_fields = fields

    def get_doctor(self, obj) -> dict:
        return {
            "id": obj.doctor_id,
            "full_name": obj.doctor.user.full_name,
        }

    def get_specialty(self, obj) -> dict | None:
        if obj.specialty is None:
            return None
        request = self.context.get("request")
        locale = ""
        if request is not None:
            locale = request.headers.get("Accept-Language", "").split(",")[0]
        locale = locale.lower().split("-")[0]
        if locale == "ar":
            name = obj.specialty.name_ar or obj.specialty.name
        elif locale == "ckb":
            name = obj.specialty.name_ckb or obj.specialty.name
        else:
            name = obj.specialty.name_en or obj.specialty.name
        return {
            "id": obj.specialty_id,
            "name": name,
        }

    def get_next_path(self, obj) -> str:
        return f"/app/patient/consultations/{obj.id}"


class ConsultationCancelSerializer(serializers.Serializer):
    """Serializer for cancelling a consultation."""

    reason = serializers.CharField(
        required=False, trim_whitespace=True, min_length=10, max_length=500
    )
    cancellation_reason = serializers.CharField(
        required=False, trim_whitespace=True, min_length=10, max_length=500
    )
    expected_status = serializers.ChoiceField(
        choices=ConsultationStatus.choices, required=False
    )

    def validate(self, attrs):
        reason = attrs.get("reason") or attrs.get("cancellation_reason")
        if not reason:
            raise serializers.ValidationError(
                {"reason": ["cancellation_reason_required"]}
            )
        attrs["reason"] = re.sub(r"\s+", " ", reason).strip()
        return attrs


class ConsultationDetailSerializer(serializers.ModelSerializer):
    """Full consultation detail with computed action flags."""

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
    actions = serializers.SerializerMethodField()
    has_intake_session = serializers.SerializerMethodField()
    has_medical_record = serializers.SerializerMethodField()

    class Meta:
        model = Consultation
        fields = [
            "id",
            "patient",
            "patient_name",
            "patient_email",
            "doctor",
            "doctor_name",
            "doctor_email",
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
            "actions",
            "has_intake_session",
            "has_medical_record",
        ]
        read_only_fields = fields

    def get_actions(self, obj):
        request = self.context.get("request")
        if not request:
            return {}
        user = request.user
        is_patient = hasattr(user, "patient_profile") and obj.patient == user.patient_profile
        is_doctor = hasattr(user, "doctor_profile") and obj.doctor == user.doctor_profile
        is_participant = is_patient or is_doctor
        is_staff = user.role in ("coordinator", "administrator")
        terminal = (ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED)
        active = obj.status not in terminal
        return {
            "can_accept": bool(is_doctor and obj.status == ConsultationStatus.SUBMITTED),
            "can_cancel": bool(active and (is_participant or is_staff)),
            "can_message": bool(
                active
                and obj.status not in (
                    ConsultationStatus.COMPLETED,
                    ConsultationStatus.CANCELLED,
                    ConsultationStatus.EMERGENCY_ESCALATED,
                )
                and (is_participant or is_staff)
            ),
            "can_start_intake": bool(
                is_patient and obj.status == ConsultationStatus.ACCEPTED
            ),
            "can_view_record": bool(is_participant or is_staff),
            "can_add_internal_note": bool(is_doctor),
            "can_transfer": bool(is_staff and obj.status not in terminal),
            "can_change_priority": bool(is_staff and obj.status not in terminal),
        }

    def get_has_intake_session(self, obj):
        return hasattr(obj, "intake_session") and obj.intake_session is not None

    def get_has_medical_record(self, obj):
        return (
            hasattr(obj, "medical_record")
            and obj.medical_record is not None
        )


def _localized_specialty_name(specialty, request) -> str:
    if specialty is None:
        return ""
    language = (
        request.headers.get("Accept-Language", "en").split(",")[0].split("-")[0]
        if request
        else "en"
    )
    if language == "ar":
        return specialty.name_ar or specialty.name
    if language in {"ckb", "ku"}:
        return specialty.name_ckb or specialty.name
    return specialty.name_en or specialty.name


class PatientConsultationListSerializer(serializers.ModelSerializer):
    doctor = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    unread_messages = serializers.IntegerField(read_only=True, default=0)
    needs_patient_action = serializers.SerializerMethodField()
    has_active_intake = serializers.SerializerMethodField()
    has_medical_record = serializers.SerializerMethodField()
    has_review = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = Consultation
        fields = [
            "id", "status", "priority", "doctor", "specialty", "created_at",
            "updated_at", "submitted_at", "unread_messages",
            "needs_patient_action", "has_active_intake", "has_medical_record",
            "has_review", "available_actions",
        ]
        read_only_fields = fields

    def get_doctor(self, obj):
        if obj.doctor is None:
            return None
        specialty = obj.doctor.specialty
        return {
            "id": obj.doctor_id,
            "full_name": obj.doctor.user.full_name,
            "professional_title": obj.doctor.professional_title,
            "specialty_name": _localized_specialty_name(
                specialty, self.context.get("request")
            ),
        }

    def get_specialty(self, obj):
        if obj.specialty is None:
            return None
        return {
            "id": obj.specialty_id,
            "name": _localized_specialty_name(
                obj.specialty, self.context.get("request")
            ),
        }

    def _policy(self, obj):
        from apps.consultations.patient_actions import patient_action_policy
        return patient_action_policy(obj)

    def get_needs_patient_action(self, obj):
        actions = self._policy(obj).actions
        return bool(
            obj.status
            in {
                ConsultationStatus.AWAITING_PATIENT_RESPONSE,
                ConsultationStatus.FOLLOW_UP_REQUIRED,
                ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
                ConsultationStatus.EMERGENCY_ESCALATED,
            }
            or actions["can_continue_intake"]
            or getattr(obj, "unread_messages", 0) > 0
        )

    def get_has_active_intake(self, obj):
        intake = getattr(obj, "intake_session", None)
        return bool(
            intake
            and intake.status in {"not_started", "in_progress", "awaiting_patient_review"}
        )

    def get_has_medical_record(self, obj):
        return getattr(obj, "medical_record", None) is not None

    def get_has_review(self, obj):
        return getattr(obj, "review", None) is not None

    def get_available_actions(self, obj):
        return self._policy(obj).available_actions


class PatientConsultationDetailSerializer(serializers.ModelSerializer):
    doctor = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()
    action_reasons = serializers.SerializerMethodField()
    intake_summary = serializers.SerializerMethodField()
    messages_summary = serializers.SerializerMethodField()
    attachments_summary = serializers.SerializerMethodField()
    medical_record_summary = serializers.SerializerMethodField()
    review_summary = serializers.SerializerMethodField()
    generated_at = serializers.SerializerMethodField()

    class Meta:
        model = Consultation
        fields = [
            "id", "status", "priority", "doctor", "specialty", "description",
            "created_at", "updated_at", "submitted_at", "accepted_at",
            "cancelled_at", "cancellation_reason", "timeline", "actions",
            "action_reasons", "intake_summary", "messages_summary",
            "attachments_summary", "medical_record_summary", "review_summary",
            "generated_at",
        ]
        read_only_fields = fields

    def get_doctor(self, obj):
        if obj.doctor is None:
            return None
        return {
            "id": obj.doctor_id,
            "full_name": obj.doctor.user.full_name,
            "professional_title": obj.doctor.professional_title,
            "specialty_name": _localized_specialty_name(
                obj.doctor.specialty, self.context.get("request")
            ),
            "is_accepting_consultations": obj.doctor.is_accepting_consultations,
        }

    def get_specialty(self, obj):
        if obj.specialty is None:
            return None
        return {
            "id": obj.specialty_id,
            "name": _localized_specialty_name(
                obj.specialty, self.context.get("request")
            ),
        }

    def _policy(self, obj):
        from apps.consultations.patient_actions import patient_action_policy
        return patient_action_policy(obj)

    def get_timeline(self, obj):
        from apps.consultations.timeline import build_patient_timeline
        return build_patient_timeline(obj)

    def get_actions(self, obj):
        return self._policy(obj).actions

    def get_action_reasons(self, obj):
        return self._policy(obj).reasons

    def get_intake_summary(self, obj):
        intake = getattr(obj, "intake_session", None)
        if intake is None:
            return {
                "exists": False, "status": None, "question_count": 0,
                "is_complete": False, "emergency_detected": False,
                "updated_at": None,
            }
        return {
            "exists": True,
            "status": intake.status,
            "question_count": intake.question_count,
            "is_complete": intake.status in {
                "awaiting_patient_review", "confirmed", "submitted_to_doctor"
            },
            "emergency_detected": intake.emergency_detected,
            "updated_at": intake.updated_at,
        }

    def get_messages_summary(self, obj):
        messages = list(obj.messages.all())
        return {
            "unread_count": getattr(obj, "unread_messages", 0),
            "last_message_at": messages[-1].sent_at if messages else None,
        }

    def get_attachments_summary(self, obj):
        attachments = list(obj.attachments.all())
        return {
            "total": len(attachments),
            "available": sum(a.status == "available" for a in attachments),
            "pending_scan": sum(a.status == "pending" for a in attachments),
            "quarantined": sum(a.status == "quarantined" for a in attachments),
        }

    def get_medical_record_summary(self, obj):
        record = getattr(obj, "medical_record", None)
        return {
            "exists": record is not None,
            "id": str(record.id) if record else None,
            "status": record.status if record else None,
            "updated_at": record.updated_at if record else None,
        }

    def get_review_summary(self, obj):
        review = getattr(obj, "review", None)
        return {
            "exists": review is not None,
            "status": review.status if review else None,
            "can_edit": bool(review and review.status != "removed"),
        }

    def get_generated_at(self, obj):
        from django.utils import timezone
        return timezone.now()
