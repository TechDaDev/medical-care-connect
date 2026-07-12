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
    answer = serializers.CharField(allow_blank=False, max_length=4000)


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
            "status",
            "language",
            "current_question",
            "question_count",
            "emergency_detected",
            "emergency_level",
            "emergency_reasons",
            "collected_data",
            "missing_fields",
            "started_at",
            "completed_at",
            "confirmed_at",
            "created_at",
            "messages",
        ]

    def get_messages(self, obj):
        qs = obj.messages.exclude(role="system").order_by("sequence_number")
        return IntakeMessageSerializer(qs, many=True).data
