from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("read/", views.mark_notifications_read, name="mark-read"),
    path("unread-count/", views.unread_notification_count, name="unread-count"),
]
