from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path(
        "<uuid:id>/read/",
        views.mark_notification_read,
        name="mark-one-read",
    ),
    path("read/", views.mark_notifications_read, name="mark-read"),
    path("read-all/", views.mark_notifications_read, name="mark-all-read"),
    path("unread-count/", views.unread_notification_count, name="unread-count"),
]
