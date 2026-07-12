from django.urls import path

from apps.messaging import views as msg_views

app_name = "messaging"

urlpatterns = [
    # Messages
    path(
        "<uuid:consultation_pk>/messages/",
        msg_views.message_list_create,
        name="message-list",
    ),
    path(
        "<uuid:consultation_pk>/messages/read/",
        msg_views.mark_messages_read_view,
        name="message-mark-read",
    ),
    path(
        "<uuid:consultation_pk>/messages/unread-count/",
        msg_views.unread_count_view,
        name="message-unread-count",
    ),
    path(
        "unread-counts/",
        msg_views.unread_counts_all_view,
        name="all-unread-counts",
    ),
    # Internal notes
    path(
        "<uuid:consultation_pk>/internal-notes/",
        msg_views.internal_note_list_create,
        name="internal-note-list",
    ),
    path(
        "<uuid:consultation_pk>/internal-notes/<uuid:note_pk>/",
        msg_views.internal_note_detail,
        name="internal-note-detail",
    ),
]
