from rest_framework import serializers

from apps.messaging.models import ConsultationMessage, DoctorInternalNote
from apps.messaging.services import (
    consultation_allows_messaging,
    create_consultation_message,
)


class MessageSerializer(serializers.ModelSerializer):
    """Serializes a consultation message."""

    sender_name = serializers.SerializerMethodField()
    is_read_by_current_user = serializers.SerializerMethodField()

    class Meta:
        model = ConsultationMessage
        fields = [
            "id", "consultation", "sender", "sender_name",
            "message_type", "content", "is_system_message",
            "sent_at", "edited_at", "is_read_by_current_user",
        ]
        read_only_fields = [
            "id", "sender", "sender_name",
            "message_type", "is_system_message", "sent_at",
            "edited_at", "is_read_by_current_user",
        ]

    def get_sender_name(self, obj) -> str:
        if not obj.sender:
            return "System"
        return obj.sender.full_name

    def get_is_read_by_current_user(self, obj) -> bool:
        request = self.context.get("request")
        if not request:
            return False
        if obj.sender_id == request.user.id:
            return True
        return any(
            receipt.user_id == request.user.id
            for receipt in obj.read_receipts.all()
        )


class MessageCreateSerializer(serializers.Serializer):
    """Validates and creates a new message."""

    content = serializers.CharField(max_length=5000, min_length=1, trim_whitespace=True)
    client_request_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        consultation = self.context.get("consultation")
        if consultation and not consultation_allows_messaging(consultation):
            raise serializers.ValidationError(
                f"Cannot send messages in status '{consultation.get_status_display()}'."
            )
        return attrs

    def save(self, **kwargs):
        consultation = self.context["consultation"]
        sender = self.context["sender"]
        return create_consultation_message(
            consultation=consultation,
            sender=sender,
            content=self.validated_data["content"],
            client_request_id=self.validated_data.get("client_request_id"),
        )


class MarkReadSerializer(serializers.Serializer):
    """Accepts a list of message IDs to mark as read."""

    message_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )


class UnreadCountSerializer(serializers.Serializer):
    """Unread message count for a consultation."""

    consultation_id = serializers.UUIDField(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)


class InternalNoteSerializer(serializers.ModelSerializer):
    """Serializes a doctor internal note."""

    author_email = serializers.EmailField(source="author.email", read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = DoctorInternalNote
        fields = [
            "id", "consultation", "author", "author_email", "author_name",
            "content", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "author", "author_email", "author_name",
            "created_at", "updated_at",
        ]

    def get_author_name(self, obj) -> str:
        return obj.author.full_name


class InternalNoteCreateSerializer(serializers.ModelSerializer):
    """Creates an internal note."""

    class Meta:
        model = DoctorInternalNote
        fields = ["content"]

    def validate_content(self, value):
        if len(value) > 5000:
            raise serializers.ValidationError("Content cannot exceed 5000 characters.")
        return value
