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
        allow_blank=False, max_length=4000, trim_whitespace=True
    )
    client_request_id = serializers.UUIDField(required=False)


class AnswerResponseSerializer(serializers.Serializer):
    session_status = serializers.CharField()
    patient_facing_message = serializers.CharField()
    next_question = serializers.CharField(allow_null=True, allow_blank=True)
    question_count = serializers.IntegerField()
    emergency_detected = serializers.BooleanField()
    emergency_level = serializers.CharField()
    record_ready = serializers.BooleanField()


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
            "updated_at",
            "messages",
            "is_complete",
            "ready_for_review",
            "can_send_message",
            "can_complete",
            "progress_percent",
            "emergency_instruction",
        ]

    answered_count = serializers.SerializerMethodField()
    is_complete = serializers.SerializerMethodField()
    ready_for_review = serializers.SerializerMethodField()
    can_send_message = serializers.SerializerMethodField()
    can_complete = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()
    emergency_instruction = serializers.SerializerMethodField()

    def get_answered_count(self, obj):
        return sum(message.role == "patient" for message in obj.messages.all())

    def get_is_complete(self, obj):
        return obj.status in {"ready_for_review", "confirmed"}

    def get_ready_for_review(self, obj):
        return obj.status == "ready_for_review"

    def get_can_send_message(self, obj):
        return obj.status in {"not_started", "in_progress", "awaiting_patient"}

    def get_can_complete(self, obj):
        return obj.status == "ready_for_review"

    def get_progress_percent(self, obj):
        maximum = max(1, getattr(settings, "AI_INTAKE_MAX_QUESTIONS", 12))
        return min(100, round(obj.question_count * 100 / maximum))

    def get_emergency_instruction(self, obj):
        if not obj.emergency_detected:
            return ""
        return gettext(
            "MCC is not an emergency service. Seek immediate local emergency care."
        )

    def get_messages(self, obj):
        messages = [
            message for message in obj.messages.all()
            if message.role != "system"
        ]
        return IntakeMessageSerializer(messages, many=True).data
