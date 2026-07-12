from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notification_list(request: Request) -> Response:
    """List notifications for the current user, newest first."""
    notifications: QuerySet[Notification] = (
        Notification.objects
        .filter(recipient=request.user)
        .select_related("consultation", "related_message")
        .order_by("-created_at")
    )
    # Optional ?unread=true filter
    if request.query_params.get("unread", "").lower() == "true":
        notifications = notifications.filter(is_read=False)

    serializer = NotificationSerializer(notifications, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_notifications_read(request: Request) -> Response:
    """Mark all unread notifications as read for the current user."""
    now = timezone.now()
    updated = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).update(is_read=True, read_at=now)
    return Response({"marked_read": updated})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unread_notification_count(request: Request) -> Response:
    """Get the number of unread notifications."""
    count = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()
    return Response({"unread_count": count})
