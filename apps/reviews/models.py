from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class ReviewStatus(models.TextChoices):
    PUBLISHED = "published", _("Published")
    UNDER_REVIEW = "under_review", _("Under Review")
    HIDDEN = "hidden", _("Hidden")
    REMOVED = "removed", _("Removed")


class ReportResolution(models.TextChoices):
    DISMISSED = "dismissed", _("Dismissed")
    CONTENT_HIDDEN = "content_hidden", _("Content Hidden")
    CONTENT_REMOVED = "content_removed", _("Content Removed")
    REVIEWER_WARNED = "reviewer_warned", _("Reviewer Warned")
    REVIEWER_SUSPENDED = "reviewer_suspended", _("Reviewer Suspended")


class ConsultationReview(BaseModel):
    """A patient's review of a completed consultation."""

    consultation = models.OneToOneField(
        "consultations.Consultation",
        on_delete=models.CASCADE,
        related_name="review",
        verbose_name=_("consultation"),
    )
    reviewer = models.ForeignKey(
        "patients.PatientProfile",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("reviewer"),
    )
    rating = models.PositiveSmallIntegerField(
        _("rating"),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_("Rating from 1 (worst) to 5 (best)."),
    )
    title = models.CharField(_("title"), max_length=255, blank=True)
    body = models.TextField(_("body"), blank=True)
    is_anonymous = models.BooleanField(
        _("anonymous"),
        default=False,
        help_text=_("If true, the reviewer's identity is hidden."),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PUBLISHED,
    )
    moderated_at = models.DateTimeField(_("moderated at"), null=True, blank=True)
    moderated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_reviews",
        verbose_name=_("moderated by"),
    )
    moderation_reason = models.TextField(_("moderation reason"), blank=True)
    edit_count = models.PositiveSmallIntegerField(_("edit count"), default=0)
    last_edited_at = models.DateTimeField(_("last edited at"), null=True, blank=True)

    # Denormalised response flag for efficient querying
    has_response = models.BooleanField(_("has response"), default=False)

    class Meta:
        verbose_name = _("consultation review")
        verbose_name_plural = _("consultation reviews")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["reviewer", "status"]),
            models.Index(fields=["rating"]),
        ]

    def __str__(self) -> str:
        return f"Review {self.id} — {self.rating}★ for consultation {self.consultation_id}"


class DoctorReviewResponse(BaseModel):
    """A doctor's response to a review."""

    review = models.OneToOneField(
        ConsultationReview,
        on_delete=models.CASCADE,
        related_name="response",
        verbose_name=_("review"),
    )
    doctor = models.ForeignKey(
        "doctors.DoctorProfile",
        on_delete=models.CASCADE,
        related_name="review_responses",
        verbose_name=_("doctor"),
    )
    body = models.TextField(_("body"))

    class Meta:
        verbose_name = _("doctor review response")
        verbose_name_plural = _("doctor review responses")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Response to review {self.review_id} by Dr. {self.doctor_id}"


class ReviewReport(BaseModel):
    """A user-submitted report about a review."""

    review = models.ForeignKey(
        ConsultationReview,
        on_delete=models.CASCADE,
        related_name="reports",
        verbose_name=_("review"),
    )
    reporter = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="review_reports",
        verbose_name=_("reporter"),
    )
    reason = models.CharField(
        _("reason"),
        max_length=50,
        choices=[
            ("inappropriate", _("Inappropriate Content")),
            ("spam", _("Spam")),
            ("fake", _("Fake Review")),
            ("conflict_of_interest", _("Conflict of Interest")),
            ("privacy_violation", _("Privacy Violation")),
            ("other", _("Other")),
        ],
    )
    description = models.TextField(_("description"), blank=True)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    resolved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_reports",
        verbose_name=_("resolved by"),
    )
    resolution = models.CharField(
        _("resolution"),
        max_length=30,
        choices=ReportResolution.choices,
        blank=True,
    )
    resolution_notes = models.TextField(_("resolution notes"), blank=True)

    class Meta:
        verbose_name = _("review report")
        verbose_name_plural = _("review reports")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["review", "resolved_at"]),
        ]

    def __str__(self) -> str:
        return f"Report on review {self.review_id} — {self.reason}"
