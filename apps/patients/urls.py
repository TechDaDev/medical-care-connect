from django.urls import path

from apps.patients import views

app_name = "patients"

urlpatterns = [
    path("me/", views.my_patient_profile, name="my-profile"),
    path("me/dashboard/", views.my_patient_dashboard, name="my-dashboard"),
    path(
        "me/medical-records/",
        views.my_medical_records,
        name="medical-record-list",
    ),
    path(
        "me/medical-records/<uuid:id>/",
        views.my_medical_record_detail,
        name="medical-record-detail",
    ),
    path(
        "me/message-threads/",
        views.my_message_threads,
        name="message-thread-list",
    ),
]
