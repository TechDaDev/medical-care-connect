from rest_framework import serializers

from apps.consultations.models import Consultation, ConsultationStatus


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
        if value.specialty_id and not value.specialty.is_active:
            raise serializers.ValidationError(
                "This doctor's specialty is not available for new consultations."
            )
        return value

    def validate(self, attrs):
        doctor = attrs.get("doctor")
        specialty = attrs.get("specialty")
        if specialty and not specialty.is_active:
            raise serializers.ValidationError(
                {"specialty": "This specialty is not active."}
            )
        if doctor and specialty and doctor.specialty_id != specialty.id:
            raise serializers.ValidationError(
                {"specialty": "Specialty must match the selected doctor."}
            )
        return attrs


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
