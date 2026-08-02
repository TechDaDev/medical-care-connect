"""Doctor Phase A application services.

Contracts here keep access decisions, dashboard aggregation, and availability
summaries consistent across API views without exposing clinical content.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime

from django.conf import settings
from django.db.models import Avg, Count, Max, Q
from django.utils import timezone

from apps.consultations.models import Consultation, ConsultationStatus, Priority
from apps.doctors.models import DoctorAvailability, DoctorProfile
from apps.messaging.models import ConsultationMessage
from apps.notifications.models import Notification, NotificationType
from apps.reviews.models import ConsultationReview, ReviewStatus


DOCTOR_TERMINAL_STATUSES = {
    ConsultationStatus.COMPLETED,
    ConsultationStatus.CANCELLED,
    ConsultationStatus.TRANSFERRED,
}
DOCTOR_ACTIVE_STATUSES = [
    value
    for value, _label in ConsultationStatus.choices
    if value not in DOCTOR_TERMINAL_STATUSES and value != ConsultationStatus.DRAFT
]
DOCTOR_ATTENTION_STATUSES = {
    ConsultationStatus.SUBMITTED,
    ConsultationStatus.INTAKE_COMPLETED,
    ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
    ConsultationStatus.UNDER_REVIEW,
    ConsultationStatus.FOLLOW_UP_REQUIRED,
    ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
    ConsultationStatus.EMERGENCY_ESCALATED,
}


def doctor_profile_completeness(profile: DoctorProfile | None) -> dict:
    """Return stable, non-sensitive profile completion codes."""
    if profile is None:
        return {
            "is_complete": False,
            "missing_fields": ["doctor_profile"],
        }

    user = profile.user
    checks = OrderedDict(
        (
            ("first_name", bool((user.first_name or "").strip())),
            ("last_name", bool((user.last_name or "").strip())),
            ("phone_number", bool((user.phone_number or "").strip())),
            ("specialty", profile.specialty_id is not None),
            (
                "professional_title",
                bool((profile.professional_title or "").strip()),
            ),
            ("workplace_name", bool((profile.workplace_name or "").strip())),
            ("qualifications", bool((profile.qualifications or "").strip())),
            ("biography", bool((profile.biography or "").strip())),
            ("languages", bool(profile.languages)),
            (
                "estimated_response_minutes",
                bool(profile.estimated_response_minutes),
            ),
        )
    )
    missing = [field for field, complete in checks.items() if not complete]
    complete_count = len(checks) - len(missing)
    return {
        "is_complete": not missing,
        "completion_percent": round((complete_count / len(checks)) * 100),
        "missing_fields": missing,
    }


def doctor_access_state(user, profile: DoctorProfile | None = None) -> dict:
    """Build authoritative doctor access/navigation contract."""
    if profile is None:
        profile = getattr(user, "doctor_profile", None)

    if not user.is_active:
        state = "inactive"
    elif profile is None:
        state = "missing_profile"
    elif profile.approval_status == DoctorProfile.ApprovalStatus.REJECTED:
        state = "rejected"
    elif profile.approval_status == DoctorProfile.ApprovalStatus.SUSPENDED:
        state = "suspended"
    elif (
        profile.approval_status == DoctorProfile.ApprovalStatus.APPROVED
        and profile.is_approved
    ):
        state = "approved"
    else:
        state = "pending"

    next_paths = {
        "approved": "/app/doctor",
        "pending": "/app/doctor/pending-approval",
        "rejected": "/app/doctor/application-rejected",
        "suspended": "/app/doctor/suspended",
        "missing_profile": "/app/doctor/profile-missing",
        "inactive": "/login",
    }
    can_edit_profile = state in {"approved", "pending", "rejected"}
    reason_codes = {
        "approved": None,
        "pending": "application_pending",
        "rejected": "application_rejected",
        "suspended": "account_suspended",
        "missing_profile": "doctor_profile_missing",
        "inactive": "account_inactive",
    }
    return {
        "state": state,
        "can_access_dashboard": state == "approved",
        "can_manage_availability": state == "approved",
        "can_accept_consultations": state == "approved",
        "can_edit_profile": can_edit_profile,
        "reason_code": reason_codes[state],
        "approval_status": profile.approval_status if profile else None,
        "is_approved": bool(profile and profile.is_approved),
        "is_accepting_consultations": bool(
            profile and profile.is_accepting_consultations
        ),
        "profile_id": str(profile.id) if profile else None,
        "updated_at": profile.updated_at if profile else None,
        "next_path": next_paths[state],
    }


def availability_summary(profile: DoctorProfile) -> dict:
    """Return weekly availability summary; recurring slots have no dated next slot."""
    slots = DoctorAvailability.objects.filter(doctor=profile)
    return {
        "timezone": settings.TIME_ZONE,
        "is_accepting_consultations": profile.is_accepting_consultations,
        "can_toggle_accepting": True,
        "toggle_unavailable_reason": None,
        "active_slot_count": slots.filter(is_active=True).count(),
        "next_available_start": None,
    }


def _consultation_action_path(consultation_id) -> str:
    return f"/app/doctor/consultations/{consultation_id}"


def _notification_action_path(notification: Notification) -> str:
    if (
        notification.notification_type == NotificationType.NEW_MESSAGE
        and notification.consultation_id
    ):
        return f"/app/doctor/messages/{notification.consultation_id}"
    if notification.consultation_id:
        return _consultation_action_path(notification.consultation_id)
    if notification.notification_type in {
        NotificationType.REVIEW_AVAILABLE,
        NotificationType.REVIEW_RESPONSE,
    }:
        return "/app/doctor/reviews"
    if notification.notification_type in {
        NotificationType.DOCTOR_APPLICATION,
        NotificationType.DOCTOR_APPLICATION_STATUS,
        NotificationType.ACCOUNT_STATUS_CHANGE,
    }:
        return "/app/doctor/profile"
    return "/app/doctor/notifications"


def build_doctor_dashboard(profile: DoctorProfile, user) -> dict:
    """Build bounded-query dashboard response without message/record content."""
    consultations = Consultation.objects.filter(doctor=profile)
    status_annotations = {
        value: Count("id", filter=Q(status=value))
        for value, _label in ConsultationStatus.choices
    }
    consultation_counts = consultations.aggregate(
        total=Count("id"),
        total_active=Count("id", filter=Q(status__in=DOCTOR_ACTIVE_STATUSES)),
        urgent=Count(
            "id",
            filter=Q(priority=Priority.URGENT, status__in=DOCTOR_ACTIVE_STATUSES),
        ),
        **status_annotations,
    )

    recent_models = list(
        consultations.select_related("patient__user", "specialty")
        .only(
            "id",
            "status",
            "priority",
            "updated_at",
            "patient__user__first_name",
            "patient__user__last_name",
            "specialty__name",
            "specialty__name_en",
            "specialty__name_ar",
            "specialty__name_ckb",
        )
        .order_by("-updated_at")[:8]
    )

    unread_rows = list(
        ConsultationMessage.objects.filter(consultation__doctor=profile)
        .exclude(sender=user)
        .exclude(read_receipts__user=user)
        .values(
            "consultation_id",
            "consultation__patient__user__first_name",
            "consultation__patient__user__last_name",
            "consultation__status",
        )
        .annotate(unread_count=Count("id", distinct=True), last_message_at=Max("sent_at"))
        .order_by("-last_message_at")
    )
    unread_by_consultation = {
        row["consultation_id"]: row["unread_count"] for row in unread_rows
    }
    unread_total = sum(row["unread_count"] for row in unread_rows)
    notification_qs = Notification.objects.filter(recipient=user)
    unread_notifications = notification_qs.filter(is_read=False).count()
    recent_notification_models = list(
        notification_qs.only(
            "id",
            "notification_type",
            "title",
            "body",
            "consultation_id",
            "is_read",
            "created_at",
        ).order_by("-created_at")[:5]
    )

    review_qs = ConsultationReview.objects.filter(
        consultation__doctor=profile,
        status=ReviewStatus.PUBLISHED,
    )
    review_summary = review_qs.aggregate(
        total=Count("id"),
        unanswered=Count("id", filter=Q(has_response=False)),
        average_rating=Avg("rating"),
    )
    recent_reviews = list(
        review_qs.only(
            "id",
            "consultation_id",
            "rating",
            "is_anonymous",
            "has_response",
            "created_at",
        ).order_by("-created_at")[:3]
    )

    attention = []

    def add_attention(
        item_type,
        count,
        severity,
        path,
        *,
        consultation_id=None,
        review_id=None,
    ):
        if count:
            attention.append(
                {
                    "type": item_type,
                    "consultation_id": (
                        str(consultation_id) if consultation_id else None
                    ),
                    "review_id": str(review_id) if review_id else None,
                    "count": count,
                    "severity": severity,
                    "title_key": f"doctor.attention.{item_type}.title",
                    "description_key": f"doctor.attention.{item_type}.description",
                    "created_at": None,
                    "action_path": path or "/app/doctor/consultations",
                }
            )

    representative = {
        consultation.status: consultation.id for consultation in reversed(recent_models)
    }
    add_attention(
        "emergency_escalation",
        consultation_counts[ConsultationStatus.EMERGENCY_ESCALATED],
        "danger",
        (
            _consultation_action_path(
                representative[ConsultationStatus.EMERGENCY_ESCALATED]
            )
            if ConsultationStatus.EMERGENCY_ESCALATED in representative
            else "/app/doctor/consultations"
        ),
        consultation_id=representative.get(
            ConsultationStatus.EMERGENCY_ESCALATED
        ),
    )
    add_attention(
        "urgent_consultation",
        consultation_counts["urgent"],
        "danger",
        "/app/doctor/consultations",
    )
    for item_type, consultation_status in (
        ("new_consultation", ConsultationStatus.SUBMITTED),
        ("intake_ready", ConsultationStatus.INTAKE_COMPLETED),
        ("awaiting_doctor_response", ConsultationStatus.AWAITING_DOCTOR_RESPONSE),
    ):
        add_attention(
            item_type,
            consultation_counts[consultation_status],
            "warning",
            (
                _consultation_action_path(representative[consultation_status])
                if consultation_status in representative
                else "/app/doctor/consultations"
            ),
            consultation_id=representative.get(consultation_status),
        )
    add_attention(
        "unread_messages",
        unread_total,
        "warning",
        "/app/doctor/messages",
    )
    unanswered_review = next(
        (review for review in recent_reviews if not review.has_response), None
    )
    add_attention(
        "review_response",
        review_summary["unanswered"],
        "info",
        "/app/doctor/reviews?responded=false",
        review_id=unanswered_review.id if unanswered_review else None,
    )

    recent_consultations = [
        {
            "id": str(consultation.id),
            "patient_display_name": consultation.patient.user.full_name,
            "specialty": (
                {
                    "id": str(consultation.specialty_id),
                    "name": consultation.specialty.name,
                }
                if consultation.specialty_id
                else None
            ),
            "status": consultation.status,
            "priority": consultation.priority,
            "unread_messages": unread_by_consultation.get(consultation.id, 0),
            "needs_doctor_action": consultation.status in DOCTOR_ATTENTION_STATUSES,
            "updated_at": consultation.updated_at,
            "action_path": _consultation_action_path(consultation.id),
        }
        for consultation in recent_models[:5]
    ]

    return {
        "generated_at": timezone.now(),
        "access": doctor_access_state(user, profile),
        "profile": {
            "id": str(profile.id),
            "full_name": user.full_name,
            "professional_title": profile.professional_title,
            "specialty_name": profile.specialty.name if profile.specialty_id else None,
            "approval_status": profile.approval_status,
            "is_approved": profile.is_approved,
            "is_accepting_consultations": profile.is_accepting_consultations,
            "completion_percent": doctor_profile_completeness(profile)[
                "completion_percent"
            ],
            "missing_fields": doctor_profile_completeness(profile)[
                "missing_fields"
            ],
        },
        "consultations": {
            "total_active": consultation_counts["total_active"],
            "submitted": consultation_counts[ConsultationStatus.SUBMITTED],
            "accepted": consultation_counts[ConsultationStatus.ACCEPTED],
            "intake_in_progress": consultation_counts[
                ConsultationStatus.INTAKE_IN_PROGRESS
            ],
            "intake_completed": consultation_counts[
                ConsultationStatus.INTAKE_COMPLETED
            ],
            "doctor_review": consultation_counts[ConsultationStatus.DOCTOR_REVIEW],
            "awaiting_patient": consultation_counts[
                ConsultationStatus.AWAITING_PATIENT_RESPONSE
            ],
            "awaiting_doctor": consultation_counts[
                ConsultationStatus.AWAITING_DOCTOR_RESPONSE
            ],
            "under_review": consultation_counts[ConsultationStatus.UNDER_REVIEW],
            "follow_up_required": consultation_counts[
                ConsultationStatus.FOLLOW_UP_REQUIRED
            ],
            "physical_visit_required": consultation_counts[
                ConsultationStatus.PHYSICAL_VISIT_REQUIRED
            ],
            "transferred": consultation_counts[ConsultationStatus.TRANSFERRED],
            "emergency_escalated": consultation_counts[
                ConsultationStatus.EMERGENCY_ESCALATED
            ],
            "completed": consultation_counts[ConsultationStatus.COMPLETED],
            "cancelled": consultation_counts[ConsultationStatus.CANCELLED],
        },
        "attention": {
            "total": sum(item["count"] for item in attention),
            "items": attention,
        },
        "recent_consultations": recent_consultations,
        "messages": {
            "unread_total": unread_total,
            "recent_threads": [
                {
                    "consultation_id": str(row["consultation_id"]),
                    "patient_display_name": " ".join(
                        filter(
                            None,
                            (
                                row["consultation__patient__user__first_name"],
                                row["consultation__patient__user__last_name"],
                            ),
                        )
                    ),
                    "consultation_status": row["consultation__status"],
                    "unread_count": row["unread_count"],
                    "last_message_at": row["last_message_at"],
                    "action_path": f"/app/doctor/messages/{row['consultation_id']}",
                }
                for row in unread_rows[:5]
            ],
        },
        "notifications": {
            "unread_total": unread_notifications,
            "recent": [
                {
                    "id": str(notification.id),
                    "notification_type": notification.notification_type,
                    "title": notification.title,
                    "body": notification.body,
                    "is_read": notification.is_read,
                    "created_at": notification.created_at,
                    "action_path": _notification_action_path(notification),
                }
                for notification in recent_notification_models
            ],
        },
        "reviews": {
            "total_reviews": review_summary["total"],
            "awaiting_response": review_summary["unanswered"],
            "average_rating": review_summary["average_rating"] or 0.0,
            "recent": [
                {
                    "id": str(review.id),
                    "consultation_id": str(review.consultation_id),
                    "rating": review.rating,
                    "is_anonymous": review.is_anonymous,
                    "has_response": review.has_response,
                    "created_at": review.created_at,
                    "action_path": "/app/doctor/reviews",
                }
                for review in recent_reviews
            ],
        },
        "availability": availability_summary(profile),
    }


def availability_overlaps(
    *,
    profile: DoctorProfile,
    day_of_week: str,
    start_time,
    end_time,
    exclude_id=None,
) -> bool:
    """Check interval overlap while caller holds doctor-profile row lock."""
    queryset = DoctorAvailability.objects.filter(
        doctor=profile,
        day_of_week=day_of_week,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if exclude_id:
        queryset = queryset.exclude(id=exclude_id)
    return queryset.exists()


def stale_timestamp(expected: datetime | None, actual: datetime) -> bool:
    """Compare optional optimistic-concurrency timestamp."""
    return expected is not None and expected != actual
