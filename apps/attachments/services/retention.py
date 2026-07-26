"""Retention policy service for expired attachments."""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.attachments.choices import AttachmentStatus
from apps.attachments.models import ConsultationAttachment
from apps.consultations.models import ConsultationStatus

logger = logging.getLogger(__name__)


def get_retention_cutoff():
    """Return the datetime before which soft-deleted attachments are eligible."""
    days = settings.ATTACHMENT_RETENTION_DAYS
    if days <= 0:
        return None
    return timezone.now() - timedelta(days=days)


def purge_expired(dry_run: bool = True, batch_size: int = 100) -> int:
    """Soft-deleted attachments past retention period.

    Returns count of attachments processed.
    dry_run=True: log only, no changes.
    """
    cutoff = get_retention_cutoff()
    if cutoff is None:
        logger.info("Retention policy disabled (ATTACHMENT_RETENTION_DAYS=0). Nothing to purge.")
        return 0

    qs = ConsultationAttachment.objects.filter(
        is_deleted=True,
        status=AttachmentStatus.DELETED,
        deleted_at__lt=cutoff,
        storage_deleted_at__isnull=True,
        consultation__status__in=(
            ConsultationStatus.COMPLETED,
            ConsultationStatus.CANCELLED,
        ),
    )[:batch_size]

    count = 0
    for attachment in qs:
        if dry_run:
            logger.info(
                "[DRY-RUN] Would purge attachment %s",
                attachment.id,
            )
        else:
            # Delete physical object
            from apps.attachments.services.factory import get_storage_backend
            backend = get_storage_backend()
            try:
                backend.delete(attachment.storage_key)
            except Exception as exc:
                logger.error("Failed to delete storage object for %s: %s", attachment.id, exc)
                continue
            # Preserve metadata and immutable audit history.
            from apps.attachments.choices import AttachmentEventType
            from apps.attachments.models import AttachmentAuditEvent

            attachment.storage_deleted_at = timezone.now()
            attachment.save(update_fields=["storage_deleted_at", "updated_at"])
            AttachmentAuditEvent.objects.create(
                attachment=attachment,
                actor=None,
                event_type=AttachmentEventType.RETENTION_DELETED,
                safe_metadata={"result": "success"},
            )
            logger.info("Purged attachment bytes %s", attachment.id)
        count += 1

    return count
