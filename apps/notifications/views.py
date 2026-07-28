from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.notifications.models import Notification
from apps.notifications.serializers import (
    NotificationQuerySerializer,
    NotificationSerializer,
)


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notification_list(request: Request) -> Response:
    """List notifications for the current user, newest first."""
    query_serializer = NotificationQuerySerializer(data=request.query_params)
    query_serializer.is_valid(raise_exception=True)
    filters = query_serializer.validated_data
    notifications: QuerySet[Notification] = (
        Notification.objects
        .filter(recipient=request.user)
        .select_related(
            "consultation",
            "recipient",
            "related_message",
            "consultation__medical_record",
        )
        .order_by("-created_at")
    )
    # Optional ?unread=true filter
    if filters.get("unread"):
        notifications = notifications.filter(is_read=False)
    if notification_type := filters.get("type"):
        notifications = notifications.filter(notification_type=notification_type)
    if created_after := filters.get("created_after"):
        notifications = notifications.filter(created_at__date__gte=created_after)
    if created_before := filters.get("created_before"):
        notifications = notifications.filter(created_at__date__lte=created_before)

    paginator = NotificationPagination()
    page = paginator.paginate_queryset(notifications, request)
    serializer = NotificationSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_notification_read(request: Request, id) -> Response:
    notification = (
        Notification.objects.filter(recipient=request.user, id=id)
        .select_related(
            "consultation",
            "recipient",
            "related_message",
            "consultation__medical_record",
        )
        .first()
    )
    if notification is None:
        return Response(
            {"detail": "Not found.", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at", "updated_at"])
    return Response(NotificationSerializer(notification).data)


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
