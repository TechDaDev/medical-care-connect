"""Retention policy service for expired attachments."""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.attachments.choices import AttachmentStatus
from apps.attachments.models import ConsultationAttachment

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
    )[:batch_size]

    count = 0
    for attachment in qs:
        if dry_run:
            logger.info(
                "[DRY-RUN] Would purge attachment %s (%s)",
                attachment.id, attachment.original_filename,
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
            # Hard-delete DB record
            attachment.delete()
            logger.info("Purged attachment %s", attachment.id)
        count += 1

    return count
