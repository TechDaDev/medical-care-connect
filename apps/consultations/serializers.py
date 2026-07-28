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

    cancellation_reason = serializers.CharField(required=True, min_length=1)


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
