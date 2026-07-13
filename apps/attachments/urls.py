from django.urls import path

from apps.attachments import views

app_name = "attachments"

urlpatterns = [
    # Consultation-scoped
    path(
        "consultations/<uuid:consultation_id>/attachments/",
        views.list_attachments,
        name="list",
    ),
    path(
        "consultations/<uuid:consultation_id>/attachments/upload/",
        views.upload_attachment,
        name="upload",
    ),
    # Direct attachment access
    path(
        "attachments/<uuid:attachment_id>/",
        views.attachment_detail,
        name="detail",
    ),
    path(
        "attachments/<uuid:attachment_id>/download/",
        views.download_attachment,
        name="download",
    ),
    path(
        "attachments/<uuid:attachment_id>/delete/",
        views.delete_attachment,
        name="delete",
    ),
    path(
        "attachments/<uuid:attachment_id>/restore/",
        views.restore_attachment,
        name="restore",
    ),
]
