"""Serializers for staff endpoints."""
from rest_framework import serializers

from apps.consultations.models import Consultation, ConsultationStatus


class StaffConsultationListSerializer(serializers.ModelSerializer):
    """Lightweight consultation list for staff views."""

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

    class Meta:
        model = Consultation
        fields = [
            "id",
            "patient_name",
            "patient_email",
            "doctor_name",
            "doctor_email",
            "specialty_name",
            "status",
            "status_display",
            "priority",
            "priority_display",
            "description",
            "created_at",
            "updated_at",
            "submitted_at",
            "accepted_at",
        ]
        read_only_fields = fields


class TransferConsultationSerializer(serializers.Serializer):
    """Serializer for transferring a consultation."""

    doctor_id = serializers.UUIDField(required=True)
    reason = serializers.CharField(
        required=True, min_length=1, max_length=1000
    )


class PriorityUpdateSerializer(serializers.Serializer):
    """Serializer for updating consultation priority."""

    priority = serializers.ChoiceField(
        choices=["routine", "urgent", "emergency"],
        required=True,
    )


class DoctorWorkloadSerializer(serializers.Serializer):
    """Serializer for doctor workload summary."""

    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    specialty_name = serializers.CharField(read_only=True, default=None)
    is_approved = serializers.BooleanField(read_only=True)
    is_accepting_consultations = serializers.BooleanField(read_only=True)
    active_count = serializers.IntegerField(read_only=True)
    submitted_count = serializers.IntegerField(read_only=True)
    accepted_count = serializers.IntegerField(read_only=True)
    intake_completed_count = serializers.IntegerField(read_only=True)
    doctor_review_count = serializers.IntegerField(read_only=True)
    estimated_response_minutes = serializers.IntegerField(read_only=True, default=None)
