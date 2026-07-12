from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import UserRole
from apps.accounts.permissions import IsDoctor
from apps.consultations.models import Consultation
from apps.messaging.models import ConsultationMessage, DoctorInternalNote
from apps.messaging.serializers import (
    InternalNoteCreateSerializer,
    InternalNoteSerializer,
    MarkReadSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from apps.messaging.services import (
    get_unread_message_counts,
    mark_messages_read,
)
from apps.notifications.services import notify_new_message


def _get_consultation_or_404(pk: str, user) -> Consultation:
    """Get a consultation the user is a participant of."""
    qs = Consultation.objects.select_related("patient__user", "doctor__user")
    consultation = get_object_or_404(qs, pk=pk)

    is_participant = (
        (hasattr(user, "patient_profile") and consultation.patient == user.patient_profile)
        or (hasattr(user, "doctor_profile") and consultation.doctor == user.doctor_profile)
    )
    if not is_participant and user.role not in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        return None
    return consultation


# ── Messages ────────────────────────────────────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def message_list_create(request: Request, consultation_pk: str) -> Response:
    """List messages for a consultation, or send a new message.

    GET  → all messages (ordered by sent_at).
    POST → send a text message.
    """
    consultation = _get_consultation_or_404(consultation_pk, request.user)
    if consultation is None:
        return Response(
            {"detail": "You do not have access to this consultation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        messages: QuerySet[ConsultationMessage] = (
            ConsultationMessage.objects
            .filter(consultation=consultation)
            .select_related("sender")
            .prefetch_related("read_receipts__user")
            .order_by("sent_at")
        )
        # Mark messages as read for this user
        unread = messages.exclude(sender=request.user).exclude(
            read_receipts__user=request.user
        )
        if unread.exists():
            mark_messages_read(unread, request.user)

        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    # POST
    serializer = MessageCreateSerializer(
        data=request.data,
        context={"consultation": consultation, "sender": request.user},
    )
    serializer.is_valid(raise_exception=True)
    message = serializer.save()

    # Notify other participant
    notify_new_message(message)

    output = MessageSerializer(message)
    return Response(output.data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_messages_read_view(request: Request, consultation_pk: str) -> Response:
    """Mark specific messages as read for the current user."""
    consultation = _get_consultation_or_404(consultation_pk, request.user)
    if consultation is None:
        return Response(
            {"detail": "You do not have access to this consultation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = MarkReadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    messages = ConsultationMessage.objects.filter(
        consultation=consultation,
        id__in=serializer.validated_data["message_ids"],
    )
    mark_messages_read(messages, request.user)
    return Response({"detail": "Messages marked as read."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unread_count_view(request: Request, consultation_pk: str) -> Response:
    """Get unread message count for a consultation."""
    consultation = _get_consultation_or_404(consultation_pk, request.user)
    if consultation is None:
        return Response(
            {"detail": "You do not have access to this consultation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    counts = get_unread_message_counts(consultation, request.user)
    counts["consultation_id"] = consultation.id
    return Response(counts)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unread_counts_all_view(request: Request) -> Response:
    """Get unread message counts for all consultations the user is in."""
    user = request.user
    consultations = Consultation.objects.none()

    if hasattr(user, "patient_profile"):
        consultations = Consultation.objects.filter(patient=user.patient_profile)
    elif hasattr(user, "doctor_profile"):
        consultations = Consultation.objects.filter(doctor=user.doctor_profile)
    elif user.role in (UserRole.COORDINATOR, UserRole.ADMINISTRATOR):
        consultations = Consultation.objects.all()

    results = []
    for c in consultations:
        counts = get_unread_message_counts(c, user)
        results.append({"consultation_id": c.id, "unread_count": counts["unread_count"]})
    return Response(results)


# ── Internal Notes ─────────────────────────────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsDoctor])
def internal_note_list_create(request: Request, consultation_pk: str) -> Response:
    """List or create internal doctor notes for a consultation."""
    consultation = get_object_or_404(Consultation, pk=consultation_pk)

    # Doctor must be the assigned doctor
    doctor_profile = getattr(request.user, "doctor_profile", None)
    if doctor_profile is None or consultation.doctor != doctor_profile:
        return Response(
            {"detail": "You are not the assigned doctor for this consultation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        notes = DoctorInternalNote.objects.filter(
            consultation=consultation
        ).select_related("author").order_by("-created_at")
        serializer = InternalNoteSerializer(notes, many=True)
        return Response(serializer.data)

    # POST
    serializer = InternalNoteCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    note = DoctorInternalNote.objects.create(
        consultation=consultation,
        author=request.user,
        content=serializer.validated_data["content"],
    )
    output = InternalNoteSerializer(note)
    return Response(output.data, status=status.HTTP_201_CREATED)


@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated, IsDoctor])
def internal_note_detail(request: Request, consultation_pk: str, note_pk: str) -> Response:
    """Get or delete a specific internal note."""
    consultation = get_object_or_404(Consultation, pk=consultation_pk)

    doctor_profile = getattr(request.user, "doctor_profile", None)
    if doctor_profile is None or consultation.doctor != doctor_profile:
        return Response(
            {"detail": "You are not the assigned doctor for this consultation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    note = get_object_or_404(
        DoctorInternalNote,
        pk=note_pk,
        consultation=consultation,
        author=request.user,
    )

    if request.method == "GET":
        serializer = InternalNoteSerializer(note)
        return Response(serializer.data)

    # DELETE
    note.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
