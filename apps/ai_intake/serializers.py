from django.conf import settings
from django.utils.translation import gettext
from rest_framework import serializers

from apps.ai_intake.models import AIIntakeMessage, AIIntakeSession


class StartIntakeResponseSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    session_status = serializers.CharField()
    current_question = serializers.CharField(allow_blank=True)
    question_count = serializers.IntegerField()
    emergency_detected = serializers.BooleanField()
    emergency_level = serializers.CharField()
    emergency_message = serializers.CharField(allow_blank=True, required=False)
    language = serializers.CharField()


class AnswerRequestSerializer(serializers.Serializer):
    answer = serializers.CharField(
        allow_blank=False, max_length=2000, trim_whitespace=True
    )
    client_request_id = serializers.UUIDField(required=False, allow_null=True)


class AnswerResponseSerializer(serializers.Serializer):
    conversation_status = serializers.CharField(required=False, default="needs_more_information")
    session_status = serializers.CharField()
    patient_facing_message = serializers.CharField()
    next_question = serializers.CharField(allow_null=True, allow_blank=True)
    next_question_field = serializers.CharField(allow_null=True, required=False)
    question_count = serializers.IntegerField()
    emergency_detected = serializers.BooleanField()
    emergency_level = serializers.CharField()
    record_ready = serializers.BooleanField()
    submitted_to_doctor = serializers.BooleanField(required=False, default=False)
    error_code = serializers.CharField(allow_blank=True, required=False)
    retryable = serializers.BooleanField(required=False, default=False)
    replayed = serializers.BooleanField(required=False, default=False)
    completeness = serializers.DictField(required=False, allow_null=True)


class ConfirmRequestSerializer(serializers.Serializer):
    expected_updated_at = serializers.DateTimeField()
    confirmation = serializers.BooleanField()
    client_request_id = serializers.UUIDField()

    def validate(self, attrs):
        if not attrs.get("confirmation", False):
            raise serializers.ValidationError("confirmation_required")
        return attrs


class CorrectionRequestSerializer(serializers.Serializer):
    expected_updated_at = serializers.DateTimeField()
    corrections = serializers.DictField()
    client_request_id = serializers.UUIDField()


class SubmissionRequestSerializer(serializers.Serializer):
    expected_updated_at = serializers.DateTimeField()
    client_request_id = serializers.UUIDField()


class ReviewResponseSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    session_status = serializers.CharField()
    consultation_id = serializers.UUIDField(required=False)
    review = serializers.DictField()
    can_confirm = serializers.BooleanField()
    can_correct = serializers.BooleanField()
    can_submit = serializers.BooleanField()
    updated_at = serializers.DateTimeField()
    missing_blocking_fields = serializers.ListField(child=serializers.CharField(), required=False)


class IntakeMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIIntakeMessage
        fields = ["id", "role", "content", "sequence_number", "created_at"]


class IntakeSessionSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()

    class Meta:
        model = AIIntakeSession
        fields = [
            "id",
            "consultation",
            "status",
            "language",
            "current_question",
            "question_count",
            "answered_count",
            "emergency_detected",
            "emergency_level",
            "started_at",
            "completed_at",
            "confirmed_at",
            "submitted_at",
            "updated_at",
            "messages",
            "is_complete",
            "ready_for_review",
            "can_send_message",
            "can_complete",
            "can_confirm",
            "can_submit",
            "progress_percent",
            "emergency_instruction",
            "missing_blocking_fields",
        ]

    answered_count = serializers.SerializerMethodField()
    is_complete = serializers.SerializerMethodField()
    ready_for_review = serializers.SerializerMethodField()
    can_send_message = serializers.SerializerMethodField()
    can_complete = serializers.SerializerMethodField()
    can_confirm = serializers.SerializerMethodField()
    can_submit = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()
    emergency_instruction = serializers.SerializerMethodField()
    missing_blocking_fields = serializers.SerializerMethodField()

    def get_answered_count(self, obj):
        return sum(1 for m in obj.messages.all() if m.role == "patient")

    def get_is_complete(self, obj):
        return obj.status in {
            "awaiting_patient_review", "confirmed", "submitted_to_doctor"
        }

    def get_ready_for_review(self, obj):
        return obj.status == "awaiting_patient_review"

    def get_can_send_message(self, obj):
        return obj.status in {"not_started", "in_progress", "failed"}

    def get_can_complete(self, obj):
        return obj.status == "awaiting_patient_review"

    def get_can_confirm(self, obj):
        return obj.status == "awaiting_patient_review"

    def get_can_submit(self, obj):
        return obj.status == "confirmed"

    def get_progress_percent(self, obj):
        maximum = max(1, getattr(settings, "AI_INTAKE_MAX_QUESTIONS", 12))
        return min(100, round(obj.question_count * 100 / maximum))

    def get_emergency_instruction(self, obj):
        if not obj.emergency_detected:
            return ""
        return gettext(
            "MCC is not an emergency service. Seek immediate local emergency care."
        )

    def get_missing_blocking_fields(self, obj):
        return obj.missing_fields or []

    def get_messages(self, obj):
        messages = [
            message for message in obj.messages.all()
            if message.role != "system"
        ]
        return IntakeMessageSerializer(messages, many=True).data