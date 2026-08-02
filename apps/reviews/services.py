"""Services for reviews app — notifications and reputation calculations."""

from django.db.models import Avg, Count, Q

from apps.notifications.models import NotificationType
from apps.notifications.services import create_notification
from apps.reviews.models import ConsultationReview


def notify_review_created(review):
    """Notify the doctor about a new review."""
    doctor_user = review.consultation.doctor.user
    create_notification(
        recipient=doctor_user,
        notification_type=NotificationType.REVIEW_AVAILABLE,
        title="New Review Available",
        body=f"You received a {review.rating}★ review.",
        consultation=review.consultation,
    )


def notify_review_updated(review):
    """Notify the doctor when a review is updated."""
    doctor_user = review.consultation.doctor.user
    create_notification(
        recipient=doctor_user,
        notification_type=NotificationType.REVIEW_AVAILABLE,
        title="Review Updated",
        body=f"A review was updated to {review.rating}★.",
        consultation=review.consultation,
    )


def notify_review_response(review, response):
    """Notify the patient about a doctor's response."""
    patient_user = review.consultation.patient.user
    create_notification(
        recipient=patient_user,
        notification_type=NotificationType.REVIEW_RESPONSE,
        title="Doctor Responded to Your Review",
        body="Your doctor posted a public response to your review.",
        consultation=review.consultation,
    )


def notify_moderation_state_change(review):
    """Notify the reviewer when their review's moderation state changes."""
    patient_user = review.reviewer.user
    if review.status == "removed":
        title = "Review Removed"
        body = "Your review has been removed. Contact support for details."
    elif review.status == "hidden":
        title = "Review Hidden"
        body = "Your review has been hidden pending moderation."
    elif review.status == "published":
        title = "Review Published"
        body = "Your review is now publicly visible."
    else:
        title = "Review Status Changed"
        body = f"Your review status changed to {review.status}."

    create_notification(
        recipient=patient_user,
        notification_type=NotificationType.MODERATION_STATE,
        title=title,
        body=body,
        consultation=review.consultation,
    )


def notify_report_resolution(report):
    """Notify the reporter about report resolution."""
    if report.resolution == "dismissed":
        title = "Report Resolved — Dismissed"
        body = "Your report was reviewed and dismissed."
    elif report.resolution in ("content_hidden", "content_removed"):
        title = "Report Resolved — Action Taken"
        body = "Your report was reviewed and action has been taken."
    else:
        title = "Report Resolved"
        body = "Your report has been resolved."

    create_notification(
        recipient=report.reporter,
        notification_type=NotificationType.REPORT_RESOLUTION,
        title=title,
        body=body,
    )


def compute_doctor_reputation(doctor):
    """Calculate aggregated reputation metrics for a doctor."""
    reviews = ConsultationReview.objects.filter(
        consultation__doctor=doctor,
        status="published",
    )
    if not reviews.exists():
        return None

    agg = reviews.aggregate(
        avg_rating=Avg("rating"),
        total=Count("id"),
    )

    distribution = {}
    for i in range(1, 6):
        distribution[str(i)] = reviews.filter(rating=i).count()

    total = agg["total"]
    with_response = reviews.filter(has_response=True).count()
    response_rate = round((with_response / total * 100), 1) if total > 0 else 0.0

    trend = _compute_trend(reviews)

    return {
        "average_rating": round(float(agg["avg_rating"]), 2) if agg["avg_rating"] else 0.0,
        "total_reviews": total,
        "rating_distribution": distribution,
        "response_rate": response_rate,
        "recent_ratings_trend": trend,
    }


def _compute_trend(reviews):
    """Simple trend indicator based on most recent 10 vs previous 10 reviews."""
    ordered = reviews.order_by("-created_at")
    recent = list(ordered[:10].values_list("rating", flat=True))
    if len(recent) < 5:
        return "stable"

    older = list(ordered[10:20].values_list("rating", flat=True))
    if not older:
        return "stable"

    recent_avg = sum(recent) / len(recent)
    older_avg = sum(older) / len(older)

    diff = recent_avg - older_avg
    if diff > 0.3:
        return "improving"
    elif diff < -0.3:
        return "declining"
    return "stable"
