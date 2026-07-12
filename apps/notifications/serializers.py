from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializes an in-app notification."""

    class Meta:
        model = Notification
        fields = [
            "id", "recipient", "notification_type", "title", "body",
            "consultation", "related_message", "is_read", "read_at",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "recipient", "notification_type", "title", "body",
            "consultation", "related_message", "created_at", "updated_at",
        ]


class NotificationMarkReadSerializer(serializers.Serializer):
    """Marks all notifications as read. No fields needed."""

    pass
