from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsCoordinatorOrAdministrator,
    IsDoctor,
    IsDoctorOrAdministrator,
    IsPatient,
)
from apps.consultations.models import Consultation, ConsultationStatus
from apps.reviews.models import (
    ConsultationReview,
    DoctorReviewResponse,
    ReviewReport,
    ReviewStatus,
)
from apps.reviews.serializers import (
    DoctorReputationSerializer,
    DoctorReviewResponseSerializer,
    ModerateReviewSerializer,
    ReviewDetailSerializer,
    ReviewReportResolveSerializer,
    ReviewReportSerializer,
    ReviewSerializer,
)
from apps.reviews.services import (
    compute_doctor_reputation,
    notify_moderation_state_change,
    notify_report_resolution,
    notify_review_created,
    notify_review_response,
    notify_review_updated,
)

EDIT_WINDOW_HOURS = 72


class ReviewPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


# ── Patient: Create / Get Own Review ────────────────────────────────────────


@api_view(["POST", "GET"])
@permission_classes([IsAuthenticated, IsPatient])
def consultation_review(request: Request, consultation_id: str) -> Response:
    """Create or retrieve a review for a completed consultation."""
    consultation = get_object_or_404(Consultation, id=consultation_id)

    # Verify ownership
    patient = getattr(request.user, "patient_profile", None)
    if not patient or consultation.patient != patient:
        return Response(
            {"detail": "You can only review your own consultations."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        try:
            review = ConsultationReview.objects.get(consultation=consultation)
            serializer = ReviewDetailSerializer(review)
            return Response(serializer.data)
        except ConsultationReview.DoesNotExist:
            return Response(
                {"detail": "No review found for this consultation."},
                status=status.HTTP_404_NOT_FOUND,
            )

    # POST: create new review
    if consultation.status != ConsultationStatus.COMPLETED:
        return Response(
            {"detail": "You can only review completed consultations."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if ConsultationReview.objects.filter(consultation=consultation).exists():
        return Response(
            {"detail": "A review already exists for this consultation."},
            status=status.HTTP_409_CONFLICT,
        )

    serializer = ReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    review = serializer.save(
        consultation=consultation,
        reviewer=patient,
    )
    notify_review_created(review)

    out = ReviewDetailSerializer(review)
    return Response(out.data, status=status.HTTP_201_CREATED)


# ── Patient: Update / Delete Own Review ─────────────────────────────────────


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated, IsPatient])
def consultation_review_detail(request: Request, consultation_id: str) -> Response:
    """Update or delete the patient's own review (within edit window)."""
    consultation = get_object_or_404(Consultation, id=consultation_id)
    patient = getattr(request.user, "patient_profile", None)
    if not patient or consultation.patient != patient:
        return Response(
            {"detail": "You can only modify your own reviews."},
            status=status.HTTP_403_FORBIDDEN,
        )

    review = get_object_or_404(ConsultationReview, consultation=consultation)

    # Check edit window
    if timezone.now() > review.created_at + timedelta(hours=EDIT_WINDOW_HOURS):
        return Response(
            {"detail": f"Reviews can only be edited within {EDIT_WINDOW_HOURS} hours of creation."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if request.method == "DELETE":
        review.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = ReviewSerializer(review, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(
        edit_count=review.edit_count + 1,
        last_edited_at=timezone.now(),
    )
    notify_review_updated(review)

    out = ReviewDetailSerializer(review)
    return Response(out.data)


# ── Public: Doctor Reviews (published only) ─────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def doctor_reviews(request: Request, doctor_id: str) -> Response:
    """Paginated published reviews for a doctor."""
    from apps.doctors.models import DoctorProfile

    doctor = get_object_or_404(DoctorProfile, id=doctor_id)
    reviews = ConsultationReview.objects.filter(
        consultation__doctor=doctor,
        status=ReviewStatus.PUBLISHED,
    ).select_related(
        "consultation", "consultation__doctor", "consultation__doctor__user",
        "reviewer", "reviewer__user",
    ).prefetch_related("reports")

    paginator = ReviewPagination()
    page = paginator.paginate_queryset(reviews, request)
    serializer = ReviewDetailSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# ── Public: Doctor Reputation ───────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def doctor_reputation(request: Request, doctor_id: str) -> Response:
    """Aggregated reputation data for a doctor."""
    from apps.doctors.models import DoctorProfile

    doctor = get_object_or_404(DoctorProfile, id=doctor_id)
    data = compute_doctor_reputation(doctor)
    if data is None:
        return Response({
            "doctor_id": doctor_id,
            "doctor_name": doctor.user.full_name,
            "average_rating": 0.0,
            "total_reviews": 0,
            "rating_distribution": {},
            "response_rate": 0.0,
            "recent_ratings_trend": "no_reviews",
        })
    data["doctor_id"] = doctor_id
    data["doctor_name"] = doctor.user.full_name
    serializer = DoctorReputationSerializer(data)
    return Response(serializer.data)


# ── Doctor: Respond to Review ───────────────────────────────────────────────


@api_view(["POST", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated, IsDoctor])
def review_response(request: Request, review_id: str) -> Response:
    """Create, update, or delete a doctor's response to a review."""
    review = get_object_or_404(ConsultationReview, id=review_id)
    doctor = getattr(request.user, "doctor_profile", None)
    if not doctor:
        return Response(
            {"detail": "Doctor profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Verify doctor owns the consultation
    if review.consultation.doctor != doctor:
        return Response(
            {"detail": "You can only respond to reviews for your own consultations."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # DELETE
    if request.method == "DELETE":
        try:
            existing = DoctorReviewResponse.objects.get(review=review, doctor=doctor)
            existing.delete()
            review.has_response = False
            review.save(update_fields=["has_response"])
        except DoctorReviewResponse.DoesNotExist:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)

    # POST — create
    if request.method == "POST":
        if DoctorReviewResponse.objects.filter(review=review).exists():
            return Response(
                {"detail": "A response already exists for this review. Use PATCH to update."},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = DoctorReviewResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = serializer.save(
            review=review,
            doctor=doctor,
        )
        review.has_response = True
        review.save(update_fields=["has_response"])
        notify_review_response(review, response)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # PATCH — update
    response = get_object_or_404(DoctorReviewResponse, review=review, doctor=doctor)
    serializer = DoctorReviewResponseSerializer(response, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


# ── Report a Review ─────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def report_review(request: Request, review_id: str) -> Response:
    """Report a review for moderation."""
    review = get_object_or_404(ConsultationReview, id=review_id)

    # Prevent duplicate open reports from same user
    if ReviewReport.objects.filter(review=review, reporter=request.user, resolved_at__isnull=True).exists():
        return Response(
            {"detail": "You already have an open report for this review."},
            status=status.HTTP_409_CONFLICT,
        )

    serializer = ReviewReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(review=review, reporter=request.user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


# ── Staff: Review List ──────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def staff_review_list(request: Request) -> Response:
    """List all reviews for staff moderation."""
    status_filter = request.query_params.get("status")
    rating = request.query_params.get("rating")

    reviews = ConsultationReview.objects.select_related(
        "consultation", "consultation__patient", "consultation__patient__user",
        "consultation__doctor", "consultation__doctor__user",
        "reviewer", "reviewer__user",
    ).prefetch_related("reports")

    if status_filter:
        reviews = reviews.filter(status=status_filter)
    if rating:
        reviews = reviews.filter(rating=rating)

    paginator = ReviewPagination()
    page = paginator.paginate_queryset(reviews, request)
    serializer = ReviewDetailSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# ── Staff: Moderate Review ──────────────────────────────────────────────────


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def staff_moderate_review(request: Request, review_id: str) -> Response:
    """Moderate a review (change status)."""
    review = get_object_or_404(ConsultationReview, id=review_id)

    serializer = ModerateReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    previous_status = review.status
    review.status = serializer.validated_data["status"]
    review.moderated_at = timezone.now()
    review.moderated_by = request.user
    review.moderation_reason = serializer.validated_data.get("moderation_reason", "")
    review.save()

    # Notify if status changed
    if previous_status != review.status:
        notify_moderation_state_change(review)

    out = ReviewDetailSerializer(review)
    return Response(out.data)


# ── Staff: Report List ──────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def staff_report_list(request: Request) -> Response:
    """List all review reports."""
    resolved = request.query_params.get("resolved")
    reports = ReviewReport.objects.select_related(
        "review", "reporter", "resolved_by",
    ).order_by("-created_at")

    if resolved == "false":
        reports = reports.filter(resolved_at__isnull=True)
    elif resolved == "true":
        reports = reports.filter(resolved_at__isnull=False)

    paginator = ReviewPagination()
    page = paginator.paginate_queryset(reports, request)
    serializer = ReviewReportSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# ── Staff: Resolve Report ───────────────────────────────────────────────────


@api_view(["PATCH"])
@permission_classes([IsAuthenticated, IsCoordinatorOrAdministrator])
def staff_resolve_report(request: Request, report_id: str) -> Response:
    """Resolve a review report."""
    report = get_object_or_404(ReviewReport, id=report_id)

    serializer = ReviewReportResolveSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    report.resolved_at = timezone.now()
    report.resolved_by = request.user
    report.resolution = serializer.validated_data["resolution"]
    report.resolution_notes = serializer.validated_data.get("resolution_notes", "")
    report.save()

    notify_report_resolution(report)

    out = ReviewReportSerializer(report)
    return Response(out.data)
