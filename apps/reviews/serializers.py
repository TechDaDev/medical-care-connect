from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.reviews.models import (
    ConsultationReview,
    DoctorReviewResponse,
    ReviewReport,
    ReviewStatus,
)


class DoctorReviewResponseSerializer(serializers.ModelSerializer):
    """Serializer for doctor responses to reviews."""

    class Meta:
        model = DoctorReviewResponse
        fields = [
            "id",
            "review",
            "doctor",
            "body",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "review", "doctor", "created_at", "updated_at"]


class ReviewSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating a review."""

    reviewer_name = serializers.SerializerMethodField()
    doctor_id = serializers.UUIDField(read_only=True)
    doctor_name = serializers.CharField(read_only=True, source="consultation.doctor.user.full_name")
    consultation_status = serializers.CharField(read_only=True, source="consultation.status")

    class Meta:
        model = ConsultationReview
        fields = [
            "id",
            "consultation",
            "reviewer",
            "reviewer_name",
            "doctor_id",
            "doctor_name",
            "rating",
            "title",
            "body",
            "is_anonymous",
            "status",
            "consultation_status",
            "has_response",
            "edit_count",
            "last_edited_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "consultation",
            "reviewer",
            "reviewer_name",
            "doctor_id",
            "doctor_name",
            "status",
            "consultation_status",
            "has_response",
            "edit_count",
            "last_edited_at",
            "created_at",
            "updated_at",
        ]

    def get_reviewer_name(self, obj) -> str:
        if obj.is_anonymous:
            return str(_("Anonymous"))
        return obj.reviewer.user.full_name


class ReviewDetailSerializer(serializers.ModelSerializer):
    """Detailed review with response and report counts."""

    reviewer_name = serializers.SerializerMethodField()
    doctor_id = serializers.UUIDField(read_only=True)
    doctor_name = serializers.CharField(read_only=True, source="consultation.doctor.user.full_name")
    response = DoctorReviewResponseSerializer(read_only=True)
    report_count = serializers.SerializerMethodField()

    class Meta:
        model = ConsultationReview
        fields = [
            "id",
            "consultation",
            "reviewer",
            "reviewer_name",
            "doctor_id",
            "doctor_name",
            "rating",
            "title",
            "body",
            "is_anonymous",
            "status",
            "has_response",
            "response",
            "report_count",
            "edit_count",
            "last_edited_at",
            "moderated_at",
            "moderation_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_reviewer_name(self, obj) -> str:
        if obj.is_anonymous:
            return str(_("Anonymous"))
        return obj.reviewer.user.full_name

    def get_report_count(self, obj):
        return obj.reports.count()


class ReviewReportSerializer(serializers.ModelSerializer):
    """Serializer for submitting/listing reports."""

    class Meta:
        model = ReviewReport
        fields = [
            "id",
            "review",
            "reporter",
            "reason",
            "description",
            "resolved_at",
            "resolved_by",
            "resolution",
            "resolution_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "review",
            "reporter",
            "resolved_at",
            "resolved_by",
            "resolution",
            "resolution_notes",
            "created_at",
            "updated_at",
        ]


class DoctorReputationSerializer(serializers.Serializer):
    """Aggregated reputation data for a doctor."""

    doctor_id = serializers.UUIDField(read_only=True)
    doctor_name = serializers.CharField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    total_reviews = serializers.IntegerField(read_only=True)
    rating_distribution = serializers.DictField(read_only=True)
    response_rate = serializers.FloatField(read_only=True)
    recent_ratings_trend = serializers.CharField(read_only=True)


class ModerateReviewSerializer(serializers.Serializer):
    """Staff serializer for moderating a review."""

    status = serializers.ChoiceField(choices=ReviewStatus.choices)
    moderation_reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class ReviewReportResolveSerializer(serializers.Serializer):
    """Staff serializer for resolving a report."""

    resolution = serializers.ChoiceField(
        choices=[
            ("dismissed", _("Dismissed")),
            ("content_hidden", _("Content Hidden")),
            ("content_removed", _("Content Removed")),
            ("reviewer_warned", _("Reviewer Warned")),
            ("reviewer_suspended", _("Reviewer Suspended")),
        ]
    )
    resolution_notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
