from rest_framework import serializers

from apps.notifications.models import Notification, NotificationType


class NotificationSerializer(serializers.ModelSerializer):
    """Patient-safe in-app notification with server-calculated relative link."""

    link = serializers.SerializerMethodField()

    def get_link(self, obj):
        consultation = obj.consultation
        role_root = {
            "patient": "/app/patient",
            "doctor": "/app/doctor",
            "coordinator": "/app/staff",
            "administrator": "/app/staff",
        }.get(obj.recipient.role, "/app")
        if (
            obj.notification_type == NotificationType.NEW_MESSAGE
            and consultation is not None
        ):
            if obj.recipient.role not in {"patient", "doctor"}:
                return {
                    "type": "consultation",
                    "path": f"{role_root}/consultations/{consultation.id}",
                }
            return {
                "type": "message",
                "path": f"{role_root}/messages/{consultation.id}",
            }
        if obj.notification_type in {
            NotificationType.RECORD_CONFIRMED,
            NotificationType.RECORD_REVISION_REQUESTED,
        } and consultation is not None:
            record = getattr(consultation, "medical_record", None)
            if record is not None:
                return {
                    "type": "medical_record",
                    "path": f"/app/patient/medical-records/{record.id}",
                }
        if obj.notification_type in {
            NotificationType.PRIVACY_DELETION_APPROVED,
            NotificationType.PRIVACY_DELETION_REJECTED,
        }:
            return {
                "type": "privacy",
                "path": (
                    "/app/patient/privacy/deletion"
                    if obj.recipient.role == "patient"
                    else "/app/privacy/deletion"
                ),
            }
        if consultation is not None:
            return {
                "type": "consultation",
                "path": f"{role_root}/consultations/{consultation.id}",
            }
        return {"type": "none", "path": None}

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "title",
            "body",
            "is_read",
            "read_at",
            "created_at",
            "link",
        ]
        read_only_fields = fields


class NotificationMarkReadSerializer(serializers.Serializer):
    """Marks all notifications as read. No fields needed."""

    pass


class NotificationQuerySerializer(serializers.Serializer):
    unread = serializers.BooleanField(required=False)
    type = serializers.ChoiceField(
        choices=NotificationType.choices,
        required=False,
    )
    created_after = serializers.DateField(required=False)
    created_before = serializers.DateField(required=False)

    def validate(self, attrs):
        if (
            attrs.get("created_after")
            and attrs.get("created_before")
            and attrs["created_after"] > attrs["created_before"]
        ):
            raise serializers.ValidationError(
                "created_after must not be later than created_before."
            )
        return attrs
