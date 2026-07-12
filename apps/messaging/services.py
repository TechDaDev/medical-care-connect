"""Services for consultation messaging."""

from django.db import transaction
from django.utils import timezone

from apps.consultations.models import Consultation, ConsultationStatus
from apps.messaging.models import ConsultationMessage, MessageReadReceipt, MessageType


MESSAGING_ALLOWED_STATUSES = {
    ConsultationStatus.SUBMITTED,
    ConsultationStatus.ACCEPTED,
    ConsultationStatus.INTAKE_IN_PROGRESS,
    ConsultationStatus.INTAKE_COMPLETED,
    ConsultationStatus.DOCTOR_REVIEW,
    ConsultationStatus.AWAITING_PATIENT_RESPONSE,
    ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
    ConsultationStatus.UNDER_REVIEW,
    ConsultationStatus.FOLLOW_UP_REQUIRED,
    ConsultationStatus.PHYSICAL_VISIT_REQUIRED,
    ConsultationStatus.TRANSFERRED,
}


def consultation_allows_messaging(consultation: Consultation) -> bool:
    """Check if the consultation status allows messaging."""
    return consultation.status in MESSAGING_ALLOWED_STATUSES


def create_consultation_message(
    consultation: Consultation,
    sender,
    content: str,
    *,
    message_type: str = MessageType.TEXT,
    is_system_message: bool = False,
) -> ConsultationMessage:
    """Create and return a new consultation message."""
    if not is_system_message and not consultation_allows_messaging(consultation):
        raise ValueError(
            f"Cannot send messages in status '{consultation.get_status_display()}'."
        )
    return ConsultationMessage.objects.create(
        consultation=consultation,
        sender=sender,
        message_type=message_type,
        content=content,
        is_system_message=is_system_message,
    )


def mark_messages_read(messages, user) -> list[MessageReadReceipt]:
    """Mark a list of messages as read for a user. Returns new receipts."""
    existing = set(
        MessageReadReceipt.objects.filter(
            message__in=messages, user=user
        ).values_list("message_id", flat=True)
    )
    receipts = []
    for msg in messages:
        if msg.id not in existing:
            receipts.append(
                MessageReadReceipt(message=msg, user=user, read_at=timezone.now())
            )
    if receipts:
        MessageReadReceipt.objects.bulk_create(receipts)
    return receipts


def get_unread_message_counts(consultation: Consultation, user) -> dict:
    """Get unread message count per consultation for a user."""
    total = ConsultationMessage.objects.filter(
        consultation=consultation,
    ).exclude(
        sender=user,
    ).exclude(
        read_receipts__user=user,
    ).count()
    return {"unread_count": total}
