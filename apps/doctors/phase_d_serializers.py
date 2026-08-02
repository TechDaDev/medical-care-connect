"""Doctor Phase D boundary serializers.

Contracts intentionally exclude patient contact data, clinical narratives,
moderation internals, storage locations, and delivery-channel state.
"""

import re
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.consultations.models import ConsultationStatus, Priority
from apps.messaging.services import consultation_allows_messaging
from apps.notifications.models import Notification, NotificationType
from apps.privacy.models import AccountDeletionRequest, DataExportRequest
from apps.reviews.models import ConsultationReview, DoctorReviewResponse, ReviewStatus


class DoctorPhaseDPageSizeSerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class DoctorMessageThreadQuerySerializer(DoctorPhaseDPageSizeSerializer):
    group = serializers.ChoiceField(required=False, choices=["active", "closed"])
    unread_only = serializers.BooleanField(required=False)
    patient_awaiting_response = serializers.BooleanField(required=False)
    consultation_status = serializers.ChoiceField(required=False, choices=ConsultationStatus.choices)
    priority = serializers.ChoiceField(required=False, choices=Priority.choices)
    patient = serializers.UUIDField(required=False)
    specialty = serializers.UUIDField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=120, trim_whitespace=True)
    ordering = serializers.ChoiceField(
        required=False,
        default="priority",
        choices=["priority", "last_message_at", "-last_message_at", "unread_count", "-unread_count", "patient"],
    )


class DoctorMessageThreadSerializer(serializers.Serializer):
    consultation_id = serializers.UUIDField(source="id", read_only=True)
    patient = serializers.SerializerMethodField()
    specialty = serializers.SerializerMethodField()
    consultation_status = serializers.CharField(source="status", read_only=True)
    priority = serializers.CharField(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)
    last_message_at = serializers.DateTimeField(read_only=True, allow_null=True)
    last_message_sender_role = serializers.CharField(read_only=True, allow_null=True)
    last_message_preview = serializers.SerializerMethodField()
    patient_awaiting_response = serializers.BooleanField(read_only=True)
    messaging_available = serializers.SerializerMethodField()
    unavailable_reason = serializers.SerializerMethodField()
    action_path = serializers.SerializerMethodField()

    def get_patient(self, obj):
        return {"id": obj.patient_id, "display_name": obj.patient.user.full_name}

    def get_specialty(self, obj):
        if not obj.specialty_id:
            return None
        request = self.context.get("request")
        locale = ""
        if request is not None:
            locale = request.query_params.get("locale", "")
            if not locale:
                locale = request.headers.get("Accept-Language", "").split(",")[0]
        locale = locale.lower().split("-")[0]
        if locale == "ar":
            name = obj.specialty.name_ar or obj.specialty.name
        elif locale == "ckb":
            name = obj.specialty.name_ckb or obj.specialty.name
        else:
            name = obj.specialty.name_en or obj.specialty.name
        return {"id": obj.specialty_id, "name": name}

    def get_last_message_preview(self, obj):
        content = re.sub(r"\s+", " ", (obj.last_message_content or "").strip())
        return content[:157] + "..." if len(content) > 160 else content or None

    def get_messaging_available(self, obj):
        return consultation_allows_messaging(obj)

    def get_unavailable_reason(self, obj):
        return None if consultation_allows_messaging(obj) else "conversation_closed"

    def get_action_path(self, obj):
        return f"/app/doctor/messages/{obj.id}"


def doctor_notification_link(notification: Notification) -> dict:
    """Return allowlisted doctor-relative notification destination."""
    consultation = notification.consultation
    notification_type = notification.notification_type
    if notification_type == NotificationType.NEW_MESSAGE and consultation:
        return {"type": "message", "path": f"/app/doctor/messages/{consultation.id}"}
    if notification_type == NotificationType.RECORD_FINALIZED and consultation:
        record = getattr(consultation, "medical_record", None)
        if record is not None:
            return {"type": "medical_record", "path": f"/app/doctor/medical-records/{record.id}"}
    if notification_type == NotificationType.REVIEW_AVAILABLE:
        return {"type": "review", "path": "/app/doctor/reviews"}
    if notification_type in {
        NotificationType.PRIVACY_DELETION_APPROVED,
        NotificationType.PRIVACY_DELETION_REJECTED,
    }:
        return {"type": "privacy", "path": "/app/doctor/privacy/deletion"}
    if consultation:
        return {"type": "consultation", "path": f"/app/doctor/consultations/{consultation.id}"}
    if notification_type in {NotificationType.DOCTOR_APPLICATION, NotificationType.DOCTOR_APPLICATION_STATUS}:
        return {"type": "profile", "path": "/app/doctor/profile"}
    return {"type": "none", "path": None}


class DoctorNotificationSerializer(serializers.ModelSerializer):
    link = serializers.SerializerMethodField()

    def get_link(self, obj):
        return doctor_notification_link(obj)

    class Meta:
        model = Notification
        fields = ["id", "notification_type", "title", "body", "is_read", "read_at", "created_at", "link"]
        read_only_fields = fields


