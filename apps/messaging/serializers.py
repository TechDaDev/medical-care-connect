from rest_framework import serializers

from apps.messaging.models import ConsultationMessage, DoctorInternalNote
from apps.messaging.services import (
    consultation_allows_messaging,
    create_consultation_message,
)


class MessageSerializer(serializers.ModelSerializer):
    """Serializes a consultation message."""

    sender_email = serializers.EmailField(source="sender.email", read_only=True)
    sender_name = serializers.SerializerMethodField()
    read_by = serializers.SerializerMethodField()

    class Meta:
        model = ConsultationMessage
        fields = [
            "id", "consultation", "sender", "sender_email", "sender_name",
            "message_type", "content", "is_system_message",
            "sent_at", "edited_at", "read_by",
        ]
        read_only_fields = [
            "id", "sender", "sender_email", "sender_name",
            "message_type", "is_system_message", "sent_at",
            "edited_at", "read_by",
        ]

    def get_sender_name(self, obj) -> str:
        if not obj.sender:
            return "System"
        return obj.sender.full_name

    def get_read_by(self, obj) -> list[dict]:
        receipts = obj.read_receipts.select_related("user").all()
        return [
            {"user_id": r.user.id, "read_at": r.read_at}
            for r in receipts
        ]


class MessageCreateSerializer(serializers.Serializer):
    """Validates and creates a new message."""

    content = serializers.CharField(max_length=5000, min_length=1)

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
