from django.urls import path

from apps.reviews import views

app_name = "reviews"

urlpatterns = [
    # Patient review management (per consultation)
    path(
        "consultations/<uuid:consultation_id>/review/",
        views.consultation_review,
        name="consultation-review",
    ),
    path(
        "consultations/<uuid:consultation_id>/review/edit/",
        views.consultation_review_detail,
        name="consultation-review-detail",
    ),
    # Public doctor reviews and reputation
    path(
        "doctors/<uuid:doctor_id>/reviews/",
        views.doctor_reviews,
        name="doctor-reviews",
    ),
    path(
        "doctors/<uuid:doctor_id>/reputation/",
        views.doctor_reputation,
        name="doctor-reputation",
    ),
    # Doctor response
    path(
        "reviews/<uuid:review_id>/response/",
        views.review_response,
        name="review-response",
    ),
    # Report a review
    path(
        "reviews/<uuid:review_id>/report/",
        views.report_review,
        name="report-review",
    ),
]
