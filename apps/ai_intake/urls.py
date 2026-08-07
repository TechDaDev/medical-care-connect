from django.urls import path

from apps.ai_intake import views

app_name = "intake"

urlpatterns = [
    path(
        "sessions/<uuid:session_id>/answer/",
        views.answer_intake,
        name="intake-answer",
    ),
    path(
        "sessions/<uuid:session_id>/review/",
        views.intake_review,
        name="intake-review",
    ),
    path(
        "sessions/<uuid:session_id>/corrections/",
        views.intake_corrections,
        name="intake-corrections",
    ),
    path(
        "sessions/<uuid:session_id>/confirm/",
        views.intake_confirm,
        name="intake-confirm",
    ),
    path(
        "sessions/<uuid:session_id>/submit/",
        views.intake_submit,
        name="intake-submit",
    ),
    path(
        "sessions/<uuid:session_id>/",
        views.get_session,
        name="intake-session",
    ),
]