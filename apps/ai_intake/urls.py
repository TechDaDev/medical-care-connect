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
        "sessions/<uuid:session_id>/",
        views.get_session,
        name="intake-session",
    ),
]