class DoctorNotificationQuerySerializer(DoctorPhaseDPageSizeSerializer):
    unread = serializers.BooleanField(required=False)
    type = serializers.ChoiceField(required=False, choices=NotificationType.choices)
    created_after = serializers.DateField(required=False)
    created_before = serializers.DateField(required=False)
    ordering = serializers.ChoiceField(required=False, default="-created_at", choices=["created_at", "-created_at"])

    def validate(self, attrs):
        if attrs.get("created_after") and attrs.get("created_before") and attrs["created_after"] > attrs["created_before"]:
            raise serializers.ValidationError({"created_before": "created_before_must_follow_created_after"})
        return attrs


class DoctorReviewQuerySerializer(DoctorPhaseDPageSizeSerializer):
    responded = serializers.BooleanField(required=False)
    awaiting_response = serializers.BooleanField(required=False)
    rating = serializers.IntegerField(required=False, min_value=1, max_value=5)
    minimum_rating = serializers.IntegerField(required=False, min_value=1, max_value=5)
    maximum_rating = serializers.IntegerField(required=False, min_value=1, max_value=5)
    status = serializers.ChoiceField(required=False, choices=ReviewStatus.choices)
    created_after = serializers.DateField(required=False)
    created_before = serializers.DateField(required=False)
    ordering = serializers.ChoiceField(
        required=False,
        default="priority",
        choices=["priority", "created_at", "-created_at", "rating", "-rating"],
    )

    def validate(self, attrs):
        minimum = attrs.get("minimum_rating")
        maximum = attrs.get("maximum_rating")
        if minimum and maximum and minimum > maximum:
            raise serializers.ValidationError({"maximum_rating": "maximum_rating_must_follow_minimum_rating"})
        if attrs.get("created_after") and attrs.get("created_before") and attrs["created_after"] > attrs["created_before"]:
            raise serializers.ValidationError({"created_before": "created_before_must_follow_created_after"})
        return attrs


class DoctorReviewResponseProjectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorReviewResponse
        fields = ["id", "body", "created_at", "updated_at"]
        read_only_fields = fields


class DoctorReviewItemSerializer(serializers.ModelSerializer):
    reviewer_display_name = serializers.SerializerMethodField()
    response = DoctorReviewResponseProjectionSerializer(read_only=True)
    can_respond = serializers.SerializerMethodField()
    can_edit_response = serializers.SerializerMethodField()
    response_unavailable_reason = serializers.SerializerMethodField()

    class Meta:
        model = ConsultationReview
        fields = [
            "id", "rating", "title", "body", "is_anonymous", "reviewer_display_name",
            "status", "created_at", "updated_at", "has_response", "response",
            "can_respond", "can_edit_response", "response_unavailable_reason",
        ]
        read_only_fields = fields

    def get_reviewer_display_name(self, obj):
        return None if obj.is_anonymous else obj.reviewer.user.full_name

    def get_can_respond(self, obj):
        return obj.status == ReviewStatus.PUBLISHED and not obj.has_response

    def get_can_edit_response(self, obj):
        response = getattr(obj, "response", None)
        return bool(
            response
            and obj.status == ReviewStatus.PUBLISHED
            and timezone.now() <= response.created_at + timedelta(hours=72)
        )

    def get_response_unavailable_reason(self, obj):
        if obj.status != ReviewStatus.PUBLISHED:
            return "review_not_eligible"
        if not obj.has_response:
            return None
        if not self.get_can_edit_response(obj):
            return "response_edit_window_closed"
        return None


class DoctorReviewResponseCreateSerializer(serializers.Serializer):
    body = serializers.CharField(trim_whitespace=True, min_length=10, max_length=2000)
    client_request_id = serializers.UUIDField()

    def validate_body(self, value):
        normalized = " ".join(value.split())
        if len([character for character in normalized if character.isalnum()]) < 10:
            raise serializers.ValidationError("response_too_short")
        return normalized


class DoctorReviewResponseUpdateSerializer(DoctorReviewResponseCreateSerializer):
    expected_updated_at = serializers.DateTimeField()


class DoctorDataExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataExportRequest
        fields = ["id", "status", "requested_at", "started_at", "completed_at", "expires_at", "size_bytes", "failure_code"]
        read_only_fields = fields


class DoctorDeletionRequestSerializer(serializers.ModelSerializer):
    can_cancel = serializers.SerializerMethodField()

    def get_can_cancel(self, obj):
        return obj.status == "pending"

    class Meta:
        model = AccountDeletionRequest
        fields = ["id", "status", "reason", "requested_at", "reviewed_at", "rejection_reason", "can_cancel"]
        read_only_fields = fields


class DoctorDeletionCreateSerializer(serializers.Serializer):
    reason = serializers.CharField(trim_whitespace=True, min_length=10, max_length=1000)
    confirmation = serializers.BooleanField()

    def validate_confirmation(self, value):
        if value is not True:
            raise serializers.ValidationError("confirmation_required")
        return value
