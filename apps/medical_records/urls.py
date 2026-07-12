from django.urls import path

from apps.medical_records import views

app_name = "records"

urlpatterns = [
    path(
        "<uuid:record_id>/",
        views.draft_record,
        name="record-detail",
    ),
    path(
        "<uuid:record_id>/confirm/",
        views.confirm_record,
        name="record-confirm",
    ),
]
