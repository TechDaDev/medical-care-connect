"""Services for consultation messaging."""

from django.db import transaction
from django.utils import timezone

from apps.consultations.models import Consultation, ConsultationStatus
from apps.accounts.models import UserRole
from apps.core.audit_service import create_audit_event
from apps.core.models import AuditEventCategory
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
    client_request_id=None,
) -> ConsultationMessage:
    """Create and return a new consultation message."""
    with transaction.atomic():
        locked = Consultation.objects.select_for_update(of=("self",)).get(
            pk=consultation.pk
        )
        if not is_system_message and not consultation_allows_messaging(locked):
            raise ValueError(
                f"Cannot send messages in status '{locked.get_status_display()}'."
            )
        if client_request_id is not None:
            existing = ConsultationMessage.objects.filter(
                sender=sender, client_request_id=client_request_id
            ).first()
            if existing:
                if existing.consultation_id != locked.id:
                    raise ValueError("client_request_id_conflict")
                return existing
        message = ConsultationMessage.objects.create(
            consultation=locked, sender=sender, message_type=message_type,
            content=content, is_system_message=is_system_message,
            client_request_id=client_request_id,
        )
        if (
            not is_system_message
            and sender.role == UserRole.PATIENT
            and locked.status == ConsultationStatus.AWAITING_PATIENT_RESPONSE
        ):
            locked.status = ConsultationStatus.AWAITING_DOCTOR_RESPONSE
            locked.save(update_fields=["status", "updated_at"])
            create_audit_event(
                "patient_response_received",
                AuditEventCategory.CONSULTATION,
                actor_id=str(sender.id),
                actor_role=sender.role,
                target_type="consultation",
                target_id=str(locked.id),
                metadata={
                    "old_status": ConsultationStatus.AWAITING_PATIENT_RESPONSE,
                    "new_status": ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
                },
            )
        return message


def mark_messages_read(messages, user) -> list[MessageReadReceipt]:
    """Mark a list of messages as read for a user. Returns new receipts."""
    existing = set(
        MessageReadReceipt.objects.filter(
            message__in=messages, user=user
        ).values_list("message_id", flat=True)
    )
    receipts = []
    for msg in messages:
        if msg.sender_id != user.id and msg.id not in existing:
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
